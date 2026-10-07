import { handle, engine, EngineError } from "@/lib/py";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

const POST_OK = new Set(["scene", "analyze", "crop", "review", "export", "fetch_start", "fetch_status", "case"]);

export async function GET(_: Request, ctx: { params: Promise<{ cmd: string }> }) {
  const { cmd } = await ctx.params;
  return cmd === "meta" ? handle("sat", "meta") : Response.json({ error: "Not found" }, { status: 404 });
}

export async function POST(req: Request, ctx: { params: Promise<{ cmd: string }> }) {
  const { cmd } = await ctx.params;
  if (cmd === "upload") {                                   // two rasters as multipart form data
    try {
      const f = await req.formData(), file = (k: string) => f.get(k) as File | null;
      const before = file("before"), after = file("after");
      if (!before || !after || typeof before === "string" || typeof after === "string") return Response.json({ error: "Attach both GeoTIFF files." }, { status: 422 });
      if (before.size > 60e6 || after.size > 60e6) return Response.json({ error: "Each file must be under 60 MB." }, { status: 422 });
      const b64 = async (x: File) => Buffer.from(await x.arrayBuffer()).toString("base64");
      return Response.json(await engine("sat", "upload", {
        before_b64: await b64(before), after_b64: await b64(after), before_name: before.name, after_name: after.name,
        before_date: f.get("before_date"), after_date: f.get("after_date"), encoding: f.get("encoding") ?? "float",
        name: f.get("name") ?? "Uploaded pair", kind: f.get("kind") ?? "forest",
      }));
    } catch (e) {
      if (e instanceof EngineError) return Response.json({ error: e.message }, { status: e.kind === "input" ? 422 : 502 });
      return Response.json({ error: "Could not read the upload." }, { status: 400 });
    }
  }
  if (!POST_OK.has(cmd)) return Response.json({ error: "Not found" }, { status: 404 });
  return handle("sat", cmd, req);
}
