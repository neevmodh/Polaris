import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import path from "node:path";
import readline from "node:readline";

/** Backend bridge. Polaris runs two Python engines as long-lived child processes and talks to them in JSON lines:
 *  - carbon: SCOPE's tested footprint, model and planning code (carbon/api_worker.py)
 *  - sat:    Task 3's satellite analysis code, wrapped by engines/sat_worker.py
 *  - air:    Task 1's greenhouse-gas forecasts, wrapped by engines/air_worker.py
 *  - grid:   the NetZeroAI microgrid optimiser, wrapped by engines/grid_worker.py
 *  Each is located relative to this project and can be moved with SCOPE_DIR / TASK3_DIR / TASK1_DIR / NETZERO_DIR. */
const POLARIS = path.resolve(process.cwd(), "..");
const SCOPE = process.env.SCOPE_DIR ?? path.resolve(POLARIS, "..", "SCOPE");
const TASK3 = process.env.TASK3_DIR ?? path.resolve(POLARIS, "..", "Task3");
const TASK1 = process.env.TASK1_DIR ?? path.resolve(POLARIS, "..", "task1");
const NETZERO = process.env.NETZERO_DIR ?? path.resolve(POLARIS, "..", "netzero-ai");
const TIMEOUT_MS = 120_000;
const READY_MS = Number(process.env.POLARIS_READY_MS ?? 60_000);   // a worker that never says ready must not hang requests
const MAX_PENDING = 24;                                             // per engine; beyond this we refuse instead of queueing without limit

type Spec = { cmd: string; args: string[]; cwd: string; env: Record<string, string> };
const SPECS: Record<string, Spec> = {
  carbon: { cmd: process.env.SCOPE_PYTHON ?? path.join(SCOPE, ".venv", "bin", "python"), args: ["-m", "carbon.api_worker"], cwd: SCOPE, env: {} },
  sat: {
    cmd: process.env.TASK3_PYTHON ?? path.join(TASK3, ".venv", "bin", "python"), args: [path.join(POLARIS, "engines", "sat_worker.py")], cwd: TASK3,
    env: { TASK3_DIR: TASK3, POLARIS_DATA: path.join(POLARIS, "data") },
  },
  air: {
    cmd: process.env.TASK1_PYTHON ?? path.join(TASK1, ".venv", "bin", "python"), args: [path.join(POLARIS, "engines", "air_worker.py")], cwd: TASK1,
    env: { TASK1_DIR: TASK1 },
  },
  grid: {
    cmd: process.env.NETZERO_PYTHON ?? path.join(NETZERO, ".venv", "bin", "python"), args: [path.join(POLARIS, "engines", "grid_worker.py")], cwd: NETZERO,
    env: { NETZERO_DIR: NETZERO },
  },
};
export type EngineName = keyof typeof SPECS;

type Pending = { resolve: (v: unknown) => void; reject: (e: Error) => void; timer: NodeJS.Timeout };
type State = { proc?: ChildProcessWithoutNullStreams; ready?: Promise<void>; pending: Map<number, Pending>; seq: number; inflight: Map<string, Promise<unknown>> };
const g = globalThis as unknown as { __polarisEngines?: Record<string, State> };
const states: Record<string, State> = (g.__polarisEngines ??= {});

export class EngineError extends Error {
  constructor(message: string, public kind: "input" | "internal" | "engine" | "busy") { super(message); }
}

