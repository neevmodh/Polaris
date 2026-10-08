"use client";
import Link from "next/link";
import { useState } from "react";
import { useGet, usePost } from "@/lib/hooks";
import type { SatAnalysis, SatMeta } from "@/lib/sat";
import { nf0 } from "@/lib/format";
import { HBars, MetricBars } from "@/components/charts";
import { PageHead, Panel, Term } from "@/components/ui";

/** Reference values come from the Task 3 validation run, one set per water method. A figure is compared with the
 *  reference for the method that actually produced it, never with the other method's. */
const LAKE_REF: Record<string, { water: number; algae: number }> = {
  "Pretrained U-Net": { water: 703.17, algae: 319.41 },
  "Spectral open-water mask": { water: 1015.02, algae: 413.64 },
};
const FOREST_REF = { loss: 245.43, regions: 84, clear: 99.79 };
const close = (a: number | null | undefined, b: number) => a != null && Math.abs(a - b) < 0.006;

function Failure({ what, message, retry }: { what: string; message: string; retry: () => void }) {
  return <div className="alert err" role="alert"><span>{what} could not be computed: {message}</span><button type="button" className="btn ghost" onClick={retry}>Retry</button></div>;
}

export default function EarthEvidence() {
  const [tries, setTries] = useState({ forest: 0, lake: 0 });
  const { data: meta, error } = useGet<SatMeta>("/api/sat/meta");
  const forest = usePost<SatAnalysis>("/api/sat/analyze", { kind: "forest", case: "forest", retry: tries.forest }, { debounce: 0 });
  const lake = usePost<SatAnalysis>("/api/sat/analyze", { kind: "lake", case: "lake", water: "Pretrained U-Net", retry: tries.lake }, { debounce: 0 });
  const m = meta?.metrics, c = m?.rf.confusion_matrix, b = m?.ndvi_baseline.confusion_matrix;
  const fs = forest.data?.summary, ls = lake.data?.summary;
  const lakeMethod = lake.data?.method ?? null, lref = lakeMethod ? LAKE_REF[lakeMethod] : undefined;
  return (
    <>
      <PageHead eyebrow="Earth models" title="How the satellite models were tested">
        The forest model is a random forest trained on one Sentinel-2 pair and scored on a strip it never saw, against a plain NDVI rule. The lake analysis segments open water, with a pretrained U-Net where it is installed and a spectral mask where it is not.
      </PageHead>
      {error && <div className="alert err">{error}</div>}
      {m && c && b && (
        <div className="stack fade">
          <div className="grid2 even">
            <Panel title="Forest model against the NDVI rule" tick="var(--ml)">
              <MetricBars aName="Random forest" bName="NDVI baseline" groups={[
                { label: "precision", a: m.rf.precision, b: m.ndvi_baseline.precision }, { label: "recall", a: m.rf.recall, b: m.ndvi_baseline.recall }, { label: "F1", a: m.rf.f1, b: m.ndvi_baseline.f1 },
                { label: "IoU", a: m.rf.iou, b: m.ndvi_baseline.iou }, { label: "avg prec.", a: m.rf.average_precision, b: m.ndvi_baseline.average_precision }]} />
              <p className="note">The forest wins mainly on recall ({m.rf.recall.toFixed(3)} vs {m.ndvi_baseline.recall.toFixed(3)}) and average precision ({m.rf.average_precision.toFixed(3)} vs {m.ndvi_baseline.average_precision.toFixed(3)}). Precision is about equal.</p>
            </Panel>
            <Panel title="What the model learned from" tick="var(--ml)">
              <HBars rows={Object.entries(m.feature_importance).sort((x, y) => y[1] - x[1]).slice(0, 8).map(([name, value]) => ({ name, value }))} />
              <p className="note">Shortwave-infrared change leads: moisture and burn signals move before colour does. {m.features.length} features in all.</p>
            </Panel>
          </div>
          <Panel title="Counts on the held-out strip" tick="var(--ml)" right={<span>{nf0.format(m.holdout_samples)} pixels · {nf0.format(m.holdout_positive_samples)} reference loss</span>}>
            <div className="scroll"><table className="t"><thead><tr><th>Method</th><th className="r">Loss found</th><th className="r">Loss missed</th><th className="r">False alarms</th><th className="r">Correct no-loss</th></tr></thead>
              <tbody><tr className="best"><td><b>Random forest</b></td><td className="r">{c.tp}</td><td className="r">{c.fn}</td><td className="r">{c.fp}</td><td className="r">{c.tn}</td></tr>
                <tr><td>NDVI baseline</td><td className="r">{b.tp}</td><td className="r">{b.fn}</td><td className="r">{b.fp}</td><td className="r">{b.tn}</td></tr></tbody></table></div>
            <p className="note">Training used {nf0.format(m.trained_samples)} pixels from the western 70% ({nf0.format(m.training_positive_samples)} with loss); a six-column gap separates it from the eastern holdout. Labels: {m.reference}. Label years {m.label_interval}.</p>
          </Panel>
          <Panel title="Polaris recomputes the published case-study numbers" tick="var(--s3)">
            {forest.error && <Failure what="The forest case" message={forest.error} retry={() => setTries((t) => ({ ...t, forest: t.forest + 1 }))} />}
            {lake.error && <Failure what="The lake case" message={lake.error} retry={() => setTries((t) => ({ ...t, lake: t.lake + 1 }))} />}
            {lake.data?.fallback && <div className="alert" role="status"><span>{lake.data.fallback} The lake figures below are for the <b>{lakeMethod}</b> and are compared with that method&apos;s own reference.</span></div>}
            <div className="scroll"><table className="t"><thead><tr><th>Case</th><th>Quantity</th><th className="r">Polaris now</th><th className="r">Reference</th><th className="r">Check</th></tr></thead>
              <tbody>
                <tr><td>Rondônia</td><td>candidate forest loss</td><td className="r">{forest.loading ? "…" : fs?.candidate_loss_area_ha != null ? `${fs.candidate_loss_area_ha.toFixed(2)} ha in ${fs.alert_regions} regions` : "unavailable"}</td><td className="r">{FOREST_REF.loss} ha, {FOREST_REF.regions} regions</td><td className="r">{fs ? (close(fs.candidate_loss_area_ha, FOREST_REF.loss) && fs.alert_regions === FOREST_REF.regions ? "matches" : "differs") : "—"}</td></tr>
                <tr><td>Rondônia</td><td>clear paired coverage</td><td className="r">{forest.loading ? "…" : fs?.observed_pair_pct != null ? `${fs.observed_pair_pct}%` : "unavailable"}</td><td className="r">{FOREST_REF.clear}%</td><td className="r">{fs ? (close(fs.observed_pair_pct, FOREST_REF.clear) ? "matches" : "differs") : "—"}</td></tr>
                <tr><td>Loktak ({lakeMethod ?? "…"})</td><td>comparable open water</td><td className="r">{lake.loading ? "…" : ls?.common_water_ha != null ? `${ls.common_water_ha.toFixed(2)} ha` : "unavailable"}</td><td className="r">{lref ? `${lref.water} ha` : "—"}</td><td className="r">{ls && lref ? (close(ls.common_water_ha, lref.water) ? "matches" : "differs") : "—"}</td></tr>
                <tr><td>Loktak ({lakeMethod ?? "…"})</td><td>algae-proxy increase</td><td className="r">{lake.loading ? "…" : ls?.algae_proxy_increase_ha != null ? `${ls.algae_proxy_increase_ha.toFixed(2)} ha` : "unavailable"}</td><td className="r">{lref ? `${lref.algae} ha` : "—"}</td><td className="r">{ls && lref ? (close(ls.algae_proxy_increase_ha, lref.algae) ? "matches" : "differs") : "—"}</td></tr>
              </tbody></table></div>
            <p className="note">Each row is compared with the reference for the method that produced it. A row says &quot;matches&quot; only after its computation succeeds and agrees to two decimals; otherwise it says &quot;differs&quot; or shows nothing. An automated test asserts the same values, so a change that breaks the bridge is caught.</p>
          </Panel>
          <Panel title="Limits that travel with every satellite number" tick="var(--s1)">
            <ul className="ledger no">
              <li><span className="lk">✕</span><span><b>One region.</b> The holdout is the eastern strip of the same scene pair, so it is not a test in another country or year. There is no evidence of transfer.</span></li>
              <li><span className="lk">✕</span><span><b>Reference, not truth.</b> Hansen labels are annual satellite-derived loss; the endpoint years are excluded because annual labels cannot say whether loss came before an image.</span></li>
              <li><span className="lk">✕</span><span><b>Uncalibrated scores.</b> Forest scores are not probabilities. Map hectares use user-adjustable filters and a different pixel population from the holdout, so hectares must not be inferred from F1.</span></li>
              <li><span className="lk">✕</span><span><b>Proxies, not pollutants.</b> The lake NDCI and turbidity ratios are <Term tip="Unitless band ratios. They move with algae and sediment but are not chlorophyll or NTU values.">optical proxies</Term>. The U-Net segments water and makes no safety claim. No field samples were available.</span></li>
            </ul>
            <p className="note">Full detail: <Link href="/evidence/method" className="btn ghost" style={{ padding: 0 }}>Method, sources and licences →</Link></p>
          </Panel>
        </div>
      )}
    </>
  );
}
