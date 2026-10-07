"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useGet, usePost } from "@/lib/hooks";
import { useStore } from "@/lib/store";
import type { DispatchKey, DispatchSummary, DispatchWeek, WeekSeries } from "@/lib/types";
import { fmtT, nf0, pct } from "@/lib/format";
import { DispatchChart, MonthlyBars, StressChart } from "@/components/charts";
import { ErrorNote, PageHead, Panel, Term } from "@/components/ui";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const NAMES: Record<DispatchKey, string> = { A: "A · Rule-based", B: "B · Optimizer, simple forecast", C: "C · Optimizer, trained forecast" };
const COLORS: Record<DispatchKey, string> = { A: "var(--muted)", B: "var(--ink2)", C: "var(--s3)" };
const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);
const weekStats = (w: WeekSeries) => ({ fuel: sum(w.fuel_l), gen: sum(w.gen), re: sum(w.pv_used) + sum(w.wind_used), demand: sum(w.demand), unmet: sum(w.unmet) });

export default function Dispatch() {
  const { data, error } = useGet<DispatchSummary>("/api/dispatch/summary");
  const { dispatch, setDispatch } = useStore();
  const [key, setKey] = useState<"polar" | "community">("polar");
  const [month, setMonth] = useState(6);
  const [view, setView] = useState<DispatchKey>("C");
  const d = data?.profiles[key];
  const week = usePost<DispatchWeek>("/api/dispatch/week", { profile: key, month }, { debounce: 0, enabled: !!d });
  const A = d?.scenarios.A, C = d?.scenarios.C, B = d?.scenarios.B;
  const saving = A && C ? 1 - C.fuel_l / A.fuel_l : null;
  const stats = useMemo(() => (week.data ? (Object.fromEntries((["A", "B", "C"] as DispatchKey[]).map((k) => [k, weekStats(week.data![k])])) as Record<DispatchKey, ReturnType<typeof weekStats>>) : null), [week.data]);
  const st = d?.stress;
  const profiles = data?.profiles ? (Object.keys(data.profiles) as ("polar" | "community")[]) : [];

  return (
    <>
      <PageHead eyebrow="Dispatch planner" title="Which source should power each hour?">
        A station with solar, wind, a battery and a diesel generator is run three ways against the same real weather: by simple rules, by an <Term tip="Mixed-integer linear program: it chooses generator on/off, battery charge and discharge and load shifting for the next 168 hours so that fuel, starts and battery wear are as low as the physical limits allow.">optimizer</Term> fed simple forecasts, and by the optimizer fed trained seven-day forecasts. Scored on a year the models never saw.
      </PageHead>
      <ErrorNote message={error} />
      {data && !data.ready && <div className="alert err">The dispatch results are not generated yet. Run <span className="mono">python -m carbon.dispatch_eval</span> in the SCOPE folder.</div>}
      {d && A && B && C && (
        <div className="stack fade">
          <div style={{ display: "flex", flexWrap: "wrap", gap: "12px 22px", alignItems: "center" }}>
            <div className="seg2" role="group" aria-label="Station profile">
              {profiles.map((k) => <button key={k} aria-pressed={key === k} onClick={() => setKey(k)}>{k === "polar" ? "Polar research station" : "Himalayan community"}</button>)}
            </div>
            <span className="note">{d.profile.name}. Capacities are assumptions: {d.profile.pv_kwp} kWp solar, {d.profile.wind_kw} kW wind, {d.profile.battery_kwh} kWh battery, {d.profile.gen_kw} kW generator.</span>
          </div>

          <div className="kpis">
            <div className="kpi"><div className="k">Diesel, held-out year</div><div className="v num">{nf0.format(C.fuel_l)}<small>L</small></div><div className="d">{nf0.format(A.fuel_l)} L with rules · {nf0.format(B.fuel_l)} L optimizer + simple forecast</div></div>
            <div className="kpi"><div className="k">Saving by planning ahead</div><div className="v num" style={{ color: saving && saving > 0 ? "var(--good)" : "var(--ink)" }}>{saving != null ? pct(saving, 1) : "–"}</div><div className="d">{fmtT(A.co2_t - C.co2_t)} t CO₂ less per year</div></div>
            <div className="kpi"><div className="k">Renewable energy used</div><div className="v num">{C.renewable_utilisation != null ? pct(C.renewable_utilisation) : "–"}</div><div className="d">{A.renewable_utilisation != null ? `${pct(A.renewable_utilisation)} with rules; the optimizer curtails more but needs less diesel` : ""}</div></div>
            <div className="kpi"><div className="k">Load left unserved</div><div className="v num">{fmtT(C.unmet_kwh)}<small>kWh</small></div><div className="d">out of {nf0.format(C.demand_kwh)} kWh demand</div></div>
          </div>
          <div className="btns noprint">
            <button className="btn primary" disabled={saving == null} onClick={() => saving != null && setDispatch({ frac: Math.max(saving, 0), label: `${d.profile.name.split(" (")[0]}, ${pct(saving, 1)} computed by the dispatch planner` })}>
              Use {saving != null ? pct(saving, 1) : "this"} as the diesel saving in the abatement and runway sheets
            </button>
            {dispatch && <span className="note" style={{ alignSelf: "center" }}>Saved: {dispatch.label}. <Link href="/plan/abatement" className="btn ghost" style={{ padding: 0 }}>Open abatement →</Link></span>}
          </div>

          <Panel title="One week, hour by hour" tick="var(--s1)" right={<span>{MONTHS[month - 1]} 2025, first seven days</span>}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "10px 20px", alignItems: "center", justifyContent: "space-between" }}>
              <div className="field" style={{ minWidth: 170 }}><label htmlFor="mo">Week starting</label><div className="inp"><select id="mo" value={month} onChange={(e) => setMonth(Number(e.target.value))}>{MONTHS.map((m, i) => <option key={m} value={i + 1}>1 {m}</option>)}</select></div></div>
              <div className="seg2" role="group" aria-label="Show strategy">
                {(["A", "B", "C"] as DispatchKey[]).map((k) => <button key={k} aria-pressed={view === k} onClick={() => setView(k)}>{NAMES[k]}</button>)}
              </div>
            </div>
            <div className={week.loading ? "busy" : ""}>{week.data ? <DispatchChart w={week.data[view]} /> : <div className="skeleton" style={{ height: 360 }} />}</div>
            {stats && (
              <div className="scroll"><table className="t"><thead><tr><th>This week</th><th className="r">Diesel L</th><th className="r">Generator kWh</th><th className="r">Renewables used kWh</th><th className="r">Demand kWh</th><th className="r">Unserved kWh</th></tr></thead>
                <tbody>{(["A", "B", "C"] as DispatchKey[]).map((k) => <tr key={k} className={k === view ? "best" : ""}><td><b>{NAMES[k]}</b></td><td className="r">{nf0.format(stats[k].fuel)}</td><td className="r">{nf0.format(stats[k].gen)}</td><td className="r">{nf0.format(stats[k].re)}</td><td className="r">{nf0.format(stats[k].demand)}</td><td className="r">{stats[k].unmet.toFixed(1)}</td></tr>)}</tbody></table></div>
            )}
            <p className="note">Plans are made from forecasts issued at the start of each day and executed against what actually happened, so a wrong forecast costs fuel, just as it would on site. The generator follows forecast errors; the battery and flexible load absorb the rest.</p>
          </Panel>

          <Panel title="Month by month" tick="var(--s3)" right={<span>diesel litres, held-out year</span>}>
            <MonthlyBars series={(["A", "B", "C"] as DispatchKey[]).map((k) => ({ name: NAMES[k], color: COLORS[k], values: d.monthly[k].fuel_l }))} />
            <p className="note">The benefit is seasonal. Where weather already supplies most of the load, as in the polar winter on wind, there is little for an optimizer to improve; in shoulder seasons it shifts flexible load into the windy and sunny hours and runs the generator in fewer, fuller blocks.</p>
          </Panel>

          {st && (
            <Panel title="Resupply stress test" tick="var(--bad)" right={<span>{nf0.format(st.tank_l)} L tank · delivery on day {st.delivery_day}</span>}>
              <p className="note" style={{ marginTop: -4 }}>The proposal&apos;s question: the tank lasts about 20 days under rule-based operation ({nf0.format(st.rule_based_daily_l)} L a day) but the delivery comes on day {st.delivery_day}. Can planning ahead close the gap? <b>Survival</b> mode paces the diesel toward the delivery date and rations non-essential load first.</p>
              <StressChart tank={st.tank_l} delivery={st.delivery_day} runs={[
                { name: "Rule-based", color: "var(--muted)", dash: "7 5", data: st.scenarios["A"] },
                { name: "Economy", color: "var(--ink)", data: st.scenarios["C-economy"] },
                { name: "Survival", color: "var(--s3)", data: st.scenarios["C-survival"] }]} />
              <div className="scroll"><table className="t"><thead><tr><th>Until the delivery</th><th className="r">Essential load unserved</th><th className="r">First blackout of essential load</th><th className="r">Non-essential shed</th><th className="r">Flexible load moved</th><th className="r">Diesel left</th></tr></thead>
                <tbody>{([["Rule-based", "A"], ["Optimizer, economy", "C-economy"], ["Optimizer, survival", "C-survival"]] as const).map(([n, k]) => {
                  const r = st.scenarios[k]; return <tr key={k} className={k === "C-survival" ? "best" : ""}><td><b>{n}</b></td><td className="r">{nf0.format(r.essential_unmet_kwh)} kWh ({r.essential_unmet_pct}%)</td><td className="r">{r.first_essential_unmet_day ? `day ${r.first_essential_unmet_day}` : "none"}</td><td className="r">{nf0.format(r.shed_nonessential_kwh)} kWh</td><td className="r">{nf0.format(r.flex_shifted_kwh)} kWh</td><td className="r">{nf0.format(r.fuel_left_at_delivery_l)} L</td></tr>;
                })}</tbody></table></div>
              <p className="note">{st.scenarios["C-survival"].essential_unmet_kwh === 0 ? <>Dispatch alone cannot create diesel, but rationing buys the five days: with Survival mode essential load is served until the boat arrives, at the price of shedding {nf0.format(st.scenarios["C-survival"].shed_nonessential_kwh)} kWh of non-essential load.</> : <>Even with rationing, essential load is short by {nf0.format(st.scenarios["C-survival"].essential_unmet_kwh)} kWh before the delivery: the equipment and fuel cannot close this gap.</>} It leaves {nf0.format(st.scenarios["C-survival"].fuel_left_at_delivery_l)} L unused, a deliberate reserve in the pacing rule.</p>
            </Panel>
          )}

          <div className="grid2 even">
            <Panel title="How good are the forecasts?" tick="var(--ml)" right={<span>2025, never seen in training</span>}>
              <div className="scroll"><table className="t"><thead><tr><th>Quantity</th><th className="r">LightGBM MAE</th><th className="r">Same hour yesterday</th><th className="r">Persistence</th><th className="r">Skill</th></tr></thead>
                <tbody>{([["demand", "Demand (kW)"], ["solar_cf", "Solar (capacity factor)"], ["wind_cf", "Wind (capacity factor)"]] as const).map(([k, n]) => { const f = d.forecast[k]; const dg = k === "demand" ? 2 : 3; return <tr key={k}><td><b>{n}</b></td><td className="r">{f.lightgbm.mae.toFixed(dg)}</td><td className="r">{f.seasonal_naive_24h.mae.toFixed(dg)}</td><td className="r">{f.persistence.mae.toFixed(dg)}</td><td className="r"><b>{f.skill_vs_seasonal_naive_24h >= 0 ? "+" : ""}{(f.skill_vs_seasonal_naive_24h * 100).toFixed(0)}%</b></td></tr>; })}</tbody></table></div>
              <p className="note">Skill is the error reduction against same-hour-yesterday. Forecasts use only history, the calendar and sun geometry, so they are statistical, not weather-model forecasts. Wind is the hard one, especially beyond a day. The P20–P80 bands used in Survival mode cover {pct(d.forecast.demand.band_coverage_p20_p80)} of outcomes for demand, close to the 60% they should.</p>
            </Panel>
            <Panel title="Economy against Green" tick="var(--s2)" right={<span>seven-day samples</span>}>
              <div className="scroll"><table className="t"><thead><tr><th>Week</th><th className="r">Rules L</th><th className="r">Economy L</th><th className="r">Green L</th><th className="r">Starts (E / G)</th></tr></thead>
                <tbody>{Object.entries(d.mode_compare).map(([day, r]) => <tr key={day}><td className="mono">{day}</td><td className="r">{nf0.format(r.A.fuel_l)}</td><td className="r">{nf0.format(r.economy.fuel_l)}</td><td className="r">{nf0.format(r.green.fuel_l)}</td><td className="r">{r.economy.generator_starts} / {r.green.generator_starts}</td></tr>)}</tbody></table></div>
              <p className="note">Economy weighs fuel, generator starts and battery wear in rupees; Green minimises diesel CO₂ and tolerates more starts. They are close because diesel dominates both costs, as the proposal expected.</p>
            </Panel>
          </div>

          <Panel title="What is assumed" tick="var(--ink)">
            <ul className="ledger no"><li><span className="lk">!</span><span><b>Weather is real, demand is simulated.</b> {d.weather_source}. Demand: {d.demand_source}. Equipment sizes, generator curve, prices and the 40% rule-based battery reserve are stated assumptions.</span></li>
              <li><span className="lk">!</span><span><b>ERA5 is reanalysis, not a forecast feed.</b> The planner&apos;s forecasts are built from history; a real deployment needs a weather-model forecast, which would likely help most for wind.</span></li>
              <li><span className="lk">!</span><span><b>Results are for these two illustrative sites and one held-out year.</b> Training years {d.split.train}, calibration {d.split.calibration}, test {d.split.test}. Not a measured saving at any named station.</span></li></ul>
          </Panel>
        </div>
      )}
    </>
  );
}
