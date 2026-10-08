"use client";
import { useEffect, useRef, useState } from "react";
import { Panel } from "@/components/ui";

/** The analyst panel. A sheet passes the figures it has already computed; the language model only
 *  puts them into words. Nothing is sent until the reader asks, and the exact text sent is shown. */
/** An answer belongs to the exact figures it was asked about. If the sheet's figures move on, the answer is marked
 *  stale instead of being allowed to describe a scenario that is no longer on screen. */
type Answered = { text: string; question: string; figures: string; at: string };

export function Analyst({ sheet, figures, presets, disabled = false }: { sheet: string; figures: string; presets: string[]; disabled?: boolean }) {
  const [status, setStatus] = useState<{ enabled: boolean; model: string | null } | null>(null);
  const [q, setQ] = useState(presets[0] ?? "");
  const [answered, setAnswered] = useState<Answered | null>(null);
  const [failure, setFailure] = useState<{ figures: string; message: string } | null>(null);
  const seq = useRef(0);                              // only the newest request may settle the panel
  const [pending, setPending] = useState<string | null>(null);        // the figures a request is in flight for
  const [shown, setShown] = useState(false);

  useEffect(() => { fetch("/api/ask").then((r) => r.json()).then(setStatus).catch(() => setStatus({ enabled: false, model: null })); }, []);

  // Figures change (new scenario, new inputs, a recalculation in flight): nothing asked earlier may be shown as current,
  // and a request still on the wire for the old figures must not land on the new ones.
  useEffect(() => { seq.current++; }, [figures]);            // a request still on the wire for older figures can no longer settle

  async function run(question: string) {
    if (!figures || disabled) return;
    const snapshot = figures, id = ++seq.current;       // freeze exactly what is being asked about
    setQ(question); setPending(snapshot); setFailure(null);
    try {
      const r = await fetch("/api/ask", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, figures: snapshot, sheet }),
      });
      const j = await r.json();
      if (id !== seq.current) return;                    // superseded while waiting
      if (r.ok) setAnswered({ text: j.answer, question, figures: snapshot, at: new Date().toLocaleTimeString() });
      else setFailure({ figures: snapshot, message: j.error ?? `Request failed (${r.status})` });
    } catch { if (id === seq.current) setFailure({ figures: snapshot, message: "Cannot reach the server." }); }
    if (id === seq.current) setPending(null);
  }

  const off = status != null && !status.enabled;
  const ready = Boolean(figures) && !disabled;
  const busy = pending !== null && pending === figures;
  const error = failure && failure.figures === figures ? failure.message : "";
  const stale = answered != null && answered.figures !== figures;
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
              <button key={p} type="button" className="chip-btn" aria-pressed={q === p} disabled={busy || !ready} onClick={() => run(p)}>{p}</button>
            ))}
          </div>
          <div className="askrow">
            <label className="sr-only" htmlFor="ask-q">Your question</label>
            <input id="ask-q" value={q} disabled={busy} placeholder="Ask anything about the figures on this sheet"
              onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && q.trim()) run(q); }} />
            <button type="button" className="btn primary" disabled={busy || !ready || !q.trim()} onClick={() => run(q)}>
              {busy ? "Reading…" : ready ? "Ask" : "Calculating…"}
            </button>
          </div>
          {error && <p className="alert err" role="alert">{error}</p>}
          {answered && (
            <div className={"answer" + (stale ? " stale" : "")} role="status" aria-live="polite">
              <p className="note" style={{ margin: 0 }}>{stale ? "Out of date: the figures on this sheet have changed since this was asked." : `Answered at ${answered.at} for the figures below.`} Question: {answered.question}</p>
              {answered.text.split(/\n{2,}/).map((para, i) => <p key={i}>{para}</p>)}
            </div>
          )}
          {answered && <p className="note">Generated text. The figures it was given come from this page and are not re-checked by the server; the sheet and the Evidence pages remain the source of truth.</p>}
          <details className="det" onToggle={(e) => setShown((e.target as HTMLDetailsElement).open)}>
            <summary>{answered ? "Exactly what the analyst was shown for the answer above" : "What the analyst will be shown"}</summary>
            {shown && <pre className="figpre">{answered ? answered.figures : figures}</pre>}
          </details>
        </>
      )}
    </Panel>
  );
}