function start(name: string, st: State): Promise<void> {
  const spec = SPECS[name];
  const proc = spawn(/*turbopackIgnore: true*/ spec.cmd, spec.args, { cwd: spec.cwd, env: { ...process.env, ...spec.env }, stdio: ["pipe", "pipe", "pipe"] });
  st.proc = proc;
  proc.stderr.on("data", (d) => { if (process.env.POLARIS_DEBUG) process.stderr.write(`[${name}] ${d}`); });
  const rl = readline.createInterface({ input: proc.stdout });
  let onReady: () => void, onFail: (e: Error) => void;
  const ready = new Promise<void>((res, rej) => { onReady = res; onFail = rej; });
  rl.on("line", (line) => {
    let msg: { ready?: boolean; id?: number; ok?: boolean; result?: unknown; error?: string; kind?: string };
    try { msg = JSON.parse(line); } catch { return; }
    if (msg.ready) return onReady();
    const p = msg.id != null ? st.pending.get(msg.id) : undefined;
    if (!p) return;
    clearTimeout(p.timer); st.pending.delete(msg.id!);
    if (msg.ok) p.resolve(msg.result);
    else p.reject(new EngineError(msg.error ?? "engine error", msg.kind === "input" ? "input" : msg.kind === "busy" ? "busy" : "internal"));
  });
  proc.on("error", (e) => onFail(new EngineError(`Cannot start the ${name} engine at ${spec.cmd}: ${e.message}`, "engine")));
  proc.on("exit", (code) => {
    st.proc = undefined; st.ready = undefined;
    onFail(new EngineError(`The ${name} engine exited (${code})`, "engine"));
    for (const [id, p] of st.pending) { clearTimeout(p.timer); p.reject(new EngineError(`The ${name} engine restarted`, "engine")); st.pending.delete(id); }
  });
  return ready;
}

function reset(st: State) { const p = st.proc; st.proc = undefined; st.ready = undefined; try { p?.kill("SIGKILL"); } catch { /* already gone */ } }

export async function engine<T = unknown>(name: EngineName, cmd: string, args: unknown = {}): Promise<T> {
  const st = (states[name] ??= { pending: new Map(), seq: 0, inflight: new Map() });
  // Identical requests already running share one answer, so a burst of the same call does one unit of work.
  const dedupe = JSON.stringify([cmd, args]);
  const running = st.inflight.get(dedupe);
  if (running) return running as Promise<T>;
  if (st.pending.size >= MAX_PENDING) throw new EngineError(`The ${name} engine is busy. Try again in a moment.`, "busy");

  const work = (async () => {
    if (!st.proc) st.ready = start(name, st);
    const ready = st.ready!;
    let t: NodeJS.Timeout | undefined;
    try {
      await Promise.race([ready, new Promise<never>((_, rej) => { t = setTimeout(() => rej(new EngineError(`The ${name} engine did not become ready within ${Math.round(READY_MS / 1000)} s`, "engine")), READY_MS); })]);
    } catch (e) { reset(st); throw e; }          // an unhealthy start is torn down so the next call gets a fresh one
    finally { clearTimeout(t); }
    const id = ++st.seq;
    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        st.pending.delete(id);
        reject(new EngineError("Engine timed out", "engine"));
        // The Python side cannot be interrupted mid-call. If nothing else is waiting, restart it so the abandoned work stops.
        if (st.pending.size === 0) reset(st);
      }, TIMEOUT_MS);
      st.pending.set(id, { resolve: resolve as (v: unknown) => void, reject, timer });
      st.proc!.stdin.write(JSON.stringify({ id, cmd, args }) + "\n");
    });
  })();
  st.inflight.set(dedupe, work);
  try { return await work; } finally { st.inflight.delete(dedupe); }
}

export async function handle(name: EngineName, cmd: string, req?: Request, extra?: (body: unknown) => unknown): Promise<Response> {
  try {
    let args: unknown = {};
    if (req && req.method === "POST") {
      try { args = await req.json(); } catch { return Response.json({ error: "Body must be valid JSON" }, { status: 400 }); }
    }
    return Response.json(await engine(name, cmd, extra ? extra(args) : args));
  } catch (e) {
    if (e instanceof EngineError) return Response.json({ error: e.message }, { status: e.kind === "input" ? 422 : e.kind === "busy" ? 503 : 502 });
    return Response.json({ error: "Unexpected server error" }, { status: 500 });
  }
}

export const RESULTS_DIR = path.join(SCOPE, "results");
export const PATHS = { POLARIS, SCOPE, TASK3, TASK1, NETZERO };
