"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useGet, usePost } from "@/lib/hooks";
import { useStore } from "@/lib/store";
import type { Meta, PredictResult, Report } from "@/lib/types";
import { fmtSig, pct, nf0 } from "@/lib/format";
import { ErrorNote, Num, PageHead, Panel, Slider, Term } from "@/components/ui";
import { LogRange } from "@/components/charts";

export default function Estimate() {
  const { data: meta } = useGet<Meta>("/api/meta");
  const { data: rep } = useGet<Report>("/api/report");
  const { setMl } = useStore();
  const [sector, setSector] = useState("Cement");
  const [activity, setActivity] = useState("");
  const [turnover, setTurnover] = useState(2000);
  const [employees, setEmployees] = useState(0);
  const [renewable, setRenewable] = useState(0.1);
  const acts = useMemo(() => (meta?.activities ?? []).filter((a) => a.startsWith(sector + " /")), [meta, sector]);
  const act = acts.includes(activity) ? activity : acts[0] ?? "";
  const ready = !!meta?.models_ready && !!act;
  const body = useMemo(() => ({ sector, activity: act, turnover_cr: turnover, employees: employees || null, renewable_share: renewable, year: 2026 }), [sector, act, turnover, employees, renewable]);
  const { data, error, loading, snapshotKey, calculatedAt } = usePost<PredictResult>("/api/predict", body, { enabled: ready && turnover > 0 });
  const logT = Math.log10(Math.max(turnover, 1));
  const m = rep?.metrics;
  const synthetic = meta?.data_source !== "BRSR";

  const cards = data ? [
    { key: "s1" as const, name: "Scope 1", d: "direct fuel burning", color: "var(--s1)" },
    { key: "s2" as const, name: "Scope 2", d: "purchased electricity", color: "var(--s2)" },
  ] : [];

  return (
    <>
      <PageHead eyebrow="ML estimator" title="No meter data? Estimate it.">
        Describe a company by sector, size and renewable share. Models trained on company-year records return Scope 1 and 2 with a calibrated 90% <Term tip="A prediction interval built from the model's own past errors on companies it had not seen, so about 90 of every 100 true values land inside.">conformal interval</Term>. Scope 3 stays spend-based.
      </PageHead>
      {!meta?.models_ready && meta && <div className="alert err">Models are not trained yet. Run <span className="mono">make train</span> in the SCOPE folder.</div>}
      <div className="grid2">
        <div className="stack fade">
          <Panel title="Company profile" tick="var(--ml)">
            <div className="field"><label htmlFor="sector">Sector</label>
              <div className="inp"><select id="sector" value={sector} onChange={(e) => setSector(e.target.value)}>{meta?.sectors?.map((s) => <option key={s}>{s}</option>)}</select></div></div>
            <div className="field"><label htmlFor="act">Activity type</label>
              <div className="inp"><select id="act" value={act} onChange={(e) => setActivity(e.target.value)}>{acts.map((a) => <option key={a}>{a}</option>)}</select></div></div>
            <div className="field">
              <label htmlFor="turn">Annual turnover<span className="rowval">₹ {nf0.format(turnover)} crore</span></label>
              <input id="turn" className="range" type="range" min={0} max={6} step={0.02} value={logT} onChange={(e) => setTurnover(Math.round(Math.pow(10, Number(e.target.value))))} aria-valuetext={`${nf0.format(turnover)} crore rupees`} />
              <div className="lab" style={{ fontSize: 11, color: "var(--faint)", fontFamily: "var(--font-mono)" }}><span>₹1 Cr</span><span>₹10 lakh Cr</span></div>
            </div>
            <div className="fields">
              <Num label="Turnover (exact)" unit="₹ crore" value={turnover} onChange={setTurnover} />
              <Num label="Employees (optional)" unit="people" value={employees} onChange={setEmployees} />
            </div>
            <Slider label="Renewable electricity share" value={renewable} min={0} max={0.95} step={0.01} onChange={setRenewable} format={(v) => pct(v)} />
          </Panel>
          {m && (
            <Panel title="How far to trust it" tick="var(--ml)" right={synthetic ? <span className="pill warn">synthetic data</span> : <span className="pill good">BRSR</span>}>
              <p className="note">On companies the model never saw, the Scope 1 model is <b>{m.s1.improvement_vs_baseline_rmse_pct.toFixed(0)}%</b> closer than the usual sector-median shortcut (95% CI {m.s1.improvement_95ci_pct[0].toFixed(0)}–{m.s1.improvement_95ci_pct[1].toFixed(0)}%), and the 90% interval covered <b>{pct(m.s1.interval_coverage_test)}</b> of true values.
                {synthetic && " These figures come from generated data, so they test the pipeline, not real-world accuracy."}</p>
              <Link href="/evidence/carbon" className="btn" style={{ alignSelf: "flex-start" }}>Open model report →</Link>
            </Panel>
          )}
        </div>
        <div className="stack sticky fade" style={{ animationDelay: ".08s" }}>
          <ErrorNote message={turnover <= 0 ? "Turnover must be greater than zero." : error} />
          {data?.warnings.map((w) => <div className="alert" key={w} role="alert"><span aria-hidden>⚠</span>{w}</div>)}
          {cards.map((c) => (
            <section key={c.key} className={`panel ${loading ? "busy" : ""}`}>
              <div className="panel-h"><span className="tick"><i style={{ background: c.color }} />{c.name} · {c.d}</span><span className="pill ml">{data![c.key].model}</span></div>
              <div className="panel-b">
                <div className="big" style={{ fontSize: "clamp(44px,6vw,68px)", color: "var(--ink)" }}>{fmtSig(data![c.key].point)}<small>tCO₂e / yr</small></div>
                <LogRange lo={data![c.key].lo} point={data![c.key].point} hi={data![c.key].hi} color={c.color} />
                <p className="sub">90% interval <b className="num" style={{ color: "var(--ink)" }}>{fmtSig(data![c.key].lo, 2)}</b> to <b className="num" style={{ color: "var(--ink)" }}>{fmtSig(data![c.key].hi, 2)}</b> t · log scale · rounded</p>
              </div>
            </section>
          ))}
          {data && !loading && !error && (
            <div className="btns">
              <Link href="/plan/abatement" className="btn primary" onClick={() => setMl({ s1_t: data.s1.point, s2_t: data.s2.point, label: `${sector}, ₹${nf0.format(turnover)} Cr`, inputs: structuredClone(body), fingerprint: snapshotKey, calculatedAt })}>Plan abatement from this estimate →</Link>
            </div>
          )}
          {!data && !error && ready && <div className="skeleton" style={{ height: 260 }} />}
        </div>
      </div>
    </>
  );
}
