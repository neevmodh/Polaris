import type { CalcInputs, CalcResult, Meta } from "./types";

export const toBody = (i: CalcInputs) => ({
  ...i.fuel, kwh: i.kwh, td_loss: i.td_loss,
  spend_inr: Object.fromEntries(Object.entries(i.spend_lakh).map(([k, v]) => [k, v * 1e5])),
});

/** Every number a reader needs to audit a result: factor, source, value, uncertainty. */
export function ledger(meta: Meta, i: CalcInputs) {
  const rows: { item: string; scope: string; value: string; source: string; sigma: string }[] = [];
  for (const f of meta.fuels) if ((i.fuel[f.key] ?? 0) > 0) rows.push({ item: f.label, scope: "1", value: `${f.ef} kg CO₂ per unit`, source: f.key === "diesel_l" ? "EPA: 10.21 kg per US gallon ÷ 3.78541 L" : "IPCC / DESNZ approximate, verify", sigma: `±${meta.sigmas.fuel * 100}%` });
  if (i.kwh > 0) rows.push({ item: "Grid electricity", scope: "2", value: `${meta.grid_ef} kg CO₂ per kWh${i.td_loss ? `, grossed up for ${(i.td_loss * 100).toFixed(0)}% T&D loss` : ""}`, source: "CEA CO₂ Baseline Database v22.0, FY2025-26 weighted average", sigma: `±${meta.sigmas.grid * 100}%` });
  for (const c of meta.scope3) if ((i.spend_lakh[c.key] ?? 0) > 0) rows.push({ item: c.label, scope: "3", value: `${(c.ef_kg_per_usd / meta.usd_to_inr).toFixed(4)} kg CO₂e per ₹ (${c.ef_kg_per_usd} per USD at ₹${meta.usd_to_inr})`, source: `EPA USEEIO v1.3, NAICS ${c.naics}, with margins (US factor, Indian spend)`, sigma: `±${meta.sigmas.spend * 100}%` });
  return rows;
}

export function download(name: string, text: string, mime: string) {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const csvCell = (v: unknown) => `"${String(v).replaceAll('"', '""')}"`;
export function toCsv(rows: Record<string, unknown>[]): string {
  if (!rows.length) return "";
  const cols = Object.keys(rows[0]);
  return [cols.join(","), ...rows.map((r) => cols.map((c) => csvCell(r[c])).join(","))].join("\n");
}

export function resultRows(name: string, r: CalcResult) {
  return (["scope1", "scope2", "scope3", "total"] as const).map((k) => ({
    scenario: name, scope: k, tco2e: r.point[k].toFixed(3), p5: r.range[k].p5.toFixed(3), p95: r.range[k].p95.toFixed(3),
  }));
}
