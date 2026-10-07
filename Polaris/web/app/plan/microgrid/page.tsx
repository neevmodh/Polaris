"use client";
import { useMemo, useState } from "react";
import { usePost } from "@/lib/hooks";
import { nf0 } from "@/lib/format";
import { ErrorNote, PageHead, Panel, Term } from "@/components/ui";
import { Analyst } from "@/components/Analyst";
import { GridChart } from "@/components/charts";
import type { GridCompare, GridMeta, GridPlan } from "@/lib/types";

const LABELS: Record<string, string> = {
  "": "Normal day", normal: "Normal day", cloud_event: "Cloud event", wind_drop: "Wind drop",
  load_spike: "Evening load spike", battery_low: "Battery low", grid_outage: "Grid outage",
};

/** The grid-tied cousin of the diesel dispatch sheet: solar, wind and a battery against a tariff. */
export default function MicrogridSheet() {
  const [scenario, setScenario] = useState("");
  const { data: meta } = usePost<GridMeta>("/api/grid/meta", {});
  const { data: cmp } = usePost<GridCompare>("/api/grid/compare", {});
  const body = useMemo(() => ({ scenario, hours: 24 }), [scenario]);
  const { data: r, error, loading } = usePost<GridPlan>("/api/grid/plan", body);

  const k = r?.kpis;
  const fallback = r?.method === "rule-based fallback";
  const figures = r && k && [
    `Plan: ${LABELS[r.scenario] ?? r.scenario}, 24 hours ahead`,
    `Plan type: ${r.method}${r.fallback_reason ? ` because ${r.fallback_reason}. It is NOT a cost-optimal plan and you must say so.` : " by the HiGHS solver"}`,
    `Demand over the day: ${nf0.format(k.load_kwh)} kWh`,
    `Renewable energy used ${nf0.format(k.renewable_used_kwh)} kWh of ${nf0.format(k.renewable_offered_kwh)} kWh offered (${k.renewable_utilization_pct.toFixed(1)}%); spilled ${nf0.format(k.renewable_spilled_kwh)} kWh`,
    `Grid import ${nf0.format(k.grid_import_kwh)} kWh (${k.grid_dependency_pct.toFixed(1)}% of demand), cost Rs ${nf0.format(k.grid_cost_rs)}, grid CO2 ${nf0.format(k.grid_co2_kg)} kg`,
    `Unserved load ${nf0.format(k.unserved_kwh)} kWh; critical load coverage ${k.critical_load_coverage_pct.toFixed(1)}%`,
    `Battery state of charge ranged ${Math.min(...r.dispatch.map((d) => d.soc_pct)).toFixed(0)}% to ${Math.max(...r.dispatch.map((d) => d.soc_pct)).toFixed(0)}%`,
    `Plant: ${meta?.config.plant.solar_kw ?? "?"} kW solar, ${meta?.config.plant.wind_kw ?? "?"} kW wind, ${meta?.config.battery.capacity_kwh ?? "?"} kWh battery, grid import limit ${meta?.config.grid.import_kw ?? "?"} kW`,
    cmp ? `Every scenario, unserved kWh: ${cmp.rows.map((x) => `${LABELS[x.scenario] ?? x.scenario} ${x.kpis.unserved_kwh.toFixed(0)}`).join("; ")}` : "",
    `LIMIT: the dataset behind this sheet is synthetic demo data, so the forecast errors show the pipeline works, not field accuracy.`,
  ].filter(Boolean).join("\n");

  return (
    <>
      <PageHead eyebrow="Plan · microgrid" title="Can sun, wind and a battery carry the day?">
        The grid-tied counterpart to the diesel sheet. Forecasts of solar, wind and demand feed a{" "}
        <Term tip="A linear programme solved by HiGHS: it chooses, for every hour, how much to draw from each source so the whole day is cheapest.">linear optimiser</Term>{" "}
        that schedules the battery and grid against a time-of-day tariff — then every disturbance is thrown at the same day.
      </PageHead>

      <div className="btns noprint" role="group" aria-label="Scenario">
        <button className="chip-btn" aria-pressed={scenario === ""} onClick={() => setScenario("")}>Normal day</button>
        {(meta?.scenarios ?? []).map((s) => (
          <button key={s} className="chip-btn" aria-pressed={scenario === s} onClick={() => setScenario(s)}>{LABELS[s] ?? s}</button>
        ))}
      </div>

      <ErrorNote message={error} />

      {r && k && (
        <>
          <div className="kpis">
            <div className="kpi"><div className="k">Renewable used</div><div className="v num">{nf0.format(k.renewable_used_kwh)}<small>kWh</small></div><div className="d">{k.renewable_utilization_pct.toFixed(1)}% of what sun and wind offered{k.renewable_spilled_kwh > 1 ? ` · ${nf0.format(k.renewable_spilled_kwh)} kWh spilled` : ""}</div></div>
            <div className="kpi"><div className="k">Grid import</div><div className="v num">{nf0.format(k.grid_import_kwh)}<small>kWh</small></div><div className="d">{k.grid_dependency_pct.toFixed(1)}% of demand</div></div>
            <div className="kpi"><div className="k">Grid CO₂</div><div className="v num">{nf0.format(k.grid_co2_kg)}<small>kg</small></div><div className="d">₹{nf0.format(k.grid_cost_rs)} on the time-of-day tariff</div></div>
            <div className="kpi"><div className="k">{k.unserved_kwh > 0 ? "Unserved load" : "Load served"}</div>
              <div className="v num" style={{ color: k.unserved_kwh > 0 ? "var(--bad)" : "var(--good)" }}>
                {k.unserved_kwh > 0 ? <>{nf0.format(k.unserved_kwh)}<small>kWh</small></> : "100%"}</div>
              <div className="d">{k.unserved_kwh > 0 ? `${k.critical_load_coverage_pct.toFixed(1)}% of demand covered` : "every hour met"}</div></div>
          </div>

          {fallback && (
            <p className="alert err">
              The optimiser found {r.fallback_reason}, so this is the simple rule-based schedule, not a cost-optimal one.
            </p>
          )}
          {k.unserved_kwh > 0 && !fallback && (
            <p className="alert err">
              This day cannot be fully served: {nf0.format(k.unserved_kwh)} kWh is shed even under the best plan. That is the honest
              answer for a plant this size without the grid, not a solver failure.
            </p>
          )}

          <Panel title={`${LABELS[r.scenario] ?? r.scenario} · where each kilowatt comes from`} tick="var(--s2)"
            right={<span className="pill" style={{ borderColor: fallback ? "var(--warn)" : "var(--good)", color: fallback ? "var(--warn)" : "var(--good)" }}>{fallback ? "rule-based" : "HiGHS optimal"}</span>}>
            <GridChart dispatch={r.dispatch} load={r.forecast.map((f) => f.load_kw)} />
            <p className="note">
              The line is demand; the band below the axis is the battery charging. Battery level runs{" "}
              {Math.min(...r.dispatch.map((d) => d.soc_pct)).toFixed(0)}–{Math.max(...r.dispatch.map((d) => d.soc_pct)).toFixed(0)}% across the day.
            </p>
          </Panel>

          <div className="grid2">
            {cmp && (
              <Panel title="Every disturbance against the same day" tick="var(--ml)">
                <div className="scroll">
                  <table className="t"><thead><tr><th>Scenario</th><th className="r">Grid kWh</th><th className="r">CO₂ kg</th><th className="r">Unserved kWh</th><th className="r">Plan</th></tr></thead>
                    <tbody>{cmp.rows.map((x) => (
                      <tr key={x.scenario} className={(x.scenario === "normal" ? "" : x.scenario) === scenario ? "best" : ""}>
                        <td>{LABELS[x.scenario] ?? x.scenario}</td>
                        <td className="r num">{nf0.format(x.kpis.grid_import_kwh)}</td>
                        <td className="r num">{nf0.format(x.kpis.grid_co2_kg)}</td>
                        <td className="r num" style={{ color: x.kpis.unserved_kwh > 0 ? "var(--bad)" : undefined }}>{nf0.format(x.kpis.unserved_kwh)}</td>
                        <td className="r">{x.method === "optimised" ? "optimal" : "rule-based"}</td>
                      </tr>))}</tbody></table>
                </div>
                <p className="note">Only losing the grid leaves load unserved; the other four are absorbed by the battery and the tariff schedule.</p>
              </Panel>
            )}
            <div className="stack">
              {meta && (
                <Panel title="Forecast accuracy" tick="var(--s3)">
                  <div className="scroll">
                    <table className="t"><thead><tr><th>Signal</th><th className="r">MAE kW</th><th className="r">Naive baseline</th></tr></thead>
                      <tbody>{Object.entries(meta.accuracy).map(([n, m]) => (
                        <tr key={n}><td>{n.replace("_available_kw", "").replace("_kw", "")}</td>
                          <td className="r num" style={{ color: "var(--good)" }}>{m.MAE.toFixed(1)}</td>
                          <td className="r num">{m.baseline_MAE.toFixed(1)}</td></tr>))}</tbody></table>
                  </div>
                  <p className="note">Held out from training. The dataset is <b>synthetic demo data</b>, so these show the pipeline works — they are not field accuracy.</p>
                </Panel>
              )}
              {meta && (
                <Panel title="The plant" tick="var(--warn)">
                  <div className="scroll">
                    <table className="t"><tbody>
                      <tr><td>Solar</td><td className="r num">{meta.config.plant.solar_kw} kW</td></tr>
                      <tr><td>Wind</td><td className="r num">{meta.config.plant.wind_kw} kW</td></tr>
                      <tr><td>Battery</td><td className="r num">{meta.config.battery.capacity_kwh} kWh · {meta.config.battery.charge_kw} kW</td></tr>
                      <tr><td>Usable charge</td><td className="r num">{(meta.config.battery.soc_min * 100).toFixed(0)}–{(meta.config.battery.soc_max * 100).toFixed(0)}%</td></tr>
                      <tr><td>Grid limit</td><td className="r num">{meta.config.grid.import_kw} kW import</td></tr>
                    </tbody></table>
                  </div>
                </Panel>
              )}
            </div>
          </div>

          <Analyst sheet="Microgrid dispatch" figures={figures ?? ""}
            presets={["Why was this plan chosen?", "What is the biggest risk here?", "How could we cut the grid import?"]} />
        </>
      )}
      {loading && !r && <p className="note">Forecasting and solving the day…</p>}
    </>
  );
}
