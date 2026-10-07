"use client";
import { useGet } from "@/lib/hooks";
import type { Report, Stress, TargetReport } from "@/lib/types";
import { nf0, pct } from "@/lib/format";
import { PageHead, Panel } from "@/components/ui";

const f3 = (v: number | null | undefined) => (v == null ? "–" : v.toFixed(3));

function TargetCard({ name, color, t, synthetic }: { name: string; color: string; t: TargetReport; synthetic: boolean }) {
  const oot = t.out_of_time_2024plus;
  return (
    <Panel title={name} tick={color} right={<span className="pill ml">{t.best_model}</span>}>
      <div className="kpis" style={{ gridTemplateColumns: "repeat(2, minmax(0,1fr))" }}>
        <div className="kpi"><div className="k">Beats baseline by</div><div className="v num">{t.improvement_vs_baseline_rmse_pct.toFixed(0)}%</div><div className="d">95% CI {t.improvement_95ci_pct[0].toFixed(0)}–{t.improvement_95ci_pct[1].toFixed(0)}% · company bootstrap</div></div>
        <div className="kpi"><div className="k">Interval coverage</div><div className="v num">{pct(t.interval_coverage_test, 1)}</div><div className="d">target {pct(t.target_coverage)} · {t.interval_method} conformal</div></div>
      </div>
      <p className="note">Worst sector covers {pct(t.worst_sector_coverage)}; the median interval spans ×{t.median_interval_factor.toFixed(1)} from low to high.
        {oot && ` Out-of-time check (train to 2023, score 2024 on, unseen companies): error ${oot.model_rmse_log.toFixed(2)} vs ${oot.baseline_rmse_log.toFixed(2)} for the baseline.`}
        {synthetic && " Measured on synthetic data."}</p>
    </Panel>
  );
}

export default function Models() {
  const { data, error, loading } = useGet<Report>("/api/report");
  const { data: stress } = useGet<Stress>("/api/stress");
  const m = data?.metrics, synthetic = m?.data_source !== "BRSR";
  return (
    <>
      <PageHead eyebrow="Model report" title="How the models were tested">
        Four model families, tuned with company-grouped cross-validation, chosen on CV only, then scored once on companies they never saw.
      </PageHead>
      {error && <div className="alert err">{error}</div>}
      {loading && <div className="skeleton" style={{ height: 320 }} />}
      {data && !data.ready && <div className="alert err">No report found. Run <span className="mono">make train</span>.</div>}
      {m && data?.comparison && (
        <div className="stack fade">
          {synthetic && <div className="alert"><span aria-hidden>⚠</span>These models were trained on synthetic companies. The numbers show the pipeline works; they say nothing yet about real Indian companies.</div>}
          <div className="grid2 even">
            <TargetCard name="Scope 1" color="var(--s1)" t={m.s1} synthetic={synthetic} />
            <TargetCard name="Scope 2" color="var(--s2)" t={m.s2} synthetic={synthetic} />
          </div>
          <Panel title="Model comparison · RMSE on log tCO₂e (lower is better)" tick="var(--ml)">
            <div className="scroll">
              <table className="t">
                <thead><tr><th>Target</th><th>Model</th><th className="r">Train</th><th className="r">CV</th><th className="r">Test</th><th className="r">Test ÷ train</th><th className="r">R²</th><th className="r">Median error</th><th>Flag</th></tr></thead>
                <tbody>
                  {data.comparison.map((r, i) => {
                    const best = (r.target === "s1" ? m.s1 : m.s2).best_model === r.model;
                    return (
                      <tr key={i} className={best ? "best" : ""}>
                        <td className="mono">{r.target.toUpperCase()}</td><td>{r.model.replaceAll("_", " ")}{best && <span className="pill ml" style={{ marginLeft: 8 }}>chosen</span>}</td>
                        <td className="r">{f3(r.train_rmse_log)}</td><td className="r">{f3(r.cv_rmse_log)}</td><td className="r"><b>{f3(r.rmse_log)}</b></td>
                        <td className="r">{r.overfit_ratio_test_over_train != null ? r.overfit_ratio_test_over_train.toFixed(2) : "–"}</td>
                        <td className="r">{r.r2_log.toFixed(3)}</td><td className="r">{r.median_pct_error.toFixed(0)}%</td>
                        <td>{r.overfit_flag ? <span className="pill warn">overfit</span> : r.model === "sector_median_baseline" ? <span className="pill">baseline</span> : ""}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="note">Overfit is flagged when test error exceeds 1.5× train error. The model is chosen on cross-validation inside the training companies; the test set is read once.</p>
          </Panel>
          {stress?.tests && (
            <Panel title="Stress tests on a world the models never saw" tick="var(--ml)" right={<span>{stress.passed}/{stress.total} passed · {nf0.format(stress.n_fresh_companies ?? 0)} fresh companies</span>}>
              <div className="scroll"><table className="t wrap">
                <thead><tr><th>Group</th><th>Test</th><th className="r">Value</th><th>Result</th><th>Detail</th></tr></thead>
                <tbody>{stress.tests.map((t, i) => (
                  <tr key={i}><td className="mono" style={{ fontSize: 11 }}>{t.group}</td><td>{t.name}</td><td className="r">{t.value.toFixed(3)}</td>
                    <td><span className={`mark ${t.passed === null ? "info" : t.passed ? "pass" : "fail"}`}>{t.passed === null ? "LIMIT" : t.passed ? "PASS" : "FAIL"}</span></td><td className="note">{t.detail}</td></tr>
                ))}</tbody>
              </table></div>
              <p className="note"><b>Limit</b> rows are situations the models are not built for, shown on purpose: if every company&apos;s emissions shift by +50%, or one sector doubles, the intervals stop covering and the model cannot tell. Clean unit errors out of the training data, and retrain when the world changes.</p>
            </Panel>
          )}
          <Panel title="Diagnostics" tick="var(--ml)">
            <p className="note">Left: predicted vs actual with the 90% band, on held-out companies. Right: SHAP shows what drives the best tree model ({m.s1.best_model === "ridge" ? "a tree model is used because ridge is linear, so its effects are just its coefficients" : m.s1.best_model}).</p>
            <div className="plots">
              {data.plots?.map((p) => (
                // eslint-disable-next-line @next/next/no-img-element
                <figure key={p}><img src={`/api/plots/${p}`} alt={p.replace(".png", "").replaceAll("_", " ")} loading="lazy" /><figcaption>{p.replace(".png", "").replaceAll("_", " ")}</figcaption></figure>
              ))}
            </div>
          </Panel>
        </div>
      )}
    </>
  );
}
