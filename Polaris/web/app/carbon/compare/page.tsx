"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useGet, usePost } from "@/lib/hooks";
import { useStore } from "@/lib/store";
import { download, ledger, resultRows, toBody, toCsv } from "@/lib/export";
import type { CalcInputs, CalcResult, Meta, Scenario } from "@/lib/types";
import { fmtT, nf0, pct } from "@/lib/format";
import { ErrorNote, PageHead, Panel } from "@/components/ui";

const SC = [{ k: "scope1", n: "Scope 1", c: "var(--s1)" }, { k: "scope2", n: "Scope 2", c: "var(--s2)" }, { k: "scope3", n: "Scope 3", c: "var(--s3)" }, { k: "total", n: "Total", c: "var(--ink)" }] as const;

function changes(a: CalcInputs, b: CalcInputs, meta: Meta | null): string[] {
  const out: string[] = [];
  const d = (label: string, x: number, y: number, unit: string) => { if (x !== y) out.push(`${label}: ${nf0.format(x)} → ${nf0.format(y)} ${unit}`); };
  meta?.fuels.forEach((f) => d(f.label.replace(/ \(.*\)/, ""), a.fuel[f.key] ?? 0, b.fuel[f.key] ?? 0, f.label.match(/\((.*)\)/)?.[1] ?? ""));
  d("Grid electricity", a.kwh, b.kwh, "kWh");
  if (a.td_loss !== b.td_loss) out.push(`T&D loss: ${pct(a.td_loss)} → ${pct(b.td_loss)}`);
  meta?.scope3.forEach((c) => d(c.label, a.spend_lakh[c.key] ?? 0, b.spend_lakh[c.key] ?? 0, "₹ lakh"));
  return out;
}

function Slot({ slot, sc, save, clear, name, setName }: { slot: "A" | "B"; sc: Scenario | null; save: () => void; clear: () => void; name: string; setName: (v: string) => void }) {
  return (
    <div style={{ display: "flex", gap: 14, alignItems: "flex-end", flexWrap: "wrap" }}>
      <div style={{ font: "800 40px/1 var(--font-display)", width: 34 }} aria-hidden>{slot}</div>
      <div className="field" style={{ flex: "1 1 180px" }}>
        <label htmlFor={`name-${slot}`}>Scenario {slot} name</label>
        <div className="inp"><input id={`name-${slot}`} value={name} onChange={(e) => setName(e.target.value)} placeholder={slot === "A" ? "Today" : "With solar and PPA"} maxLength={40} /></div>
      </div>
      <button className="btn primary" onClick={save}>{sc ? "Replace with current inputs" : "Save current inputs"}</button>
      {sc && <button className="btn ghost" onClick={clear}>Remove</button>}
    </div>
  );
}

