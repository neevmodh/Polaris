import { randomBytes, createHash } from "node:crypto";
import { handle, engine, EngineError } from "@/lib/py";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

const POST_OK = new Set(["scene", "analyze", "crop", "review", "export", "fetch_start", "fetch_status", "case"]);

const COOKIE = "polaris_owner";
const FILE_MAX = 60e6;                       // per raster
const BODY_MAX = 2 * FILE_MAX + 2e6;         // both rasters plus form fields
const MAX_UPLOADS = 2;                       // concurrent uploads in flight on this server
let uploading = 0;

/** Who is calling. A random token lives in an HttpOnly cookie; the engine only ever sees a hash of it, and private
 *  cases (uploads, fetched regions, their reviews) belong to that hash. Demo cases stay public. */
function owner(req: Request): { id: string; fresh: string | null } {
  const raw = /(?:^|;\s*)polaris_owner=([0-9a-f]{32})/.exec(req.headers.get("cookie") ?? "")?.[1];
  const token = raw ?? randomBytes(16).toString("hex");
  const id = createHash("sha256").update(token).digest("hex").slice(0, 16);
  const secure = req.url.startsWith("https:") || req.headers.get("x-forwarded-proto") === "https";
  return { id, fresh: raw ? null : `${COOKIE}=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000${secure ? "; Secure" : ""}` };
}

function withCookie(res: Response, fresh: string | null): Response {
  if (fresh) res.headers.append("set-cookie", fresh);
  return res;
}

/** Read the request body up to a hard cap, aborting as soon as it is exceeded instead of buffering it all first. */
async function readCapped(req: Request, max: number): Promise<Uint8Array | null> {
  const declared = Number(req.headers.get("content-length") ?? NaN);
  if (Number.isFinite(declared) && declared > max) return null;
  if (!req.body) return new Uint8Array();
  const reader = req.body.getReader(), chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > max) { await reader.cancel(); return null; }
    chunks.push(value);
  }
  const out = new Uint8Array(total); let at = 0;
  for (const c of chunks) { out.set(c, at); at += c.byteLength; }
  return out;
}

export async function GET(req: Request, ctx: { params: Promise<{ cmd: string }> }) {
  const { cmd } = await ctx.params;
  if (cmd !== "meta") return Response.json({ error: "Not found" }, { status: 404 });
  const o = owner(req);
  return withCookie(await handle("sat", "meta", undefined, () => ({ _owner: o.id })), o.fresh);
}

export async function POST(req: Request, ctx: { params: Promise<{ cmd: string }> }) {
  const { cmd } = await ctx.params;
  const o = owner(req);
  if (cmd === "upload") {                                   // two rasters as multipart form data
    if (uploading >= MAX_UPLOADS) return withCookie(Response.json({ error: "Too many uploads are in progress. Try again shortly." }, { status: 429 }), o.fresh);
    uploading++;
    try {
      const body = await readCapped(req, BODY_MAX);
      if (!body) return withCookie(Response.json({ error: "The upload is too large. Each raster must be under 60 MB." }, { status: 413 }), o.fresh);
      const f = await new Response(new Blob([body as BlobPart]), { headers: { "content-type": req.headers.get("content-type") ?? "" } }).formData();
      const file = (k: string) => f.get(k) as File | null;
      const before = file("before"), after = file("after");
      if (!before || !after || typeof before === "string" || typeof after === "string") return withCookie(Response.json({ error: "Attach both GeoTIFF files." }, { status: 422 }), o.fresh);
      if (before.size > FILE_MAX || after.size > FILE_MAX) return withCookie(Response.json({ error: "Each file must be under 60 MB." }, { status: 422 }), o.fresh);
      const b64 = async (x: File) => Buffer.from(await x.arrayBuffer()).toString("base64");
      const res = Response.json(await engine("sat", "upload", {
        before_b64: await b64(before), after_b64: await b64(after), before_name: before.name, after_name: after.name,
        before_date: f.get("before_date"), after_date: f.get("after_date"), encoding: f.get("encoding") ?? "float",
        name: f.get("name") ?? "Uploaded pair", kind: f.get("kind") ?? "forest", _owner: o.id,
      }));
      return withCookie(res, o.fresh);
    } catch (e) {
      if (e instanceof EngineError) return withCookie(Response.json({ error: e.message }, { status: e.kind === "input" ? 422 : e.kind === "busy" ? 503 : 502 }), o.fresh);
      return withCookie(Response.json({ error: "Could not read the upload." }, { status: 400 }), o.fresh);
    } finally { uploading--; }
  }
  if (!POST_OK.has(cmd)) return Response.json({ error: "Not found" }, { status: 404 });
  return withCookie(await handle("sat", cmd, req, (body) => ({ ...(body as object), _owner: o.id })), o.fresh);
}
