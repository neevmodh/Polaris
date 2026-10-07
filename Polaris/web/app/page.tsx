"use client";
import Link from "next/link";
import { useGet, usePost } from "@/lib/hooks";
import { SECTIONS, SHEETS, TOTAL_SHEETS } from "@/lib/sheets";
import type { CalcResult, RunwayResult, Stress } from "@/lib/types";
import type { SatAnalysis, SatMeta } from "@/lib/sat";
import { EXAMPLE } from "@/lib/store";
import { toBody } from "@/lib/export";
import { fmtT, nf0 } from "@/lib/format";
import { StarMark } from "@/components/Shell";

const RUNWAY = { stock_l: 20000, daily_l: 1000, delivery_day: 25, saving_frac: 0.268 };

function Reading({ href, k, value, unit, note, color }: { href: string; k: string; value?: string; unit: string; note: string; color: string }) {
  return (
    <Link href={href} className="reading">
      <span className="rk"><i style={{ background: color }} />{k}</span>
      <span className="rv num">{value ?? <span className="skeleton" style={{ display: "inline-block", width: 90, height: 40 }} />}</span>
      <span className="ru">{unit}</span><span className="rn">{note}</span>
    </Link>
  );
}

export default function Home() {
  const calc = usePost<CalcResult>("/api/calc", toBody(EXAMPLE), { debounce: 0 });
  const run = usePost<RunwayResult>("/api/runway", RUNWAY, { debounce: 0 });
  const forest = usePost<SatAnalysis>("/api/sat/analyze", { kind: "forest", case: "forest", layer: "alerts" }, { debounce: 0 });
  const lake = usePost<SatAnalysis>("/api/sat/analyze", { kind: "lake", case: "lake", water: "Pretrained U-Net", layer: "algae_change" }, { debounce: 0 });
  const { data: stress } = useGet<Stress>("/api/stress");
  const { data: sat } = useGet<SatMeta>("/api/sat/meta");
  const rf = sat?.metrics;

  return (
    <>
      <header className="home-hero fade">
        <div>
          <div className="eyebrow">Greenovators 2026 · Track 3 · Net Zero AI Architecture</div>
          <h1 className="mega">Measure it.<br />See it.<br />Cut it.</h1>
          <p className="lede">Polaris is one workspace for a remote station: count its emissions with honest ranges, track the greenhouse gas already overhead, watch the land and water around it from orbit, then plan the cuts, the power schedule and the fuel that keep it running. Any sheet will explain itself in plain words.</p>
          <div className="btns" style={{ marginTop: 22 }}>
            <Link className="btn primary" href="/carbon">Open the calculator</Link>
            <Link className="btn" href="/earth/forest">Open the satellite view</Link>
          </div>
        </div>
        <div className="hero-star" aria-hidden><StarMark size={220} /></div>
      </header>

      <section className="readings fade" aria-label="Live readings from the prepared examples" style={{ animationDelay: ".06s" }}>
        <Reading href="/carbon" k="Carbon · example station" value={calc.data ? fmtT(calc.data.point.total) : undefined} unit="tCO₂e per year" note={calc.data ? `range ${fmtT(calc.data.range.total.p5)}–${fmtT(calc.data.range.total.p95)} t` : "84,000 L diesel, 500,000 kWh"} color="var(--s1)" />
        <Reading href="/earth/forest" k="Earth · Rondônia" value={forest.data?.summary.candidate_loss_area_ha != null ? nf0.format(forest.data.summary.candidate_loss_area_ha) : undefined} unit="hectares of candidate forest loss" note={forest.data ? `${forest.data.summary.alert_regions} regions to review, 2019 → 2024` : "Sentinel-2 pair"} color="var(--s3)" />
        <Reading href="/earth/lake" k="Earth · Loktak Lake" value={lake.data?.summary.common_water_ha != null ? nf0.format(lake.data.summary.common_water_ha) : undefined} unit="hectares of comparable open water" note={lake.data ? `${nf0.format(lake.data.summary.algae_proxy_increase_ha ?? 0)} ha with an algae-proxy rise` : "U-Net water mask"} color="var(--s2)" />
        <Reading href="/plan/runway" k="Plan · fuel runway" value={run.data ? `${nf0.format(run.data.p_ok_at_delivery.with_saving * 100)}%` : undefined} unit="chance the diesel lasts to day 25" note={run.data ? `${nf0.format(run.data.p_ok_at_delivery.baseline * 100)}% without the 26.8% saving` : "20-day tank, day-25 delivery"} color="var(--ml)" />
      </section>
      <p className="note" style={{ marginTop: 8 }}>Each reading is computed live by the same engines the sheets use. The carbon and runway inputs are an illustrative example, the satellite scenes are real.</p>

      <section className="fade" style={{ marginTop: 44 }}>
        <h2 className="h2">Five sections, {TOTAL_SHEETS} numbered sheets</h2>
        <div className="quad">
          {SECTIONS.map((s) => (
            <div key={s.id} className="quad-c">
              <div className="verb">{s.verb}</div>
              <h3><Link href={s.href}>{s.label}</Link></h3>
              <p className="note">{s.blurb}</p>
              <ul>{SHEETS.filter((x) => x.section === s.id).map((x) => <li key={x.href}><Link href={x.href}><span className="k">{x.num}</span>{x.label}</Link></li>)}</ul>
            </div>
          ))}
        </div>
      </section>

      <section className="fade" style={{ marginTop: 44 }}>
        <h2 className="h2">How the pieces fit</h2>
        <div className="frame" style={{ border: "1px solid var(--line-strong)", background: "var(--surface)", padding: 14, overflowX: "auto" }}>
          <svg viewBox="0 0 1080 250" role="img" aria-label="Earth observation finds land and water change, carbon accounting turns activity into tonnes, and planning chooses the cuts. Air sits alongside: it measures what the atmosphere already holds and is never added to the ledger. The link from land change to tonnes is indicative, not built." className="chart flow" style={{ minWidth: 760 }}>
            <defs><marker id="hm" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="currentColor" /></marker></defs>
            <rect className="box" x="10" y="35" width="270" height="120" style={{ stroke: "var(--s3)" }} /><text className="t1" x="26" y="66">Earth</text><text x="26" y="92">Sentinel-2 scenes, two dates:</text><text x="26" y="112">forest loss and water change,</text><text x="26" y="132">in hectares, flagged for review</text>
            <rect className="box" x="405" y="35" width="270" height="120" style={{ stroke: "var(--s1)" }} /><text className="t1" x="421" y="66">Carbon</text><text x="421" y="92">fuel, power and spend become</text><text x="421" y="112">Scope 1, 2, 3 tonnes with ranges,</text><text x="421" y="132">plus an ML gap-filler</text>
            <rect className="box" x="800" y="35" width="270" height="120" style={{ stroke: "var(--ml)" }} /><text className="t1" x="816" y="66">Plan</text><text x="816" y="92">abatement levers by rupees per</text><text x="816" y="112">tonne, a 2050 pathway, and the</text><text x="816" y="132">fuel runway</text>
            <line x1="280" y1="95" x2="405" y2="95" stroke="currentColor" strokeWidth="2" strokeDasharray="6 6" markerEnd="url(#hm)" />
            <text className="lb lw" x="342" y="82" textAnchor="middle">indicative</text><text className="sm" x="342" y="118" textAnchor="middle">ha × carbon density</text>
            <line x1="675" y1="95" x2="800" y2="95" stroke="currentColor" strokeWidth="2" markerEnd="url(#hm)" />
            <text className="lb" x="737" y="82" textAnchor="middle">built</text><text className="sm" x="737" y="118" textAnchor="middle">baseline</text>
            <rect className="box" x="405" y="180" width="270" height="56" style={{ stroke: "var(--s2)" }} /><text className="t1" x="421" y="206">Air</text><text x="421" y="226">what the atmosphere already holds</text>
            <text className="sm" x="690" y="212">measured beside the ledger, never added to it</text>
          </svg>
        </div>
        <p className="note" style={{ marginTop: 8 }}>Carbon feeds planning today. Air sits apart on purpose: a concentration over a city is not an emission by that city, so it is never added to a footprint. The dashed link is indicative: the Forest sheet turns candidate loss into tonnes of CO₂ with a carbon density you set, shown separately and never added to a footprint, because no biomass map is used and the loss is unverified.</p>
      </section>

      <section className="fade" style={{ marginTop: 44 }}>
        <h2 className="h2">Evidence at a glance</h2>
        <div className="kpis">
          <div className="kpi"><div className="k">Carbon stress tests</div><div className="v num">{stress?.total ? `${stress.passed}/${stress.total}` : "…"}</div><div className="d">on 3,000 unseen synthetic companies</div></div>
          <div className="kpi"><div className="k">Forest F1, held-out strip</div><div className="v num">{rf ? rf.rf.f1.toFixed(3) : "…"}</div><div className="d">{rf ? `vs ${rf.ndvi_baseline.f1.toFixed(3)} for the NDVI rule` : ""}</div></div>
          <div className="kpi"><div className="k">Forest holdout</div><div className="v num">{rf ? nf0.format(rf.holdout_samples) : "…"}<small>px</small></div><div className="d">same scene pair, not another place</div></div>
          <div className="kpi"><div className="k">Honest status</div><div className="v" style={{ fontSize: 20, lineHeight: 1.25 }}>ML on synthetic data</div><div className="d">imagery real, BRSR data not yet used</div></div>
        </div>
        <p className="note" style={{ marginTop: 8 }}><Link className="btn ghost" style={{ padding: 0 }} href="/evidence/method">Read what each number does and does not support →</Link></p>
      </section>

      <section className="fade" style={{ marginTop: 44 }}>
        <h2 className="h2">Sheet index</h2>
        <div className="scroll"><table className="t wrap"><thead><tr><th>No.</th><th>Sheet</th><th>The question it answers</th></tr></thead>
          <tbody>{SHEETS.filter((s) => s.section !== "home").map((s) => <tr key={s.href}><td className="mono">{s.num}</td><td><Link href={s.href}><b>{s.label}</b></Link></td><td>{s.asks}</td></tr>)}</tbody></table></div>
      </section>
    </>
  );
}
