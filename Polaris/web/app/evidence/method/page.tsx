"use client";
import { useGet } from "@/lib/hooks";
import type { Meta } from "@/lib/types";
import { PageHead, Panel } from "@/components/ui";

const Row = ({ a, b, c, d }: { a: string; b: React.ReactNode; c: React.ReactNode; d: React.ReactNode }) => <tr><td><b>{a}</b></td><td>{b}</td><td>{c}</td><td>{d}</td></tr>;

export default function Method() {
  const { data: meta } = useGet<Meta>("/api/meta");
  return (
    <>
      <PageHead eyebrow="Method" title="Sources, licences and limits">
        Where each number in Polaris comes from, under what licence, and what it can and cannot support.
      </PageHead>
      <div className="stack fade">
        <Panel title="Carbon: emission factors" tick="var(--s1)">
          <div className="scroll"><table className="t wrap"><thead><tr><th>Item</th><th>Value used</th><th>Source</th><th>Status</th></tr></thead><tbody>
            <Row a="Grid electricity" b={`${meta?.grid_ef ?? 0.675} kg CO₂ per kWh`} c="CEA CO₂ Baseline Database v22.0, FY2025-26 weighted average" d={<span className="pill good">real</span>} />
            <Row a="Diesel" b="2.70 kg CO₂ per litre" c="EPA 10.21 kg per US gallon ÷ 3.78541 L" d={<span className="pill good">real</span>} />
            <Row a="Petrol, LPG, natural gas" b="2.31 kg/L · 2.98 kg/kg · 2.02 kg/m³" c="IPCC / DESNZ approximate values" d={<span className="pill warn">verify</span>} />
            <Row a="Scope 3 spend factors" b={`${meta?.scope3.length ?? 14} categories, kg CO₂e per USD at ₹${meta?.usd_to_inr ?? 85}`} c="EPA USEEIO v1.3, 1,016 sectors, with margins" d={<span className="pill warn">US factors, Indian spend</span>} />
            <Row a="Uncertainty" b={`fuel ±${(meta?.sigmas.fuel ?? 0.05) * 100}% · grid ±${(meta?.sigmas.grid ?? 0.08) * 100}% · spend ±${(meta?.sigmas.spend ?? 0.5) * 100}%`} c="Lognormal Monte Carlo, 5,000 runs" d={<span className="pill">assumption</span>} />
          </tbody></table></div>
        </Panel>
        <Panel title="Datasets and models" tick="var(--s2)">
          <div className="scroll"><table className="t wrap"><thead><tr><th>Name</th><th>Used for</th><th>Licence</th><th>Notes</th></tr></thead><tbody>
            <Row a="Copernicus Sentinel-2 L2A" b="Both satellite analyses, via Element 84 Earth Search" c="Free and open Sentinel terms" d="Public HTTPS, no key. One scene per date, not a composite." />
            <Row a="Hansen GFC 2024 v1.12" b="Forest labels, eligibility support, holdout scoring" c="CC BY 4.0" d="Annual satellite-derived loss, not field truth." />
            <Row a="Lake U-Net (Iulia-plesu)" b="Optional water mask" c="Apache-2.0" d="124,243,147 bytes, SHA-256 verified. Segments water only." />
            <Row a="TerraVision · waterquality · Forest-CD" b="Workflow and algorithm references" c="MIT" d="Forest-CD is a research reference and is not run." />
            <Row a="BRSR Principle 6 (planned)" b="Real training data for the carbon ML" c="to confirm" d={<span className="pill warn">not used yet: ML trained on synthetic companies</span>} />
            <Row a="Pladifes CGEE" b="Method inspiration: several models, pick the best by error, uncertainty bands" c="no licence file" d="Method credited, no code copied. Please cite Nguyen et al. 2021, 2022 and Assael et al. 2023." />
          </tbody></table></div>
        </Panel>
        <div className="two">
          <Panel title="What Polaris supports" tick="var(--s3)">
            <ul className="ledger yes">
              <li><span className="lk">✓</span><span>Scope 1, 2 and 3 totals with stated factors and Monte-Carlo ranges, and which factor drives the uncertainty.</span></li>
              <li><span className="lk">✓</span><span>A fuel-runway probability and the saving needed, from a stated stochastic model.</span></li>
              <li><span className="lk">✓</span><span>Candidate forest loss and lake proxy change on real Sentinel-2 pairs, with clear-pixel areas, reproducible exports and human review notes.</span></li>
              <li><span className="lk">✓</span><span>A forest model that beats a plain rule on a held-out strip, and carbon-model intervals that cover about 90% on unseen synthetic companies.</span></li>
            </ul>
          </Panel>
          <Panel title="What it does not claim" tick="var(--s1)">
            <ul className="ledger no">
              <li><span className="lk">✕</span><span>Real-world accuracy of the carbon ML: it was trained on synthetic data.</span></li>
              <li><span className="lk">✕</span><span>Verified deforestation, or that the forest model works in other places or years.</span></li>
              <li><span className="lk">✕</span><span>Chlorophyll, turbidity in NTU, pathogens or water safety.</span></li>
              <li><span className="lk">✕</span><span>Carbon savings from the satellite results, a measured Polaris diesel saving (26.8% is a typed-in illustration), or any named-site deployment.</span></li>
            </ul>
          </Panel>
        </div>
        <Panel title="Reproducibility" tick="var(--ink)">
          <p className="note">The carbon engine (SCOPE) has 53 automated tests, 18 stress tests and 70 browser checks. The satellite bridge has 8 end-to-end tests that assert the published case-study numbers. Training is deterministic (fixed seeds), so metrics are identical on re-run. Nothing here replaces independent validation with field data.</p>
        </Panel>
      </div>
    </>
  );
}
