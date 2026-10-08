import { ask, available, model, AskError } from "@/lib/ask";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

/** The analyst spends a shared server credential, so every request is bounded: a strict body schema, size limits,
 *  a per-client quota and a global hourly budget. */
const SHEETS = new Set(["Carbon calculator", "Air forecast", "Air alerts", "Microgrid dispatch"]);
const LIMITS = { question: 500, figures: 8000, bodyBytes: 20_000, perMinute: 6, perHour: 40, globalPerHour: 400 };
const hits = new Map<string, number[]>();
let global: number[] = [];

function client(req: Request): string {
  const fwd = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  return fwd || req.headers.get("x-real-ip") || "local";
}
function allow(key: string, now: number): string | null {
  const keep = (a: number[], ms: number) => a.filter((t) => now - t < ms);
  global = keep(global, 3_600_000);
  if (global.length >= LIMITS.globalPerHour) return "The analyst has reached its hourly limit for everyone. Try again later.";
  const mine = keep(hits.get(key) ?? [], 3_600_000);
  if (mine.length >= LIMITS.perHour) return "You have reached the hourly limit for the analyst. Try again later.";
  if (keep(mine, 60_000).length >= LIMITS.perMinute) return "Too many questions in a minute. Wait a little and ask again.";
  mine.push(now); hits.set(key, mine); global.push(now);
  if (hits.size > 5000) for (const [k, v] of hits) if (!keep(v, 3_600_000).length) hits.delete(k);
  return null;
}

export async function GET() {
  return Response.json({ enabled: available(), model: available() ? model() : null });
}

export async function POST(req: Request) {
  const raw = await req.text().catch(() => "");
  if (raw.length > LIMITS.bodyBytes) return Response.json({ error: "That request is too large." }, { status: 413 });
  let body: unknown;
  try { body = JSON.parse(raw); } catch { return Response.json({ error: "Body must be valid JSON" }, { status: 400 }); }
  if (!body || typeof body !== "object" || Array.isArray(body)) return Response.json({ error: "Body must be a JSON object." }, { status: 422 });
  const { question, figures, sheet, ...extra } = body as Record<string, unknown>;
  if (Object.keys(extra).length) return Response.json({ error: `Unknown field: ${Object.keys(extra)[0]}.` }, { status: 422 });
  if (typeof question !== "string" || typeof figures !== "string" || typeof sheet !== "string") return Response.json({ error: "question, figures and sheet must be text." }, { status: 422 });
  if (!question.trim() || question.length > LIMITS.question) return Response.json({ error: `The question must be 1 to ${LIMITS.question} characters.` }, { status: 422 });
  if (!figures.trim() || figures.length > LIMITS.figures) return Response.json({ error: `The figures must be 1 to ${LIMITS.figures} characters.` }, { status: 422 });
  if (!SHEETS.has(sheet)) return Response.json({ error: "Unknown sheet." }, { status: 422 });
  const blocked = allow(client(req), Date.now());
  if (blocked) return Response.json({ error: blocked }, { status: 429 });
  try {
    return Response.json({ answer: await ask(question, figures, sheet), basis: "client-supplied figures" });
  } catch (e) {
    if (e instanceof AskError) return Response.json({ error: e.message }, { status: e.status });
    return Response.json({ error: "Unexpected server error" }, { status: 500 });
  }
}
