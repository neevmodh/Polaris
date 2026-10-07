import { handle } from "@/lib/py";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

const OK = new Set(["meta", "forecast", "alerts", "compare"]);

export async function POST(req: Request, ctx: { params: Promise<{ cmd: string }> }) {
  const { cmd } = await ctx.params;
  if (!OK.has(cmd)) return Response.json({ error: "Not found" }, { status: 404 });
  return handle("air", cmd, req);
}
