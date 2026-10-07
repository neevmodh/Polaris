"use client";
import { useMemo } from "react";
import { useGet, usePost } from "@/lib/hooks";
import { useStore } from "@/lib/store";
import { ledger, toBody } from "@/lib/export";
import type { CalcResult, Meta, Report } from "@/lib/types";
import { fmtT, nf0, pct } from "@/lib/format";
import { DriverBars } from "@/components/charts";
import { ErrorNote, PageHead, Panel } from "@/components/ui";

/** One A4 sheet an auditor can read without the app: result, inputs, every factor with its source, and the honest caveats. */
export default function ReportPage() {
  const { inputs } = useStore();
  const { data: meta } = useGet<Meta>("/api/meta");
  const { data: rep } = useGet<Report>("/api/report");
  const { data: r, error } = usePost<CalcResult>("/api/calc", useMemo(() => toBody(inputs), [inputs]));
  const rows = meta ? ledger(meta, inputs) : [];
  const synthetic = meta?.data_source !== "BRSR";
  return (
    <>
      <PageHead eyebrow="Printable report" title="Footprint statement">
        A one-sheet summary of the current inputs. Use your browser&apos;s print dialog to save it as a PDF.
      </PageHead>
      <div className="btns noprint" style={{ marginBottom: 22 }}>
        <button className="btn primary" onClick={() => window.print()}>Print or save as PDF</button>
      </div>
      <ErrorNote message={error} />
      {r && (
        <div className="stack">
          <div className="kpis">
            {(["scope1", "scope2", "scope3", "total"] as const).map((k, i) => (
              <div className="kpi" key={k}><div className="k">{["Scope 1", "Scope 2", "Scope 3", "Total"][i]}</div><div className="v num">{fmtT(r.point[k])}<small>tCO₂e / yr</small></div><div className="d">P5–P95 {fmtT(r.range[k].p5)}–{fmtT(r.range[k].p95)}</div></div>
            ))}
          </div>
          <Panel title="Inputs" tick="var(--ink)">
            <table className="t wrap"><tbody>
              {meta?.fuels.filter((f) => (inputs.fuel[f.key] ?? 0) > 0).map((f) => <tr key={f.key}><td>{f.label}</td><td className="r">{nf0.format(inputs.fuel[f.key])} per year</td></tr>)}
              {inputs.kwh > 0 && <tr><td>Grid electricity{inputs.td_loss ? ` (T&D gross-up ${pct(inputs.td_loss)})` : ""}</td><td className="r">{nf0.format(inputs.kwh)} kWh per year</td></tr>}
              {meta?.scope3.filter((c) => (inputs.spend_lakh[c.key] ?? 0) > 0).map((c) => <tr key={c.key}><td>{c.label} ({c.ghg})</td><td className="r">₹{nf0.format(inputs.spend_lakh[c.key])} lakh per year</td></tr>)}
            </tbody></table>
          </Panel>
          {r.drivers.length > 0 && <Panel title="Largest sources of uncertainty" tick="var(--ink)"><DriverBars rows={r.drivers} /></Panel>}
          <Panel title="Assumptions ledger" tick="var(--ink)">
            <div className="scroll"><table className="t wrap">
              <thead><tr><th>Item</th><th>Scope</th><th>Factor used</th><th>Source</th><th className="r">Error</th></tr></thead>
              <tbody>{rows.map((x, i) => <tr key={i}><td>{x.item}</td><td>{x.scope}</td><td>{x.value}</td><td>{x.source}</td><td className="r">{x.sigma}</td></tr>)}</tbody>
            </table></div>
          </Panel>
          <Panel title="Method and limits" tick="var(--ink)">
            <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6 }} className="note">
              <li>Scopes follow the GHG Protocol. Scope 2 is location-based using the CEA grid average; market-based accounting is not covered.</li>
              <li>Fuel factors count CO₂ only; methane and nitrous oxide from combustion are small and excluded.</li>
              <li>Scope 3 is spend-based with US EPA USEEIO factors applied to Indian rupees, so it carries the widest uncertainty (±50% per factor).</li>
              <li>Ranges come from 5,000 Monte-Carlo runs perturbing each factor within its stated error.</li>
              {rep?.metrics && <li>The ML estimator (not used in this statement) covers {pct(rep.metrics.s1.interval_coverage_test, 0)} of held-out companies at its 90% setting{synthetic ? ", measured on synthetic data" : ""}.</li>}
              {synthetic && <li><b>Data status:</b> the ML models were trained on synthetic companies, so they demonstrate the method rather than real-world accuracy.</li>}
            </ul>
          </Panel>
        </div>
      )}
    </>
  );
}
