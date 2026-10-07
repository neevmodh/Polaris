import fs from "node:fs";
import path from "node:path";
import { PATHS } from "@/lib/py";

/** The analyst: a Groq-hosted language model that explains figures Polaris has already computed.
 *  It never produces a number. Every sheet hands it its own computed facts, and the model is told
 *  to quote them exactly, to contradict nothing, and to say so when the data does not answer. */

const URL = "https://api.groq.com/openai/v1/chat/completions";

function env(name: string): string {
  if (process.env[name]) return process.env[name]!;
  for (const dir of [PATHS.POLARIS, path.join(PATHS.POLARIS, "web"), PATHS.TASK1, PATHS.NETZERO]) {
    try {
      for (const line of fs.readFileSync(path.join(dir, ".env"), "utf8").split("\n")) {
        if (line.startsWith(name + "=")) return line.slice(name.length + 1).trim();
      }
    } catch { /* no .env here */ }
  }
  return "";
}

export const model = () => env("GROQ_MODEL") || "openai/gpt-oss-120b";
export const available = () => Boolean(env("GROQ_API_KEY"));

const SYSTEM = [
  "You are the analyst for Polaris, a climate measurement and planning tool.",
  "Use ONLY the FIGURES block you are given. It was computed by tested code and is authoritative.",
  "Quote its numbers exactly, with their units. Never invent a figure, a source or a trend.",
  "Never contradict a line marked VERDICT or LIMIT; repeat its meaning in your own words instead.",
  "If the figures do not answer the question, say exactly that and name what is missing.",
  "Satellite results are screening, not proof. Spend-based Scope 3 is an estimate, not a measurement.",
  "Write plain prose for a non-specialist. No markdown, no asterisks, no headings. Under 160 words.",
].join(" ");

export class AskError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export async function ask(question: string, figures: string, sheet: string): Promise<string> {
  const key = env("GROQ_API_KEY");
  if (!key) throw new AskError("No GROQ_API_KEY is set, so the analyst is off. Add one to Polaris/.env and restart.", 503);
  if (!question.trim()) throw new AskError("Ask a question first.", 422);
  if (figures.length > 20_000) throw new AskError("Too much context to explain at once.", 422);

  let res: Response;
  try {
    res = await fetch(URL, {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: model(), temperature: 0.2, max_tokens: 700,
        messages: [
          { role: "system", content: SYSTEM },
          { role: "user", content: `SHEET: ${sheet}\n\nFIGURES (authoritative):\n${figures}\n\nQUESTION: ${question.trim()}` },
        ],
      }),
      signal: AbortSignal.timeout(45_000),
    });
  } catch {
    throw new AskError("Could not reach Groq. Check the network and try again.", 502);
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json())?.error?.message ?? detail; } catch { /* keep the status */ }
    throw new AskError(`The analyst is unavailable: ${detail}`, 502);
  }
  const body = await res.json();
  const text = String(body?.choices?.[0]?.message?.content ?? "").trim();
  if (!text) throw new AskError("The analyst returned an empty answer.", 502);
  return text.replace(/\*\*/g, "").replace(/^[*-] /gm, "• ");
}
