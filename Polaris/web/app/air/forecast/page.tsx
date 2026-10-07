"use client";
import { useMemo, useState } from "react";
import { usePost } from "@/lib/hooks";
import { nf0 } from "@/lib/format";
import { ErrorNote, PageHead, Panel, Term } from "@/components/ui";
import { Analyst } from "@/components/Analyst";
import { AirChart } from "@/components/charts";
import type { AirForecast, AirMeta } from "@/lib/types";

const HORIZONS = [7, 14, 30];
const MODELS = ["Auto (validation winner)", "Seasonal Ridge", "Lag Ridge", "Random forest", "Persistence", "Seasonal persistence"];

export default function AirForecastSheet() {
  const [city, setCity] = useState("NOIDA");
  const [horizon, setHorizon] = useState(14);
  const [model, setModel] = useState(MODELS[0]);
  const { data: meta } = usePost<AirMeta>("/api/air/meta", {});
  const body = useMemo(() => ({ city, horizon, model }), [city, horizon, model]);
  const { data: r, error, loading } = usePost<AirForecast>("/api/air/forecast", body);

  const figures = r && [
    `City: ${r.city} · ${r.unit} · regional CO2`,
    `History available: ${r.first} to ${r.last}, ${r.coverage_pct.toFixed(1)}% of calendar days present`,
    `Latest observed: ${r.latest.value.toFixed(2)} ${r.unit} on ${r.latest.date}`,
    `Day-${r.horizon} forecast: ${r.final.value.toFixed(2)} ${r.unit} on ${r.final.date} (nominal 90% band ${r.final.lower.toFixed(2)} to ${r.final.upper.toFixed(2)})`,
    `Change from latest: ${(r.final.value - r.latest.value >= 0 ? "+" : "")}${(r.final.value - r.latest.value).toFixed(2)} ${r.unit}`,
    `Model in use: ${r.selected}`,
    `Holdout MAE at the ${r.eval_horizon}-day horizon: ${r.mae.toFixed(2)} ${r.unit} over ${r.targets} targets; RMSE ${r.rmse.toFixed(2)}; nominal 90% band actually covered ${(r.coverage * 100).toFixed(0)}%`,
    `Persistence benchmark MAE: ${r.persistence_mae.toFixed(2)} ${r.unit}`,
    `VERDICT (computed by Polaris, not by you): the selected model ${r.beats_persistence ? "BEAT" : "DID NOT BEAT"} persistence here, skill ${r.skill_pct >= 0 ? "+" : ""}${r.skill_pct.toFixed(1)}%.`,
    `Holdout scores by model:\n${r.metrics.map((m) => `  ${m.model}: MAE ${m.mae.toFixed(2)}, RMSE ${m.rmse.toFixed(2)}, coverage ${(m.coverage_90 * 100).toFixed(0)}%`).join("\n")}`,
    `LIMIT: ${r.scope}`,
    `Source: ${r.origin}. ${r.citation}`,
  ].join("\n");

  return (
    <>
      <PageHead eyebrow="Air · forecast" title="What will the air hold next fortnight?">
        Emissions are one half of the story; the other is what is already overhead. This sheet trains Ridge and random-forest
        models on a city&apos;s own regional CO<sub>2</sub> history and forecasts ahead, against a{" "}
        <Term tip="Tomorrow equals today. Any model that cannot beat it is not earning its keep.">persistence benchmark</Term>.
      </PageHead>

      <div className="btns noprint" role="group" aria-label="City">
        {(meta?.cities ?? []).map((c) => (
          <button key={c.station} className="chip-btn" aria-pressed={city === c.station} onClick={() => setCity(c.station)}>{c.name}</button>
        ))}
        <span aria-hidden style={{ width: 10 }} />
        {HORIZONS.map((h) => (
          <button key={h} className="chip-btn" aria-pressed={horizon === h} onClick={() => setHorizon(h)}>{h} days</button>
        ))}
      </div>

      <ErrorNote message={error} />

      {r && (
        <>
          <div className="kpis">
            <div className="kpi"><div className="k">Latest estimate</div><div className="v num">{r.latest.value.toFixed(2)}<small>{r.unit}</small></div><div className="d">{r.latest.date}</div></div>
            <div className="kpi"><div className="k">Day {r.horizon} forecast</div><div className="v num">{r.final.value.toFixed(2)}<small>{r.unit}</small></div><div className="d">{r.final.value - r.latest.value >= 0 ? "+" : ""}{(r.final.value - r.latest.value).toFixed(2)} from latest · band {r.final.lower.toFixed(1)}–{r.final.upper.toFixed(1)}</div></div>
            <div className="kpi"><div className="k">Holdout error</div><div className="v num">{r.mae.toFixed(2)}<small>MAE</small></div><div className="d">over {nf0.format(r.targets)} held-out targets</div></div>
            <div className="kpi"><div className="k">Skill over persistence</div><div className="v num" style={{ color: r.beats_persistence ? "var(--good)" : "var(--bad)" }}>{r.skill_pct >= 0 ? "+" : ""}{r.skill_pct.toFixed(1)}%</div><div className="d">{r.beats_persistence ? "the model is ahead" : "the benchmark is ahead"}</div></div>
          </div>

          {!r.beats_persistence && (
            <p className="alert err">
              On this city&apos;s holdout the trained model loses to the benchmark: MAE {r.mae.toFixed(2)} against {r.persistence_mae.toFixed(2)} {r.unit}.
              The forecast is still shown, because hiding it would be the dishonest choice — but prefer the benchmark here.
            </p>
          )}

          <div className="grid2">
            <Panel title={`${r.city} · observation to outlook`} tick="var(--s2)">
              <AirChart history={r.history} forecast={r.forecast} unit={r.unit} />
              <p className="note">Shaded band is the nominal 90% range calibrated on past errors; it actually covered {(r.coverage * 100).toFixed(0)}% of holdout targets.</p>
            </Panel>
            <div className="stack">
              <Panel title="Every model on the same holdout" tick="var(--ml)">
                <div className="scroll">
                  <table className="t"><thead><tr><th>Model</th><th className="r">MAE</th><th className="r">RMSE</th><th className="r">90% coverage</th></tr></thead>
                    <tbody>{r.metrics.map((m) => (
                      <tr key={m.model} className={m.model === r.selected ? "best" : ""}>
                        <td>{m.model}{m.model === r.selected ? " · in use" : ""}</td>
                        <td className="r num">{m.mae.toFixed(2)}</td><td className="r num">{m.rmse.toFixed(2)}</td>
                        <td className="r num">{(m.coverage_90 * 100).toFixed(0)}%</td>
                      </tr>))}</tbody></table>
                </div>
                <div className="btns" style={{ marginTop: 12 }} role="group" aria-label="Model">
                  {MODELS.map((m) => <button key={m} className="chip-btn" aria-pressed={model === m} onClick={() => setModel(m)}>{m.replace(" (validation winner)", "")}</button>)}
                </div>
              </Panel>
              <Panel title="What this is, and is not" tick="var(--warn)">
                <p className="note" style={{ marginTop: 0 }}>{r.scope}</p>
                <p className="note">Training {r.split.train_start} to {r.split.train_end_exclusive}; calibration to {r.split.test_start}; the holdout is untouched by model choice or band width. {r.origin}.</p>
              </Panel>
            </div>
          </div>

          <Analyst sheet="Air forecast" figures={figures ?? ""} presets={["Explain this forecast", "Did the model beat the benchmark?", "What are the limits of this number?"]} />
        </>
      )}
      {loading && !r && <p className="note">Training the models…</p>}
    </>
  );
}
