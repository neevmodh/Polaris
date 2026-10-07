"use client";
import { useMemo } from "react";
import { useGet, usePost } from "@/lib/hooks";
import { EMPTY, EXAMPLE, useStore } from "@/lib/store";
import type { CalcResult, Meta } from "@/lib/types";
import { fmtT, pct } from "@/lib/format";
import { BigNum, ErrorNote, Num, NumInput, PageHead, Panel, Slider, Term } from "@/components/ui";
import { DriverBars, RangeBar } from "@/components/charts";
import { Analyst } from "@/components/Analyst";

const SCOPES = [
  { key: "scope1", n: "Scope 1", d: "fuel burned on site", color: "var(--s1)", cls: "a" },
  { key: "scope2", n: "Scope 2", d: "purchased electricity", color: "var(--s2)", cls: "b" },
  { key: "scope3", n: "Scope 3", d: "purchased goods & services", color: "var(--s3)", cls: "c" },
] as const;

export default function Calculator() {
  const { inputs, setInputs } = useStore();
  const { data: meta } = useGet<Meta>("/api/meta");
  const body = useMemo(() => ({
    ...inputs.fuel, kwh: inputs.kwh, td_loss: inputs.td_loss,
    spend_inr: Object.fromEntries(Object.entries(inputs.spend_lakh).map(([k, v]) => [k, v * 1e5])),
  }), [inputs]);
  const { data, error, loading } = usePost<CalcResult>("/api/calc", body);

  const groups = useMemo(() => {
    const m = new Map<string, NonNullable<Meta["scope3"]>>();
    meta?.scope3.forEach((c) => m.set(c.ghg, [...(m.get(c.ghg) ?? []), c]));
    return [...m.entries()];
  }, [meta]);
  const byLabel = useMemo(() => new Map((data?.scope3_breakdown ?? []).map((b) => [b.category, b.tco2e])), [data]);
  const setFuel = (k: string, v: number) => setInputs({ ...inputs, fuel: { ...inputs.fuel, [k]: v } });
  const empty = !data || data.point.total === 0;
  const maxRange = data ? Math.max(...SCOPES.map((s) => data.range[s.key].p95)) * 1.08 || 1 : 1;
  const topS3 = (data?.scope3_breakdown ?? []).slice(0, 6), topMax = topS3[0]?.tco2e ?? 1;

  return (
    <>
      <PageHead eyebrow="Calculator" title="What does this site emit in a year?">
        Enter what you burn, draw and buy. Every factor is shown with its source, and every result carries an uncertainty range from a 5,000-run <Term tip="Re-compute the footprint thousands of times, each time nudging every emission factor within its known error, then read off the spread.">Monte Carlo</Term>.
      </PageHead>
      <div className="grid2">
        <div className="stack fade">
          <Panel title="Scope 1 · Fuel burned" tick="var(--s1)" right={<span className="mono" style={{ fontSize: 11, textTransform: "none" }}>EPA / IPCC factors</span>}>
            <div className="fields">
              {meta?.fuels.map((f) => (
                <Num key={f.key} label={f.label.replace(/ \(.*\)/, "")} unit={f.label.match(/\((.*)\)/)?.[1] + " / yr"} hint={`${f.ef} kg/unit`} value={inputs.fuel[f.key] ?? 0} onChange={(v) => setFuel(f.key, v)} />
              ))}
            </div>
          </Panel>
          <Panel title="Scope 2 · Grid electricity" tick="var(--s2)" right={<span className="mono" style={{ fontSize: 11, textTransform: "none" }}>CEA v22 · {meta?.grid_ef ?? 0.675} kg/kWh</span>}>
            <Num label="Electricity drawn from the grid" unit="kWh / yr" value={inputs.kwh} onChange={(v) => setInputs({ ...inputs, kwh: v })} />
            <Slider label="Transmission & distribution loss gross-up" value={inputs.td_loss} min={0} max={0.25} step={0.01} onChange={(v) => setInputs({ ...inputs, td_loss: v })} format={(v) => (v === 0 ? "off (CEA figure)" : pct(v))} />
          </Panel>
          <Panel title="Scope 3 · Purchased spend" tick="var(--s3)" right={<span className="mono" style={{ fontSize: 11, textTransform: "none" }}>EPA USEEIO v1.3 · ₹ lakh / yr</span>}>
            {groups.map(([ghg, items], gi) => (
              <details className="group" key={ghg} open={gi < 2 || items.some((c) => (inputs.spend_lakh[c.key] ?? 0) > 0)}>
                <summary>{(() => { const m = ghg.match(/^(Cat \d+) (.*)$/); return m ? <span><span className="mono" style={{ color: "var(--faint)", marginRight: 8, fontSize: 12 }}>{m[1]}</span>{m[2]}</span> : ghg; })()}</summary>
                <div className="s3rows">
                  {items.map((c) => (
                    <div className="s3row" key={c.key}>
                      <label htmlFor={`sp-${c.key}`}>{c.label}</label>
                      <div className="inp"><NumInput id={`sp-${c.key}`} value={inputs.spend_lakh[c.key] ?? 0}
                        onChange={(v) => setInputs({ ...inputs, spend_lakh: { ...inputs.spend_lakh, [c.key]: v } })} /></div>
                      <span className="t num">{byLabel.has(c.label) ? `${fmtT(byLabel.get(c.label))} t` : ""}</span>
                    </div>
                  ))}
                </div>
              </details>
            ))}
            <p className="note">US supply-chain factors applied to Indian spend at ₹{meta?.usd_to_inr ?? 85}/USD: an approximation, so Scope 3 carries the widest range.</p>
          </Panel>
          <div className="btns">
            <button className="btn" onClick={() => setInputs(EXAMPLE)}>Load polar-station example</button>
            <button className="btn ghost" onClick={() => setInputs(EMPTY)}>Clear all</button>
          </div>
        </div>

        <div className="stack sticky fade" style={{ animationDelay: ".08s" }}>
          <ErrorNote message={error} />
          <section className={`panel ${loading ? "busy" : ""}`} aria-live="polite">
            <div className="hero">
              <div className="eyebrow" style={{ marginBottom: -4 }}>Total footprint</div>
              {empty && !loading ? (
                <p className="sub" style={{ padding: "24px 0" }}>Enter any fuel, electricity or spend to see the footprint.</p>
              ) : (
                <>
                  <div>
                    {data ? <BigNum value={data.point.total} unit="tCO₂e / year" /> : <div className="skeleton" style={{ height: 80, width: "70%" }} />}
                    {data && <p className="sub" style={{ marginTop: 10 }}>90% of Monte-Carlo runs fall between <b className="num" style={{ color: "var(--ink)" }}>{fmtT(data.range.total.p5)}</b> and <b className="num" style={{ color: "var(--ink)" }}>{fmtT(data.range.total.p95)}</b> t.</p>}
                  </div>
                  {data && (
                    <>
                      <div className="seg" role="img" aria-label="Share of total by scope">
                        {SCOPES.map((s) => {
                          const share = data.point[s.key] / (data.point.total || 1);
                          return <div key={s.key} className={s.cls} style={{ flexGrow: Math.max(data.point[s.key], 1e-9), flexBasis: 0 }}>{share > 0.09 ? pct(share) : ""}</div>;
                        })}
                      </div>
                      <div className="scoperows">
                        {SCOPES.map((s) => (
                          <div className="srow" key={s.key}>
                            <div className="nm"><i style={{ background: s.color }} /><div>{s.n}<small>{s.d}</small></div></div>
                            <RangeBar lo={data.range[s.key].p5} point={data.point[s.key]} hi={data.range[s.key].p95} max={maxRange} color={s.color} />
                            <div className="v">{fmtT(data.point[s.key])}<small>{fmtT(data.range[s.key].p5)}–{fmtT(data.range[s.key].p95)}</small></div>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </>
              )}
            </div>
          </section>
          {topS3.length > 0 && (
            <Panel title="Largest Scope 3 sources" tick="var(--s3)">
              <div className="bars">
                {topS3.map((b) => (
                  <div className="bar" key={b.category}><span className="l">{b.category}</span><span className="tr"><i style={{ width: `${(b.tco2e / topMax) * 100}%` }} /></span><span className="n">{fmtT(b.tco2e)} t</span></div>
                ))}
              </div>
            </Panel>
          )}
          {data && data.drivers.length > 0 && (
            <Panel title="What drives the uncertainty" tick="var(--ink)" right={<span>share of variance</span>}>
              <DriverBars rows={data.drivers} />
              <p className="note">Improve the data for the top line first: a better <b>{data.drivers[0].name.replace(" factor", "").toLowerCase()}</b> figure narrows the total range more than anything else.</p>
            </Panel>
          )}
          <p className="note">Whisker = <Term tip="The range that holds 90% of Monte-Carlo runs: 5% fall below it and 5% above it.">P5–P95</Term> after perturbing every emission factor (fuel ±5%, grid ±8%, spend ±50%). The tick is the point estimate.</p>
        </div>
      </div>
      {data && (
        <Analyst sheet="Carbon calculator" presets={["Explain this footprint", "Which number should I improve first?", "How certain is this total?"]}
          figures={[
            `Annual footprint for the entered site, in tonnes CO2e:`,
            `  Scope 1 (fuel burnt on site): ${fmtT(data.point.scope1)} t, 90% range ${fmtT(data.range.scope1.p5)} to ${fmtT(data.range.scope1.p95)}`,
            `  Scope 2 (purchased electricity): ${fmtT(data.point.scope2)} t, 90% range ${fmtT(data.range.scope2.p5)} to ${fmtT(data.range.scope2.p95)}`,
            `  Scope 3 (spend-based supply chain): ${fmtT(data.point.scope3)} t, 90% range ${fmtT(data.range.scope3.p5)} to ${fmtT(data.range.scope3.p95)}`,
            `  Total: ${fmtT(data.point.total)} t, 90% range ${fmtT(data.range.total.p5)} to ${fmtT(data.range.total.p95)}`,
            `Inputs: ${Object.entries(inputs.fuel).filter(([, v]) => v).map(([k, v]) => `${v} ${k}`).join(", ") || "no fuel"}, ${inputs.kwh} kWh electricity, transmission loss ${pct(inputs.td_loss)}`,
            data.scope3_breakdown.length ? `Scope 3 by category:\n${data.scope3_breakdown.map((b) => `  ${b.category} (${b.ghg_protocol}): Rs ${b.spend_inr} spent, ${fmtT(b.tco2e)} t`).join("\n")}` : `No Scope 3 spend was entered.`,
            `Uncertainty drivers, share of total variance:\n${data.drivers.map((d) => `  ${d.name}: ${pct(d.share)}`).join("\n")}`,
            `Grid factor ${meta?.grid_ef ?? "?"} kg CO2 per kWh (CEA v22). Factor uncertainty assumed: fuel +/-5%, grid +/-8%, spend +/-50%.`,
            `LIMIT: Scope 3 here is spend-based, an estimate from industry-average intensity per rupee. It is not a measurement of any supplier.`,
          ].join("\n")} />
      )}
    </>
  );
}
