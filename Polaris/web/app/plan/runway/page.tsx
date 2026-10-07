"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { usePost } from "@/lib/hooks";
import type { RunwayResult } from "@/lib/types";
import { fmtT, nf0, pct } from "@/lib/format";
import { ErrorNote, Num, PageHead, Panel, Slider, Term } from "@/components/ui";
import { DelayChart, RunwayRuler } from "@/components/charts";

/** The Polaris question: the tank says 20 days, the delivery is on day 25. Does the fuel last, and what closes the gap? */
export default function Runway() {
  const [stock, setStock] = useState(20000);
  const [daily, setDaily] = useState(1000);
  const [day, setDay] = useState(25);
  const [cv, setCv] = useState(0.15);
  const [saving, setSaving] = useState(0.268);
  const [delay, setDelay] = useState(0);
  const body = useMemo(() => ({ stock_l: stock, daily_l: daily, delivery_day: day, cv, saving_frac: saving, delay_days: delay }), [stock, daily, day, cv, saving, delay]);
  const { data: r, error, loading } = usePost<RunwayResult>("/api/runway", body, { enabled: stock >= 1 && daily >= 0.1 && day >= 1 });
  const when = day + delay;

  const verdict = r && (r.p_ok_with_delay.with_saving >= r.target_p ? "good" : r.p_ok_with_delay.with_saving >= 0.5 ? "warn" : "bad");
  return (
    <>
      <PageHead eyebrow="Fuel runway" title="Will the diesel last until the boat comes?">
        The Polaris question. Daily use is not constant: cold spells persist. This sheet runs 4,000 plausible fuel histories and tells you the <Term tip="Share of simulated histories in which the tank is still above empty on delivery day.">chance the fuel lasts</Term>, with and without a saving, and what happens if the delivery slips.
      </PageHead>
      <div className="grid2">
        <div className="stack fade">
          <Panel title="Station" tick="var(--s1)">
            <div className="fields">
              <Num label="Usable fuel on hand" unit="litres" value={stock} onChange={setStock} max={1e8} />
              <Num label="Typical daily use" unit="L / day" value={daily} onChange={setDaily} max={1e7} />
              <Num label="Next delivery in" unit="days" value={day} onChange={(v) => setDay(Math.max(1, Math.round(v)))} max={365} />
              <div className="field"><label>Nominal runway<em>stock ÷ daily</em></label><div className="inp"><span style={{ padding: "8px 4px", fontWeight: 600 }} className="num">{daily ? (stock / daily).toFixed(1) : "–"} days</span></div></div>
            </div>
            <Slider label="Day-to-day variability" value={cv} min={0} max={0.5} step={0.01} onChange={setCv} format={(v) => pct(v)} />
          </Panel>
          <Panel title="Actions" tick="var(--s3)">
            <Slider label="Polaris saving (load shifted to renewable hours)" value={saving} min={0} max={0.6} step={0.005} onChange={setSaving} format={(v) => pct(v, 1)} />
            <p className="note" style={{ marginTop: -6 }}>26.8% is the proposal&apos;s illustrative figure. Replace it with the simulated saving when the Polaris dispatch run is linked.</p>
            <Slider label="Delivery arrives late by" value={delay} min={0} max={14} step={1} onChange={setDelay} format={(v) => `${v} day${v === 1 ? "" : "s"}`} />
          </Panel>
          <p className="note">{r?.assumptions ?? "Illustrative stochastic model, not a weather forecast"}. The estimate beyond a week would need a real weather source.</p>
        </div>

        <div className={`stack sticky fade ${loading ? "busy" : ""}`} style={{ animationDelay: ".08s" }}>
          <ErrorNote message={error} />
          {r && (
            <>
              <section className="panel" style={{ background: "var(--surface)", border: "1px solid var(--ink)", borderTopWidth: 2 }}>
                <div className="hero">
                  <div className="eyebrow">Chance the fuel lasts to day {when}</div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
                    <div><div className="big" style={{ fontSize: "clamp(48px,6vw,76px)", color: "var(--muted)" }}>{nf0.format(r.p_ok_with_delay.baseline * 100)}<small>%</small></div><p className="sub" style={{ marginTop: 6 }}>as planned</p></div>
                    <div><div className="big" style={{ fontSize: "clamp(48px,6vw,76px)", color: verdict === "good" ? "var(--good)" : verdict === "warn" ? "var(--warn)" : "var(--bad)" }}>{nf0.format(r.p_ok_with_delay.with_saving * 100)}<small>%</small></div><p className="sub" style={{ marginTop: 6 }}>with {pct(saving, 1)} saving</p></div>
                  </div>
                  <p className="sub" style={{ color: "var(--ink2)" }}>
                    {r.saving_needed_for_target === null ? <>Even a 90% saving does not reach {pct(r.target_p)} confidence by day {when}. Order earlier or cut load by other means.</>
                      : r.saving_needed_for_target === 0 ? <>You already clear {pct(r.target_p)} confidence by day {when} with no saving.</>
                      : <>To reach <b>{pct(r.target_p)} confidence</b> by day {when} you need a saving of at least <b className="num">{pct(r.saving_needed_for_target, 1)}</b>.</>}
                  </p>
                </div>
              </section>
              <Panel title="Days of fuel" tick="var(--ink)" right={<span>P10–P90 band · tick = median</span>}>
                <RunwayRuler base={r.runway_days.baseline} saved={r.runway_days.with_saving} delivery={day} delay={delay} nominal={r.nominal_runway_days} />
                <p className="note">The dotted line is the nominal runway ({r.nominal_runway_days.toFixed(1)} days). Real fuel histories run ahead of or behind it: the median runs out on day <b>{r.runway_days.baseline[1]}</b>, a bad case (P10) on day <b>{r.runway_days.baseline[0]}</b>.</p>
              </Panel>
            </>
          )}
        </div>
      </div>
      {r && (
        <div className={`stack fade ${loading ? "busy" : ""}`} style={{ marginTop: 28 }}>
          <div className="kpis">
            <div className="kpi"><div className="k">Gap today</div><div className="v num">{r.gap_days_median > 0 ? `${r.gap_days_median.toFixed(0)}` : "0"}<small>days short</small></div><div className="d">median runway vs delivery day {day}</div></div>
            <div className="kpi"><div className="k">Diesel to delivery</div><div className="v num">{nf0.format(r.diesel_to_delivery_l.with_saving)}<small>L</small></div><div className="d">vs {nf0.format(r.diesel_to_delivery_l.baseline)} L as planned</div></div>
            <div className="kpi"><div className="k">CO₂ to delivery</div><div className="v num">{fmtT(r.co2_to_delivery_t.with_saving)}<small>t</small></div><div className="d">{fmtT(r.co2_to_delivery_t.baseline - r.co2_to_delivery_t.with_saving)} t less than planned</div></div>
            <div className="kpi"><div className="k">Saving needed</div><div className="v num">{r.saving_needed_for_target == null ? "n/a" : pct(r.saving_needed_for_target, 1)}</div><div className="d">for {pct(r.target_p)} confidence</div></div>
          </div>
          <Panel title="If the delivery slips" tick="var(--s1)" right={<span>chance the fuel still lasts</span>}>
            <DelayChart delays={r.delay_curve.delays} base={r.delay_curve.baseline} saved={r.delay_curve.with_saving} target={r.target_p} mark={delay} />
            <p className="note">Each day of delay is one more day of burning. The saving buys time: compare where the two lines cross the dashed target. <Link href="/plan/abatement" className="btn ghost" style={{ padding: 0 }}>See the same saving as an abatement lever →</Link></p>
          </Panel>
        </div>
      )}
    </>
  );
}
