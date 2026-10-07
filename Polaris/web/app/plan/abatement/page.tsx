"use client";
import { useMemo, useState } from "react";
import { usePost } from "@/lib/hooks";
import { useStore } from "@/lib/store";
import type { AbateResult, CalcResult } from "@/lib/types";
import { fmtT, inr, inrShort, pct, nf0 } from "@/lib/format";
import { ErrorNote, Num, PageHead, Panel, Slider, Term } from "@/components/ui";
import { MaccChart, PathwayChart } from "@/components/charts";

export default function Abatement() {
  const { inputs, ml } = useStore();
  const [source, setSource] = useState<"calc" | "ml">("calc");
  const [saved, setSaved] = useState(0.268);
  const [price, setPrice] = useState(80);
  const [solar, setSolar] = useState(150000);
  const [ppa, setPpa] = useState(0.2);
  const [supplier, setSupplier] = useState(0.1);
  const useMl = source === "ml" && !!ml;

  const calcBody = useMemo(() => ({
    ...inputs.fuel, kwh: inputs.kwh, td_loss: inputs.td_loss,
    spend_inr: Object.fromEntries(Object.entries(inputs.spend_lakh).map(([k, v]) => [k, v * 1e5])),
  }), [inputs]);
  const calc = usePost<CalcResult>("/api/calc", calcBody);
  const s3 = calc.data?.point.scope3 ?? 0;

  const body = useMemo(() => ({
    ...(useMl ? { from_ml: { s1_t: ml!.s1_t, s2_t: ml!.s2_t } } : { diesel_l: inputs.fuel.diesel_l ?? 0, kwh: inputs.kwh }),
    td_loss: inputs.td_loss, s3_t: s3, diesel_saved_frac: saved, fuel_price: price, solar_kwh: solar, ppa_share: ppa, supplier_cut: supplier,
  }), [useMl, ml, inputs, s3, saved, price, solar, ppa, supplier]);
  const { data, error, loading } = usePost<AbateResult>("/api/abatement", body, { enabled: !calc.loading || calc.data != null });

  const b = data?.baseline;
  const baseTotal = b ? b.scope1 + b.scope2 + b.scope3 : 0;
  const sumAb = data?.macc.reduce((s, l) => s + l.abatement_t, 0) ?? 0;
  const avgCost = sumAb ? (data!.annual_net_cost_inr / sumAb) : 0;

  return (
    <>
      <PageHead eyebrow="Abatement" title="Which cuts pay for themselves?">
        Stack levers on your baseline. The <Term tip="Marginal abatement cost curve: every lever as a bar, width = tonnes it saves per year, height = rupees it costs per tonne, cheapest first. Bars below zero save money.">cost curve</Term> ranks them by rupees per tonne, and the pathway shows 2026–2050 with the spread from grid decarbonisation and lever performance.
      </PageHead>
      <div className="stack fade">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "center" }}>
          <div className="seg2" role="group" aria-label="Baseline source">
            <button aria-pressed={!useMl} onClick={() => setSource("calc")}>Calculator inputs</button>
            <button aria-pressed={useMl} disabled={!ml} onClick={() => setSource("ml")} title={ml ? ml.label : "Make an estimate on the ML page first"}>ML estimate{ml ? ` · ${ml.label}` : ""}</button>
          </div>
          {b && <span className="sub">Baseline <b className="num" style={{ color: "var(--ink)" }}>{fmtT(baseTotal)}</b> tCO₂e / yr · S1 {fmtT(b.scope1)} · S2 {fmtT(b.scope2)} · S3 {fmtT(b.scope3)}</span>}
          {useMl && <span className="note">ML baseline assumes all Scope 1 is diesel and all Scope 2 is grid power.</span>}
        </div>
        <ErrorNote message={error ?? calc.error} />

        <div className="kpis">
          <div className="kpi"><div className="k">Abated by 2030</div><div className="v num">{data ? fmtT(data.abated_2030_t) : "–"}<small>tCO₂e</small></div><div className="d">cumulative, median of runs</div></div>
          <div className="kpi"><div className="k">Abated by 2050</div><div className="v num">{data ? fmtT(data.abated_2050_t) : "–"}<small>tCO₂e</small></div><div className="d">{data && baseTotal ? `at full adoption, levers cut ${pct(Math.min(sumAb / baseTotal, 1))} of today's footprint` : ""}</div></div>
          <div className="kpi"><div className="k">Net annual cost</div><div className="v num" style={{ color: data && data.annual_net_cost_inr < 0 ? "var(--good)" : "var(--ink)" }}>{data ? inrShort(data.annual_net_cost_inr) : "–"}<small>/ yr</small></div><div className="d">{data && data.annual_net_cost_inr < 0 ? "levers save money overall" : "levers cost money overall"}</div></div>
          <div className="kpi"><div className="k">Average cost</div><div className="v num">{data ? inr(avgCost) : "–"}<small>/ t</small></div><div className="d">across all levers at full adoption</div></div>
        </div>

        <div className="grid2 lev">
          <Panel title="Levers" tick="var(--s3)">
            <Slider label="Polaris diesel saving" value={saved} min={0} max={0.6} step={0.005} onChange={setSaved} format={(v) => pct(v, 1)} />
            <p className="note" style={{ marginTop: -6 }}>26.8% is illustrative until the Polaris simulation is linked. It is typed in, not computed.</p>
            <Num label="Diesel price" unit="₹ / L" value={price} onChange={setPrice} max={500} />
            <Num label="New on-site solar" unit="kWh / yr" value={solar} onChange={setSolar} />
            <Slider label="Green PPA share of remaining grid kWh" value={ppa} min={0} max={1} step={0.01} onChange={setPpa} format={(v) => pct(v)} />
            <Slider label="Supplier engagement, cut of Scope 3" value={supplier} min={0} max={0.5} step={0.01} onChange={setSupplier} format={(v) => pct(v)} />
          </Panel>
          <div className={`stack ${loading ? "busy" : ""}`}>
            <Panel title="Marginal abatement cost curve" tick="var(--ink)" right={<span className="mono" style={{ fontSize: 11, textTransform: "none" }}>cheapest first · below zero saves money</span>}>
              <MaccChart levers={data?.macc ?? []} />
            </Panel>
          </div>
        </div>

        <Panel title="Pathway 2026–2050" tick="var(--ink)" right={<span className="mono" style={{ fontSize: 11, textTransform: "none" }}>1,500 Monte-Carlo runs</span>} className={loading ? "busy" : ""}>
          <PathwayChart rows={data?.pathway ?? []} />
          <p className="note">Spread comes from grid decarbonisation (1–4% a year, most likely 2.5%) and lever performance (70–115% of plan). Levers ramp in over four years. Costs and efficacies are assumptions you can change, not measured results.</p>
        </Panel>
        {data && b && <p className="note">Baseline in numbers: {nf0.format(b.diesel_l)} litres of diesel · {nf0.format(b.kwh)} kWh from the grid.</p>}
      </div>
    </>
  );
}
