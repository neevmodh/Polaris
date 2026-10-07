import { ask, available, model, AskError } from "@/lib/ask";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function GET() {
  return Response.json({ enabled: available(), model: available() ? model() : null });
}

export async function POST(req: Request) {
  let body: { question?: string; figures?: string; sheet?: string };
  try { body = await req.json(); } catch { return Response.json({ error: "Body must be valid JSON" }, { status: 400 }); }
  try {
    return Response.json({ answer: await ask(String(body.question ?? ""), String(body.figures ?? ""), String(body.sheet ?? "Polaris")) });
  } catch (e) {
    if (e instanceof AskError) return Response.json({ error: e.message }, { status: e.status });
    return Response.json({ error: "Unexpected server error" }, { status: 500 });
  }
}
