import { readFile } from "node:fs/promises";
import path from "node:path";
import { RESULTS_DIR } from "@/lib/py";
export const dynamic = "force-dynamic";

export async function GET(_: Request, ctx: { params: Promise<{ name: string }> }) {
  const { name } = await ctx.params;
  if (!/^[a-z0-9_]+\.png$/i.test(name)) return new Response("Not found", { status: 404 });   // allow-list: no path traversal
  try {
    const buf = await readFile(path.join(RESULTS_DIR, name));
    return new Response(new Uint8Array(buf), { headers: { "Content-Type": "image/png", "Cache-Control": "no-store" } });
  } catch { return new Response("Not found", { status: 404 }); }
}
