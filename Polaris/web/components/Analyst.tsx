"use client";
import { useEffect, useState } from "react";
import { Panel } from "@/components/ui";

/** The analyst panel. A sheet passes the figures it has already computed; the language model only
 *  puts them into words. Nothing is sent until the reader asks, and the exact text sent is shown. */
export function Analyst({ sheet, figures, presets }: { sheet: string; figures: string; presets: string[] }) {
  const [status, setStatus] = useState<{ enabled: boolean; model: string | null } | null>(null);
  const [q, setQ] = useState(presets[0] ?? "");
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [shown, setShown] = useState(false);

  useEffect(() => { fetch("/api/ask").then((r) => r.json()).then(setStatus).catch(() => setStatus({ enabled: false, model: null })); }, []);

  async function run(question: string) {
    setQ(question); setBusy(true); setAnswer(""); setError("");
    try {
      const r = await fetch("/api/ask", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, figures, sheet }),
      });
      const j = await r.json();
      if (r.ok) setAnswer(j.answer); else setError(j.error ?? `Request failed (${r.status})`);
    } catch { setError("Cannot reach the server."); }
    setBusy(false);
  }

  const off = status != null && !status.enabled;
  return (
    <Panel title="Ask the analyst" tick="var(--ml)"
      right={<span className="note mono">{off ? "needs a key" : status?.model ?? "…"}</span>}>
      <p className="note" style={{ marginTop: 0 }}>
        A language model puts this sheet&apos;s figures into plain words. It is given the computed numbers only —
        it cannot recompute them, and it is told to quote them exactly and invent nothing.
      </p>
      {off ? (
        <p className="note">Set <code>GROQ_API_KEY</code> in <code>Polaris/.env</code> and restart to switch the analyst on.</p>
      ) : (
        <>
          <div className="btns">
            {presets.map((p) => (
              <button key={p} type="button" className="chip-btn" aria-pressed={q === p} disabled={busy} onClick={() => run(p)}>{p}</button>
            ))}
          </div>
          <div className="askrow">
            <label className="sr-only" htmlFor="ask-q">Your question</label>
            <input id="ask-q" value={q} disabled={busy} placeholder="Ask anything about the figures on this sheet"
              onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && q.trim()) run(q); }} />
            <button type="button" className="btn primary" disabled={busy || !q.trim()} onClick={() => run(q)}>
              {busy ? "Reading…" : "Ask"}
            </button>
          </div>
          {error && <p className="alert err" role="alert">{error}</p>}
          {answer && (
            <div className="answer" role="status">
              {answer.split(/\n{2,}/).map((para, i) => <p key={i}>{para}</p>)}
            </div>
          )}
          {answer && <p className="note">Generated text. The figures above and the Evidence sheets remain the source of truth.</p>}
          <details className="det" onToggle={(e) => setShown((e.target as HTMLDetailsElement).open)}>
            <summary>Exactly what the analyst was shown</summary>
            {shown && <pre className="figpre">{figures}</pre>}
          </details>
        </>
      )}
    </Panel>
  );
}
