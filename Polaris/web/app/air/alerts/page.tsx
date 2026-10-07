"use client";
import { useMemo, useState } from "react";
import { usePost } from "@/lib/hooks";
import { ErrorNote, PageHead, Panel, Slider, Term } from "@/components/ui";
import { Analyst } from "@/components/Analyst";
import { AlertChart } from "@/components/charts";
import type { AirAlerts, AirMeta } from "@/lib/types";

/** Which recent days sat far above their own recent history. A review queue, never a health warning. */
export default function AirAlertsSheet() {
  const [city, setCity] = useState("NOIDA");
  const [sigma, setSigma] = useState(2.5);
  const { data: meta } = usePost<AirMeta>("/api/air/meta", {});
  const body = useMemo(() => ({ city, sigma }), [city, sigma]);
  const { data: r, error, loading } = usePost<AirAlerts>("/api/air/alerts", body);

  const hits = (r?.rows ?? []).filter((x) => x.flag);
  const figures = r && [
    `City: ${r.city} · ${r.unit} · regional CO2`,
    `Window: the latest ${r.days} days of the record`,
    `Review sensitivity: ${r.sigma} standard deviations above the preceding 90 days`,
    `Days flagged: ${r.flagged} of ${r.days}`,
    hits.length ? `Flagged days:\n${hits.slice(-12).map((x) => `  ${x.date}: ${x.value.toFixed(2)} ${r.unit} against a review level of ${x.level?.toFixed(2) ?? "n/a"}`).join("\n")}` : "No day crossed the review level in this window.",
    "LIMIT: each threshold uses only the 90 days before it, so a flag means a value is unusual against its own recent history.",
    "LIMIT: these are statistical review flags on a regional model estimate. They are not health warnings, not pollution measurements, and not proof of a local emission source.",
  ].join("\n");

  return (
    <>
      <PageHead eyebrow="Air · alerts" title="Which days were unusual?">
        A day is flagged when it sits more than a chosen number of{" "}
        <Term tip="Computed from the 90 days before that day only, so no future information leaks into the threshold.">standard deviations</Term>{" "}
        above its own preceding history. This is a review queue for an analyst, not a health warning.
      </PageHead>

      <div className="btns noprint" role="group" aria-label="City">
        {(meta?.cities ?? []).map((c) => (
          <button key={c.station} className="chip-btn" aria-pressed={city === c.station} onClick={() => setCity(c.station)}>{c.name}</button>
        ))}
      </div>

      <ErrorNote message={error} />

      {r && (
        <>
          <div className="kpis">
            <div className="kpi"><div className="k">Days flagged</div><div className="v num" style={{ color: r.flagged ? "var(--warn)" : "var(--good)" }}>{r.flagged}</div><div className="d">of the latest {r.days} days</div></div>
            <div className="kpi"><div className="k">Sensitivity</div><div className="v num">{r.sigma.toFixed(1)}<small>σ</small></div><div className="d">above the preceding 90 days</div></div>
            <div className="kpi"><div className="k">Highest flagged</div><div className="v num">{hits.length ? Math.max(...hits.map((h) => h.value)).toFixed(2) : "—"}<small>{r.unit}</small></div><div className="d">{hits.length ? `on ${hits.reduce((a, b) => (b.value > a.value ? b : a)).date}` : "nothing crossed the level"}</div></div>
          </div>

          <Panel title={`${r.city} · latest ${r.days} days`} tick="var(--warn)">
            <AlertChart rows={r.rows} unit={r.unit} />
            <Slider label="Review sensitivity" value={sigma} min={1.5} max={4} step={0.5} onChange={setSigma} format={(v) => `${v.toFixed(1)} σ`} />
            <p className="note">Lowering the sensitivity flags more days. Nothing here measures exposure: these are regional model estimates over a 3° × 2° cell.</p>
          </Panel>

          {hits.length > 0 && (
            <Panel title="Flagged days" tick="var(--bad)">
              <div className="scroll">
                <table className="t"><thead><tr><th>Date</th><th className="r">Value ({r.unit})</th><th className="r">Review level</th><th className="r">Above by</th></tr></thead>
                  <tbody>{hits.slice().reverse().slice(0, 20).map((x) => (
                    <tr key={x.date}><td className="num">{x.date}</td><td className="r num">{x.value.toFixed(2)}</td>
                      <td className="r num">{x.level?.toFixed(2) ?? "—"}</td>
                      <td className="r num">{x.level != null ? `+${(x.value - x.level).toFixed(2)}` : "—"}</td></tr>))}</tbody></table>
              </div>
            </Panel>
          )}

          <Analyst sheet="Air alerts" figures={figures ?? ""} presets={["What do these flags mean?", "Should anyone act on this?", "How could this method mislead?"]} />
        </>
      )}
      {loading && !r && <p className="note">Reading the record…</p>}
    </>
  );
}