export default function Compare() {
  const { inputs, scenarios, saveScenario, clearScenario } = useStore();
  const { data: meta } = useGet<Meta>("/api/meta");
  const [nameA, setNameA] = useState(""), [nameB, setNameB] = useState("");
  const A = scenarios.A, B = scenarios.B;
  const ra = usePost<CalcResult>("/api/calc", useMemo(() => (A ? toBody(A.inputs) : {}), [A]), { enabled: !!A });
  const rb = usePost<CalcResult>("/api/calc", useMemo(() => (B ? toBody(B.inputs) : {}), [B]), { enabled: !!B });
  const both = A && B && ra.data && rb.data;
  const max = both ? Math.max(...SC.slice(0, 3).flatMap((s) => [ra.data!.range[s.k].p95, rb.data!.range[s.k].p95])) * 1.05 : 1;
  const diff = both ? changes(A.inputs, B.inputs, meta) : [];

  const exportJson = () => {
    if (!meta || !both || ra.loading || rb.loading) return;
    const payload = { generated_by: "SCOPE · Team CarbonIQ", data_status: meta.data_source, generated_at: new Date().toISOString(),
      scenarios: Object.fromEntries(([["A", A, ra.data], ["B", B, rb.data]] as const).filter(([, s]) => s).map(([k, s, r]) => [k, { name: s!.name, saved_at: s!.savedAt, inputs: structuredClone(s!.inputs), result: r, assumptions: ledger(meta, s!.inputs), calculated_at: k === "A" ? ra.calculatedAt : rb.calculatedAt, input_fingerprint: k === "A" ? ra.snapshotKey : rb.snapshotKey }])),
      calculation_version: ra.version };
    download("scope-scenarios.json", JSON.stringify(payload, null, 2), "application/json");
  };
  const exportCsv = () => {
    if (!both || ra.loading || rb.loading) return;
    const rows = [...(A && ra.data ? resultRows(A.name, ra.data) : []), ...(B && rb.data ? resultRows(B.name, rb.data) : [])];
    download("scope-scenarios.csv", toCsv(rows), "text/csv");
  };

  return (
    <>
      <PageHead eyebrow="Scenario compare" title="Scenario A against scenario B.">
        Save your current inputs as A, change something on the calculator (a new generator, a green power contract, a supplier switch), save again as B, and read the difference with its uncertainty.
      </PageHead>
      <div className="stack fade">
        <Panel title="Save slots" tick="var(--ink)" right={<span>stored in this browser</span>}>
          <Slot slot="A" sc={A} name={nameA} setName={setNameA} save={() => saveScenario("A", nameA.trim() || "Scenario A")} clear={() => clearScenario("A")} />
          <Slot slot="B" sc={B} name={nameB} setName={setNameB} save={() => saveScenario("B", nameB.trim() || "Scenario B")} clear={() => clearScenario("B")} />
          <p className="note">Current inputs: {nf0.format(inputs.fuel.diesel_l ?? 0)} L diesel · {nf0.format(inputs.kwh)} kWh · {Object.values(inputs.spend_lakh).filter((v) => v > 0).length} spend lines. Edit them on <Link href="/carbon" className="btn ghost" style={{ padding: 0 }}>the calculator</Link>.</p>
        </Panel>
        <ErrorNote message={ra.error ?? rb.error} />
        {!A || !B ? (
          <div className="alert"><span aria-hidden>→</span>{!A && !B ? "Save the current inputs as scenario A to begin." : `Scenario ${A ? "A" : "B"} is saved. Change the inputs on the calculator, then save scenario ${A ? "B" : "A"}.`}</div>
        ) : both ? (
          <>
            <div className="grid2 even">
              {([[A, ra.data!], [B, rb.data!]] as const).map(([s, r], i) => (
                <section className="panel" key={i}>
                  <div className="panel-h"><span className="tick">{i === 0 ? "A" : "B"} · {s.name}</span></div>
                  <div className="panel-b">
                    <div className="big" style={{ fontSize: "clamp(44px,5.4vw,70px)" }}>{fmtT(r.point.total)}<small>tCO₂e / yr</small></div>
                    <div className="seg" role="img" aria-label="Share by scope">
                      {SC.slice(0, 3).map((x, j) => <div key={x.k} className={["a", "b", "c"][j]} style={{ flexGrow: Math.max(r.point[x.k], 1e-9), flexBasis: 0 }} />)}
                    </div>
                  </div>
                </section>
              ))}
            </div>
            <Panel title="Difference, B minus A" tick="var(--ink)">
              <div className="scroll"><table className="t">
                <thead><tr><th>Scope</th><th className="r">A</th><th className="r">B</th><th className="r">Change</th><th className="r">Change %</th><th>Scale</th></tr></thead>
                <tbody>
                  {SC.map((s) => {
                    const a = ra.data!.point[s.k], b = rb.data!.point[s.k], d = b - a;
                    return (
                      <tr key={s.k}>
                        <td><b style={{ color: s.c }}>{s.n}</b></td>
                        <td className="r">{fmtT(a)}</td><td className="r">{fmtT(b)}</td>
                        <td className="r" style={{ color: d < 0 ? "var(--good)" : d > 0 ? "var(--bad)" : undefined, fontWeight: 700 }}>{d > 0 ? "+" : ""}{fmtT(d)}</td>
                        <td className="r">{a ? `${d > 0 ? "+" : ""}${((d / a) * 100).toFixed(1)}%` : "–"}</td>
                        <td style={{ minWidth: 200 }}>
                          {s.k !== "total" && (<div style={{ display: "grid", gap: 3 }}>
                            <div style={{ height: 7, background: "var(--muted)", width: `${(a / max) * 100}%`, opacity: .55 }} />
                            <div style={{ height: 7, background: s.c, width: `${(b / max) * 100}%` }} />
                          </div>)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table></div>
              <p className="note">Ranges (P5–P95): total A {fmtT(ra.data!.range.total.p5)}–{fmtT(ra.data!.range.total.p95)} t, total B {fmtT(rb.data!.range.total.p5)}–{fmtT(rb.data!.range.total.p95)} t. If the ranges overlap heavily, the difference may be smaller than the data can resolve.</p>
            </Panel>
            <Panel title="What changed between A and B" tick="var(--ink)">
              {diff.length ? <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 4 }}>{diff.map((d) => <li key={d}>{d}</li>)}</ul> : <p className="note">The two scenarios have identical inputs.</p>}
            </Panel>
          </>
        ) : <div className="skeleton" style={{ height: 220 }} />}
        <Panel title="Take it with you" tick="var(--ink)">
          <div className="btns">
            <Link className="btn primary" href="/carbon/report">Open printable report</Link>
            <button className="btn" onClick={exportCsv} disabled={!both || ra.loading || rb.loading}>Download CSV</button>
            <button className="btn" onClick={exportJson} disabled={!meta || !both || ra.loading || rb.loading}>Download JSON with assumptions</button>
          </div>
          <p className="note">The JSON includes every factor, its source and its uncertainty, so a reviewer can re-run the numbers.</p>
        </Panel>
      </div>
    </>
  );
}
