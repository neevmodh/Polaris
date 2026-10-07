export const nf0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
export const nf1 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1 });

/** Tonnes with sensible precision: 0.42, 8.3, 227, 33,534. */
export function fmtT(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "–";
  const a = Math.abs(n);
  if (a >= 100) return nf0.format(n);
  if (a >= 10) return nf1.format(n);
  return n.toFixed(a >= 1 ? 2 : 3);
}
export function fmtCompact(n: number): string {
  const a = Math.abs(n);
  if (a >= 1e7) return `${(n / 1e7).toFixed(a >= 1e8 ? 0 : 1)} Cr`;
  if (a >= 1e5) return `${(n / 1e5).toFixed(a >= 1e6 ? 0 : 1)} lakh`;
  if (a >= 1e3) return `${(n / 1e3).toFixed(a >= 1e4 ? 0 : 1)}k`;
  return nf0.format(n);
}
/** Round to `d` significant digits: ML estimates should not look more precise than they are. */
export function fmtSig(n: number, d = 3): string {
  if (!Number.isFinite(n) || n === 0) return fmtT(n);
  const p = Math.pow(10, Math.floor(Math.log10(Math.abs(n))) - d + 1);
  return fmtT(Math.round(n / p) * p);
}
export const pct = (x: number, d = 0) => `${(x * 100).toFixed(d)}%`;
/** Rupees in the way Indian readers expect: ₹24.3 lakh, ₹1.2 Cr. */
export function inrShort(n: number): string {
  const a = Math.abs(n), s = n < 0 ? "−" : "";
  if (a >= 1e7) return `${s}₹${(a / 1e7).toFixed(2)} Cr`;
  if (a >= 1e5) return `${s}₹${(a / 1e5).toFixed(1)} lakh`;
  return `${s}₹${nf0.format(a)}`;
}
export const inr = (n: number) => `${n < 0 ? "−" : ""}₹${nf0.format(Math.abs(n))}`;
