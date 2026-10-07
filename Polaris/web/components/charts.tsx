"use client";
import { useRef, useState } from "react";
import type { Lever, PathRow, StressRun, WeekSeries, GridHour } from "@/lib/types";
import { fmtCompact, fmtT, inr } from "@/lib/format";

function niceStep(max: number, ticks = 4) {
  const raw = max / ticks, mag = Math.pow(10, Math.floor(Math.log10(raw || 1))), n = raw / mag;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * mag;
}

/** P5–P95 whisker with a tick at the point estimate, on a 0..max scale. */
export function RangeBar({ lo, point, hi, max, color }: { lo: number; point: number; hi: number; max: number; color: string }) {
  const p = (v: number) => `${Math.min(Math.max(v / (max || 1), 0), 1) * 100}%`;
  return (
    <div className="rb" role="img" aria-label={`Point ${fmtT(point)}, range ${fmtT(lo)} to ${fmtT(hi)}`}>
      <div className="track" />
      <div className="band" style={{ left: p(lo), width: `calc(${p(hi)} - ${p(lo)})`, background: color }} />
      <div className="pt" style={{ left: p(point), background: color }} />
      <div className="ends"><span>0</span><span>{fmtT(max)}</span></div>
    </div>
  );
}

/** Interval on a log axis (emissions span orders of magnitude). */
export function LogRange({ lo, point, hi, color }: { lo: number; point: number; hi: number; color: string }) {
  const W = 520, H = 78, pad = 14;
  const a = Math.log10(Math.max(lo, 1e-9) / 3), b = Math.log10(hi * 3);
  const x = (v: number) => pad + ((Math.log10(Math.max(v, 1e-9)) - a) / (b - a)) * (W - 2 * pad);
  const ticks: number[] = [];
  for (let e = Math.floor(a); e <= Math.ceil(b); e++) for (const k of [1, 2, 5]) { const v = k * Math.pow(10, e), lg = Math.log10(v); if (lg >= a && lg <= b) ticks.push(v); }
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Estimate ${fmtT(point)}, 90% interval ${fmtT(lo)} to ${fmtT(hi)} tonnes`}>
      <line className="axis" x1={pad} x2={W - pad} y1={34} y2={34} />
      {ticks.map((t) => (<g key={t}><line className="grid" x1={x(t)} x2={x(t)} y1={26} y2={42} /><text x={x(t)} y={62} textAnchor="middle" style={{ fontSize: 11.5 }}>{fmtCompact(t)}</text></g>))}
      <rect x={x(lo)} y={24} width={Math.max(x(hi) - x(lo), 2)} height={20} rx={4} fill={color} opacity={0.25} />
      <rect x={x(lo) - 1} y={20} width={2.5} height={28} rx={1} fill={color} /><rect x={x(hi) - 1.5} y={20} width={2.5} height={28} rx={1} fill={color} />
      <rect x={x(point) - 2} y={14} width={4} height={40} rx={2} fill={color} />
    </svg>
  );
}

export function PathwayChart({ rows }: { rows: PathRow[] }) {
  const W = 1040, H = 440, m = { l: 84, r: 20, t: 36, b: 50 };
  const [hover, setHover] = useState<number | null>(null);
  const box = useRef<HTMLDivElement>(null);
  if (!rows.length) return null;
  const y0 = rows[0].year, y1 = rows[rows.length - 1].year;
  const top = Math.max(...rows.map((r) => Math.max(r.bau_p90, r.sbti_1p5C_line))) * 1.06 || 1;
  const step = niceStep(top), ymax = Math.ceil(top / step) * step;
  const X = (y: number) => m.l + ((y - y0) / (y1 - y0 || 1)) * (W - m.l - m.r);
  const Y = (v: number) => H - m.b - (v / ymax) * (H - m.t - m.b);
  const line = (k: keyof PathRow) => rows.map((r, i) => `${i ? "L" : "M"}${X(r.year).toFixed(1)},${Y(r[k] as number).toFixed(1)}`).join("");
  const band = (hi: keyof PathRow, lo: keyof PathRow) =>
    rows.map((r, i) => `${i ? "L" : "M"}${X(r.year)},${Y(r[hi] as number)}`).join("") + [...rows].reverse().map((r) => `L${X(r.year)},${Y(r[lo] as number)}`).join("") + "Z";
  const yt: number[] = []; for (let v = 0; v <= ymax + 1e-9; v += step) yt.push(v);
  const xt = rows.filter((r) => (r.year - y0) % 4 === 0 || r.year === y1);
  const onMove = (e: React.PointerEvent) => {
    const rect = box.current!.getBoundingClientRect(), px = ((e.clientX - rect.left) / rect.width) * W;
    const yr = y0 + ((px - m.l) / (W - m.l - m.r)) * (y1 - y0);
    setHover(Math.min(Math.max(Math.round(yr - y0), 0), rows.length - 1));
  };
  const h = hover != null ? rows[hover] : null;
  return (
    <div style={{ position: "relative" }} ref={box} onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Emissions pathway to 2050 with and without abatement levers, against a 1.5 degree line">
        {yt.map((v) => (<g key={v}><line className="grid" x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} /><text x={m.l - 10} y={Y(v) + 4} textAnchor="end">{fmtCompact(v)}</text></g>))}
        {xt.map((r) => <text key={r.year} x={X(r.year)} y={H - m.b + 22} textAnchor="middle">{r.year}</text>)}
        <text x={m.l} y={14}>tCO₂e per year</text>
        <path d={band("bau_p90", "bau_p10")} fill="var(--muted)" opacity={0.14} />
        <path d={band("with_levers_p90", "with_levers_p10")} fill="var(--s3)" opacity={0.22} />
        <path d={line("sbti_1p5C_line")} fill="none" stroke="var(--warn)" strokeWidth={2} strokeDasharray="2 5" strokeLinecap="round" />
        <path d={line("bau_p50")} fill="none" stroke="var(--muted)" strokeWidth={2} strokeDasharray="7 5" />
        <path d={line("with_levers_p50")} fill="none" stroke="var(--s3)" strokeWidth={3.2} strokeLinejoin="round" />
        {h && <g><line x1={X(h.year)} x2={X(h.year)} y1={m.t} y2={H - m.b} stroke="var(--ink)" strokeWidth={1} opacity={0.4} />
          <circle cx={X(h.year)} cy={Y(h.with_levers_p50)} r={5} fill="var(--s3)" stroke="var(--surface)" strokeWidth={2} />
          <circle cx={X(h.year)} cy={Y(h.bau_p50)} r={4} fill="var(--muted)" stroke="var(--surface)" strokeWidth={2} /></g>}
      </svg>
      {h && (
        <div className="tip" style={{ left: `clamp(8px, calc(${(X(h.year) / W) * 100}% - 80px), calc(100% - 200px))`, top: 8 }}>
          <b>{h.year}</b><br />Business as usual <b>{fmtT(h.bau_p50)}</b><br />With levers <b>{fmtT(h.with_levers_p50)}</b><br />1.5°C line <b>{fmtT(h.sbti_1p5C_line)}</b>
        </div>
      )}
      <div className="legend" style={{ marginTop: 6 }}>
        <span><i style={{ background: "var(--muted)" }} />Business as usual (P10–P90 shaded)</span>
        <span><i style={{ background: "var(--s3)" }} />With levers (P10–P90 shaded)</span>
        <span><i style={{ background: "var(--warn)" }} />1.5°C line, −4.2% a year</span>
      </div>
    </div>
  );
}

const SCOPE_COLOR: Record<number, string> = { 1: "var(--s1)", 2: "var(--s2)", 3: "var(--s3)" };

export function MaccChart({ levers }: { levers: Lever[] }) {
  const W = 860, H = 360, m = { l: 90, r: 20, t: 40, b: 50 };
  const [hover, setHover] = useState<number | null>(null);
  if (!levers.length) return <p className="note">No levers active. Raise a saving, solar or PPA setting to see the cost curve.</p>;
  const total = levers.reduce((s, l) => s + l.abatement_t, 0) || 1;
  const costs = levers.map((l) => l.cost_inr_per_t);
  const lo = Math.min(0, ...costs) * 1.2, hi = Math.max(0, ...costs) * 1.4 || 1;
  const step = niceStep(hi - lo, 4);
  const yMin = Math.floor(lo / step) * step, yMax = Math.ceil(hi / step) * step;
  const X = (v: number) => m.l + (v / total) * (W - m.l - m.r);
  const Y = (v: number) => m.t + ((yMax - v) / (yMax - yMin || 1)) * (H - m.t - m.b);
  const ticks: number[] = []; for (let v = yMin; v <= yMax + 1e-9; v += step) ticks.push(Math.round(v));
  const bars = levers.map((l, i) => { const x = X(l.cumulative_t - l.abatement_t); return { l, i, x, w: Math.max(X(l.cumulative_t) - x - 2, 3) }; });
  const h = hover != null ? bars[hover] : null;
  return (
    <div style={{ position: "relative" }}>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Marginal abatement cost curve: cost in rupees per tonne against annual abatement, cheapest lever first">
        {ticks.map((v) => (<g key={v}><line className="grid" x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} /><text x={m.l - 10} y={Y(v) + 4} textAnchor="end">{fmtCompact(v)}</text></g>))}
        <text x={m.l} y={16}>₹ per tCO₂e</text>
        {bars.map(({ l, i, x, w }) => {
          const y0 = Y(0), y1 = Y(l.cost_inr_per_t);
          return (<g key={l.name} onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)} style={{ cursor: "default" }}>
            <rect x={x} y={Math.min(y0, y1)} width={w} height={Math.max(Math.abs(y1 - y0), 3)} rx={3} fill={SCOPE_COLOR[l.scope]} opacity={hover == null || hover === i ? 0.95 : 0.4} />
            {w > 70 && <text x={x + w / 2} y={l.cost_inr_per_t <= 0 ? y1 + 16 : y1 - 7} textAnchor="middle" style={{ fill: "var(--ink)", fontWeight: 600, fontSize: 13 }}>{inr(l.cost_inr_per_t)}</text>}
          </g>);
        })}
        <line className="axis" x1={m.l} x2={W - m.r} y1={Y(0)} y2={Y(0)} style={{ stroke: "var(--ink)" }} />
        <text x={m.l} y={H - 12}>0</text><text x={W - m.r} y={H - 12} textAnchor="end">{fmtT(total)} tCO₂e abated per year</text>
      </svg>
      {h && (<div className="tip" style={{ left: `clamp(8px, calc(${((h.x + h.w / 2) / W) * 100}% - 90px), calc(100% - 210px))`, top: 4 }}>
        <b>{h.l.name}</b><br />Abates <b>{fmtT(h.l.abatement_t)}</b> t / yr<br />Cost <b>{inr(h.l.cost_inr_per_t)}</b> per t<br />Net <b>{inr(h.l.annual_net_cost_inr)}</b> / yr</div>)}
      <div className="legend" style={{ marginTop: 6 }}>
        {levers.map((l) => (<span key={l.name}><i style={{ background: SCOPE_COLOR[l.scope], height: 10, width: 10, borderRadius: 2 }} />{l.name} <span className="mono" style={{ fontSize: 11 }}>S{l.scope}</span></span>))}
      </div>
    </div>
  );
}

/** Days of fuel: P10–P90 band and median for each scenario against the delivery day. */
export function RunwayRuler({ base, saved, delivery, delay, nominal }: { base: number[]; saved: number[]; delivery: number; delay: number; nominal: number }) {
  const W = 860, H = 230, m = { l: 118, r: 24, t: 34, b: 40 };
  const maxDay = Math.max(delivery + delay + 4, saved[2] * 1.08, base[2] * 1.08, 10);
  const step = niceStep(maxDay, 6), top = Math.ceil(maxDay / step) * step;
  const X = (d: number) => m.l + (d / top) * (W - m.l - m.r);
  const ticks: number[] = []; for (let d = 0; d <= top + 1e-9; d += step) ticks.push(d);
  const rows = [{ y: 82, label: "As planned", v: base, color: "var(--muted)" }, { y: 148, label: "With saving", v: saved, color: "var(--s3)" }];
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Fuel lasts a median ${base[1]} days as planned and ${saved[1]} days with the saving; delivery is on day ${delivery}`}>
      {ticks.map((d) => (<g key={d}><line className="grid" x1={X(d)} x2={X(d)} y1={m.t} y2={H - m.b} /><text x={X(d)} y={H - m.b + 22} textAnchor="middle">{d}</text></g>))}
      <text x={m.l} y={H - 6}>days from today</text>
      {rows.map((r) => (<g key={r.label}>
        <text x={m.l - 12} y={r.y + 4} textAnchor="end" style={{ fill: "var(--ink)", fontWeight: 600 }}>{r.label}</text>
        <rect x={X(r.v[0])} y={r.y - 14} width={Math.max(X(r.v[2]) - X(r.v[0]), 2)} height={28} fill={r.color} opacity={0.28} />
        <rect x={X(r.v[0]) - 1} y={r.y - 14} width={2} height={28} fill={r.color} /><rect x={X(r.v[2]) - 1} y={r.y - 14} width={2} height={28} fill={r.color} />
        <rect x={X(r.v[1]) - 2} y={r.y - 20} width={4} height={40} fill={r.color} />
        <text x={X(r.v[1])} y={r.y - 26} textAnchor="middle" style={{ fill: "var(--ink)", fontWeight: 600, fontSize: 12 }}>{r.v[1]} d</text>
      </g>))}
      <line x1={X(nominal)} x2={X(nominal)} y1={m.t + 6} y2={H - m.b} stroke="var(--faint)" strokeWidth={1.5} strokeDasharray="2 4" />
      <line x1={X(delivery)} x2={X(delivery)} y1={m.t - 6} y2={H - m.b} stroke="var(--ink)" strokeWidth={2.5} />
      <text x={X(delivery)} y={m.t - 12} textAnchor="middle" style={{ fill: "var(--ink)", fontWeight: 700 }}>delivery day {delivery}</text>
      {delay > 0 && <g><line x1={X(delivery + delay)} x2={X(delivery + delay)} y1={m.t - 6} y2={H - m.b} stroke="var(--bad)" strokeWidth={2} strokeDasharray="6 4" />
        <text x={X(delivery + delay)} y={m.t - 12} textAnchor="start" dx={6} style={{ fill: "var(--bad)", fontWeight: 700 }}>+{delay} d late</text></g>}
    </svg>
  );
}

/** Chance the fuel lasts, as the delivery slips later. */
export function DelayChart({ delays, base, saved, target, mark }: { delays: number[]; base: number[]; saved: number[]; target: number; mark: number }) {
  const W = 860, H = 300, m = { l: 62, r: 18, t: 20, b: 46 };
  const [hover, setHover] = useState<number | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const X = (d: number) => m.l + (d / (delays[delays.length - 1] || 1)) * (W - m.l - m.r);
  const Y = (p: number) => H - m.b - p * (H - m.t - m.b);
  const line = (a: number[]) => a.map((p, i) => `${i ? "L" : "M"}${X(delays[i]).toFixed(1)},${Y(p).toFixed(1)}`).join("");
  const onMove = (e: React.PointerEvent) => {
    const r = box.current!.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W;
    setHover(Math.min(Math.max(Math.round(((px - m.l) / (W - m.l - m.r)) * (delays.length - 1)), 0), delays.length - 1));
  };
  return (
    <div style={{ position: "relative" }} ref={box} onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Probability that the fuel lasts until delivery, by days of delay">
        {[0, 0.25, 0.5, 0.75, 1].map((p) => (<g key={p}><line className="grid" x1={m.l} x2={W - m.r} y1={Y(p)} y2={Y(p)} /><text x={m.l - 10} y={Y(p) + 4} textAnchor="end">{Math.round(p * 100)}%</text></g>))}
        {delays.filter((d) => d % 2 === 0).map((d) => <text key={d} x={X(d)} y={H - m.b + 22} textAnchor="middle">{d}</text>)}
        <text x={m.l} y={H - 6}>days the delivery arrives late</text>
        <line x1={m.l} x2={W - m.r} y1={Y(target)} y2={Y(target)} stroke="var(--warn)" strokeWidth={1.5} strokeDasharray="2 5" />
        <text x={W - m.r} y={Y(target) - 7} textAnchor="end" style={{ fill: "var(--warn)" }}>{Math.round(target * 100)}% target</text>
        <line x1={X(mark)} x2={X(mark)} y1={m.t} y2={H - m.b} stroke="var(--ink)" strokeWidth={1} opacity={0.35} />
        <path d={line(base)} fill="none" stroke="var(--muted)" strokeWidth={2.4} strokeDasharray="7 5" />
        <path d={line(saved)} fill="none" stroke="var(--s3)" strokeWidth={3.2} strokeLinejoin="round" />
        {hover != null && <g><circle cx={X(delays[hover])} cy={Y(saved[hover])} r={5} fill="var(--s3)" stroke="var(--surface)" strokeWidth={2} /><circle cx={X(delays[hover])} cy={Y(base[hover])} r={4} fill="var(--muted)" stroke="var(--surface)" strokeWidth={2} /></g>}
      </svg>
      {hover != null && (
        <div className="tip" style={{ left: `clamp(8px, calc(${(X(delays[hover]) / W) * 100}% - 80px), calc(100% - 190px))`, top: 6 }}>
          <b>{delays[hover]} days late</b><br />As planned <b>{Math.round(base[hover] * 100)}%</b><br />With saving <b>{Math.round(saved[hover] * 100)}%</b>
        </div>
      )}
      <div className="legend" style={{ marginTop: 6 }}>
        <span><i style={{ background: "var(--muted)" }} />As planned</span><span><i style={{ background: "var(--s3)" }} />With saving</span>
      </div>
    </div>
  );
}

/** Horizontal bars for variance shares. */
export function DriverBars({ rows }: { rows: { name: string; scope: number; share: number }[] }) {
  const max = Math.max(...rows.map((r) => r.share), 1e-9);
  const col: Record<number, string> = { 1: "var(--s1)", 2: "var(--s2)", 3: "var(--s3)" };
  return (
    <div className="bars" role="list">
      {rows.map((r) => (
        <div className="bar" key={r.name} role="listitem">
          <span className="l">{r.name}</span><span className="tr"><i style={{ width: `${(r.share / max) * 100}%`, background: col[r.scope] }} /></span><span className="n">{(r.share * 100).toFixed(r.share < 0.1 ? 1 : 0)}%</span>
        </div>
      ))}
    </div>
  );
}

/** Two models, several metrics: grouped bars on a 0–1 scale. */
export function MetricBars({ groups, aName, bName }: { groups: { label: string; a: number; b: number }[]; aName: string; bName: string }) {
  const W = 620, H = 300, m = { l: 40, r: 10, t: 24, b: 40 }, gw = (W - m.l - m.r) / groups.length, bw = Math.min(34, gw / 2 - 6);
  const Y = (v: number) => H - m.b - v * (H - m.t - m.b);
  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${aName} against ${bName}: ${groups.map((g) => `${g.label} ${g.a.toFixed(2)} vs ${g.b.toFixed(2)}`).join(", ")}`}>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (<g key={t}><line className="grid" x1={m.l} x2={W - m.r} y1={Y(t)} y2={Y(t)} /><text x={m.l - 8} y={Y(t) + 4} textAnchor="end" style={{ fontSize: 11 }}>{t}</text></g>))}
        {groups.map((g, i) => {
          const cx = m.l + gw * i + gw / 2;
          return (<g key={g.label}>
            <rect x={cx - bw - 2} y={Y(g.a)} width={bw} height={Y(0) - Y(g.a)} fill="var(--ml)" /><rect x={cx + 2} y={Y(g.b)} width={bw} height={Y(0) - Y(g.b)} fill="var(--muted)" opacity={0.7} />
            <text x={cx - bw / 2 - 2} y={Y(g.a) - 5} textAnchor="middle" style={{ fontSize: 11, fill: "var(--ink)" }}>{g.a.toFixed(2)}</text>
            <text x={cx + bw / 2 + 2} y={Y(g.b) - 5} textAnchor="middle" style={{ fontSize: 11, fill: "var(--ink)" }}>{g.b.toFixed(2)}</text>
            <text x={cx} y={H - m.b + 20} textAnchor="middle" style={{ fontSize: 12 }}>{g.label}</text>
          </g>);
        })}
      </svg>
      <div className="legend" style={{ marginTop: 6 }}><span><i style={{ background: "var(--ml)" }} />{aName}</span><span><i style={{ background: "var(--muted)" }} />{bName}</span></div>
    </div>
  );
}

/** Horizontal bars for a single series (feature importance and similar). */
export function HBars({ rows, color = "var(--ml)", fmt = (v: number) => v.toFixed(3) }: { rows: { name: string; value: number }[]; color?: string; fmt?: (v: number) => string }) {
  const max = Math.max(...rows.map((r) => r.value), 1e-9);
  return (
    <div className="bars" role="list">
      {rows.map((r) => (
        <div className="bar" key={r.name} role="listitem"><span className="l mono" style={{ fontSize: 12 }}>{r.name}</span><span className="tr"><i style={{ width: `${(r.value / max) * 100}%`, background: color }} /></span><span className="n">{fmt(r.value)}</span></div>
      ))}
    </div>
  );
}


const SRC = [["Wind", "var(--s2)"], ["Solar", "var(--warn)"], ["Battery", "var(--s3)"], ["Diesel", "var(--s1)"]] as const;

/** One week, hour by hour: what powered the load (stacked) and what charged the battery (below the axis). */
export function DispatchChart({ w }: { w: WeekSeries }) {
  const W = 1040, H = 360, m = { l: 62, r: 14, t: 18, b: 44 }, n = w.demand.length;
  const [hover, setHover] = useState<number | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const top = Math.max(...w.demand.map((d, i) => Math.max(d, w.gen[i] + w.pv_used[i] + w.wind_used[i] + w.discharge[i]))) * 1.08 || 1;
  const bot = Math.max(...w.charge, 0) * 1.05;
  const step = niceStep(top + bot, 5), yTop = Math.ceil(top / step) * step, yBot = bot > 0 ? Math.ceil(bot / step) * step : 0;
  const X = (i: number) => m.l + (i / n) * (W - m.l - m.r), bw = (W - m.l - m.r) / n;
  const Y = (v: number) => m.t + ((yTop - v) / (yTop + yBot)) * (H - m.t - m.b);
  const ticks: number[] = []; for (let v = -yBot; v <= yTop + 1e-9; v += step) ticks.push(Math.round(v * 100) / 100);
  const day0 = new Date(w.start + "T00:00:00Z");
  const dayLabel = (d: number) => { const t = new Date(day0.getTime() + d * 864e5); return t.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }); };
  const onMove = (e: React.PointerEvent) => { const r = box.current!.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W; setHover(Math.min(Math.max(Math.floor(((px - m.l) / (W - m.l - m.r)) * n), 0), n - 1)); };
  const line = w.demand.map((d, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(d).toFixed(1)} L${(X(i) + bw).toFixed(1)},${Y(d).toFixed(1)}`).join("");
  const h = hover != null ? hover : null;
  return (
    <div style={{ position: "relative" }} ref={box} onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Hourly power sources for one week: wind, solar, battery and diesel stacked against the demand line">
        {ticks.map((v) => (<g key={v}><line className="grid" x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} /><text x={m.l - 8} y={Y(v) + 4} textAnchor="end">{v}</text></g>))}
        <text x={m.l} y={11}>kW</text>
        {Array.from({ length: n / 24 }, (_, d) => (<g key={d}><line className="grid" x1={X(d * 24)} x2={X(d * 24)} y1={m.t} y2={H - m.b} style={{ stroke: "var(--line-strong)", opacity: 0.35 }} /><text x={X(d * 24) + 4} y={H - m.b + 18} style={{ fontSize: 12 }}>{dayLabel(d)}</text></g>))}
        {w.demand.map((_, i) => {
          let acc = 0; const parts = [w.wind_used[i], w.pv_used[i], w.discharge[i], w.gen[i]];
          return (<g key={i}>{parts.map((v, k) => { const y0 = Y(acc); acc += v; return v > 0.01 ? <rect key={k} x={X(i)} y={Y(acc)} width={Math.max(bw - 0.4, 0.6)} height={y0 - Y(acc)} fill={SRC[k][1]} opacity={h === i ? 1 : 0.88} /> : null; })}
            {w.charge[i] > 0.01 && <rect x={X(i)} y={Y(0)} width={Math.max(bw - 0.4, 0.6)} height={Y(-w.charge[i]) - Y(0)} fill="var(--s3)" opacity={0.35} />}</g>);
        })}
        <path d={line} fill="none" stroke="var(--ink)" strokeWidth={1.8} />
        <line className="axis" x1={m.l} x2={W - m.r} y1={Y(0)} y2={Y(0)} style={{ stroke: "var(--ink)", opacity: 0.8 }} />
        {h != null && <line x1={X(h) + bw / 2} x2={X(h) + bw / 2} y1={m.t} y2={H - m.b} stroke="var(--ink)" strokeWidth={1} opacity={0.5} />}
      </svg>
      {h != null && (
        <div className="tip" style={{ left: `clamp(8px, calc(${((X(h) + bw / 2) / W) * 100}% - 90px), calc(100% - 200px))`, top: 6 }}>
          <b>{dayLabel(Math.floor(h / 24))}, {String(h % 24).padStart(2, "0")}:00 UTC</b><br />Demand <b>{w.demand[h].toFixed(1)}</b> kW<br />Wind <b>{w.wind_used[h].toFixed(1)}</b> · Solar <b>{w.pv_used[h].toFixed(1)}</b><br />Battery <b>{(w.discharge[h] - w.charge[h]).toFixed(1)}</b> · Diesel <b>{w.gen[h].toFixed(1)}</b><br />Battery level <b>{w.soc[h].toFixed(0)}</b> kWh
        </div>
      )}
      <div className="legend" style={{ marginTop: 6 }}>
        {SRC.map(([n2, c]) => <span key={n2}><i style={{ background: c, height: 10, width: 10 }} />{n2}</span>)}
        <span><i style={{ background: "var(--s3)", opacity: 0.35, height: 10, width: 10 }} />Battery charging (below axis)</span><span><i style={{ background: "var(--ink)" }} />Demand</span>
      </div>
    </div>
  );
}

/** Fuel per month for three ways of operating the same station. */
export function MonthlyBars({ series }: { series: { name: string; color: string; values: number[] }[] }) {
  const W = 1040, H = 300, m = { l: 66, r: 10, t: 18, b: 38 }, months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const max = Math.max(...series.flatMap((s) => s.values), 1) * 1.08, step = niceStep(max, 4), top = Math.ceil(max / step) * step;
  const gw = (W - m.l - m.r) / 12, bw = Math.min(22, (gw - 10) / series.length), Y = (v: number) => H - m.b - (v / top) * (H - m.t - m.b);
  const ticks: number[] = []; for (let v = 0; v <= top + 1e-9; v += step) ticks.push(v);
  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Monthly diesel use: ${series.map((s) => s.name).join(", ")}`}>
        {ticks.map((v) => (<g key={v}><line className="grid" x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} /><text x={m.l - 8} y={Y(v) + 4} textAnchor="end">{fmtCompact(v)}</text></g>))}
        <text x={m.l} y={11}>litres of diesel</text>
        {months.map((mo, i) => {
          const cx = m.l + gw * i + gw / 2;
          return (<g key={mo}>{series.map((s, k) => <rect key={s.name} x={cx - (series.length * bw) / 2 + k * bw} y={Y(s.values[i])} width={bw - 1.5} height={Y(0) - Y(s.values[i])} fill={s.color} />)}
            <text x={cx} y={H - m.b + 20} textAnchor="middle">{mo}</text></g>);
        })}
        <line className="axis" x1={m.l} x2={W - m.r} y1={Y(0)} y2={Y(0)} />
      </svg>
      <div className="legend" style={{ marginTop: 6 }}>{series.map((s) => <span key={s.name}><i style={{ background: s.color, height: 10, width: 10 }} />{s.name}</span>)}</div>
    </div>
  );
}

/** The resupply test: diesel left in the tank day by day under three ways of operating, against the delivery day. */
export function StressChart({ runs, tank, delivery }: { runs: { name: string; color: string; dash?: string; data: StressRun }[]; tank: number; delivery: number }) {
  const W = 1040, H = 330, m = { l: 66, r: 110, t: 24, b: 44 }, days = Math.max(...runs.map((r) => r.data.fuel_stock_daily.length)) - 1;
  const step = niceStep(tank, 4), top = Math.ceil(tank / step) * step;
  const X = (d: number) => m.l + (d / days) * (W - m.l - m.r), Y = (v: number) => H - m.b - (v / top) * (H - m.t - m.b);
  const ticks: number[] = []; for (let v = 0; v <= top + 1e-9; v += step) ticks.push(v);
  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Diesel in the tank by day for three operating strategies, with the delivery day marked">
        {ticks.map((v) => (<g key={v}><line className="grid" x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} /><text x={m.l - 8} y={Y(v) + 4} textAnchor="end">{fmtCompact(v)}</text></g>))}
        {Array.from({ length: Math.floor(days / 5) + 1 }, (_, i) => i * 5).map((d) => <text key={d} x={X(d)} y={H - m.b + 20} textAnchor="middle">{d}</text>)}
        <text x={m.l} y={13}>litres in the tank</text><text x={W - m.r} y={H - 6} textAnchor="end">days from the start of the test</text>
        <line x1={X(delivery)} x2={X(delivery)} y1={m.t} y2={H - m.b} stroke="var(--ink)" strokeWidth={2.5} />
        <text x={X(delivery) + 6} y={m.t + 12} style={{ fill: "var(--ink)", fontWeight: 700 }}>delivery, day {delivery}</text>
        {runs.map((r) => (<g key={r.name}>
          <path d={r.data.fuel_stock_daily.map((v, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join("")} fill="none" stroke={r.color} strokeWidth={r.name === "Survival" ? 3.4 : 2.4} strokeDasharray={r.dash} strokeLinejoin="round" />
          <text x={X(r.data.fuel_stock_daily.length - 1) + 8} y={Y(r.data.fuel_stock_daily[r.data.fuel_stock_daily.length - 1]) + 4} style={{ fill: r.color, fontWeight: 700, fontSize: 12.5 }}>{r.name}</text></g>))}
        <line className="axis" x1={m.l} x2={W - m.r} y1={Y(0)} y2={Y(0)} />
      </svg>
    </div>
  );
}

/** Observed history running into a forecast with its uncertainty band (Air sheet). */
export function AirChart({ history, forecast, unit }: { history: { date: string; value: number }[]; forecast: { date: string; predicted: number; lower: number; upper: number }[]; unit: string }) {
  const W = 1040, H = 340, m = { l: 62, r: 14, t: 18, b: 38 };
  const n = history.length + forecast.length;
  const vals = [...history.map((h) => h.value), ...forecast.flatMap((f) => [f.lower, f.upper])];
  const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * 0.08 || 1;
  const step = niceStep(hi - lo + 2 * pad, 5), yLo = Math.floor((lo - pad) / step) * step, yHi = Math.ceil((hi + pad) / step) * step;
  // A fortnight next to six months of history would be 7% of the width, so the forecast gets a
  // fixed quarter of the plot. The break is drawn, never implied.
  const inner = W - m.l - m.r, split = m.l + inner * 0.74, nh = history.length, nf = forecast.length;
  const X = (i: number) => i <= nh - 1
    ? m.l + (i / Math.max(nh - 1, 1)) * (split - m.l)
    : split + ((i - (nh - 1)) / Math.max(nf, 1)) * (W - m.r - split);
  const Y = (v: number) => m.t + ((yHi - v) / (yHi - yLo)) * (H - m.t - m.b);
  const ticks: number[] = []; for (let v = yLo; v <= yHi + 1e-9; v += step) ticks.push(Math.round(v * 100) / 100);
  const hist = history.map((h, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(h.value).toFixed(1)}`).join("");
  const j = history.length - 1;
  const line = `M${X(j).toFixed(1)},${Y(history[j]?.value ?? forecast[0].predicted).toFixed(1)}` + forecast.map((f, i) => `L${X(j + 1 + i).toFixed(1)},${Y(f.predicted).toFixed(1)}`).join("");
  const band = [...forecast.map((f, i) => `${i ? "L" : "M"}${X(j + 1 + i).toFixed(1)},${Y(f.upper).toFixed(1)}`),
    ...forecast.slice().reverse().map((f, i) => `L${X(n - 1 - i).toFixed(1)},${Y(f.lower).toFixed(1)}`), "Z"].join("");
  const label = (s: string) => new Date(s + "T00:00:00Z").toLocaleDateString("en-GB", { month: "short", year: "2-digit", timeZone: "UTC" });
  const marks = [0, Math.floor(history.length / 2), j, n - 1];
  const anchor = (i: number) => (i === 0 ? "start" : i === n - 1 ? "end" : i === j ? "end" : "middle");
  const all = [...history.map((h) => h.date), ...forecast.map((f) => f.date)];
  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Daily ${unit} history running into a forecast with its 90 percent band`}>
        {ticks.map((v) => (<g key={v}><line className="grid" x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} /><text x={m.l - 8} y={Y(v) + 4} textAnchor="end">{v}</text></g>))}
        <text x={m.l} y={11}>{unit}</text>
        <path d={band} fill="var(--ml)" opacity={0.16} />
        <path d={hist} fill="none" stroke="var(--muted)" strokeWidth={1.6} />
        <path d={line} fill="none" stroke="var(--ml)" strokeWidth={2.4} />
        <line x1={X(j)} x2={X(j)} y1={m.t} y2={H - m.b} stroke="var(--ink)" strokeDasharray="3 3" opacity={0.6} />
        {marks.map((i) => <text key={i} x={X(i)} y={H - m.b + 18} textAnchor={anchor(i)} style={{ fontSize: 12 }}>{label(all[i])}</text>)}
        <text x={(split + (W - m.r)) / 2} y={m.t - 5} textAnchor="middle" style={{ fontSize: 11, fill: "var(--ml)" }}>forecast</text>
      </svg>
      <div className="legend" style={{ marginTop: 6 }}>
        <span><i style={{ background: "var(--muted)" }} />Observed daily estimate</span>
        <span><i style={{ background: "var(--ml)" }} />Forecast</span>
        <span><i style={{ background: "var(--ml)", opacity: 0.3, height: 10, width: 10 }} />Nominal 90% band</span>
      </div>
    </div>
  );
}

/** Daily values against a rolling review level, with flagged days marked (Air alerts sheet). */
export function AlertChart({ rows, unit }: { rows: { date: string; value: number; level: number | null; flag: boolean }[]; unit: string }) {
  const W = 1040, H = 300, m = { l: 62, r: 14, t: 18, b: 38 }, n = rows.length;
  const vals = rows.flatMap((r) => (r.level == null ? [r.value] : [r.value, r.level]));
  const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * 0.08 || 1;
  const step = niceStep(hi - lo + 2 * pad, 4), yLo = Math.floor((lo - pad) / step) * step, yHi = Math.ceil((hi + pad) / step) * step;
  const X = (i: number) => m.l + (i / Math.max(n - 1, 1)) * (W - m.l - m.r);
  const Y = (v: number) => m.t + ((yHi - v) / (yHi - yLo)) * (H - m.t - m.b);
  const ticks: number[] = []; for (let v = yLo; v <= yHi + 1e-9; v += step) ticks.push(Math.round(v * 100) / 100);
  const path = (get: (r: typeof rows[0]) => number | null) => {
    let d = "", pen = false;
    rows.forEach((r, i) => { const v = get(r); if (v == null) { pen = false; return; } d += `${pen ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`; pen = true; });
    return d;
  };
  const label = (s: string) => new Date(s + "T00:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Daily ${unit} against a rolling review level, with unusually high days marked`}>
        {ticks.map((v) => (<g key={v}><line className="grid" x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} /><text x={m.l - 8} y={Y(v) + 4} textAnchor="end">{v}</text></g>))}
        <text x={m.l} y={11}>{unit}</text>
        <path d={path((r) => r.level)} fill="none" stroke="var(--warn)" strokeWidth={1.4} strokeDasharray="4 3" />
        <path d={path((r) => r.value)} fill="none" stroke="var(--muted)" strokeWidth={1.6} />
        {rows.map((r, i) => r.flag && <circle key={i} cx={X(i)} cy={Y(r.value)} r={3.4} fill="var(--bad)" />)}
        {[0, Math.floor(n / 2), n - 1].map((i) => rows[i] && <text key={i} x={X(i)} y={H - m.b + 18} textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"} style={{ fontSize: 12 }}>{label(rows[i].date)}</text>)}
      </svg>
      <div className="legend" style={{ marginTop: 6 }}>
        <span><i style={{ background: "var(--muted)" }} />Daily value</span>
        <span><i style={{ background: "var(--warn)" }} />Review level (preceding 90 days)</span>
        <span><i style={{ background: "var(--bad)" }} />Flagged day</span>
      </div>
    </div>
  );
}

/** Stacked hourly sources for the grid-tied microgrid, with demand over the top and charging below the axis. */
export function GridChart({ dispatch, load }: { dispatch: GridHour[]; load: number[] }) {
  const W = 1040, H = 340, m = { l: 62, r: 14, t: 18, b: 40 }, n = dispatch.length;
  const [hover, setHover] = useState<number | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const SRCS: [string, string, (d: GridHour) => number][] = [
    ["Solar", "var(--s1)", (d) => d.solar_kw], ["Wind", "var(--s3)", (d) => d.wind_kw],
    ["Battery", "var(--ml)", (d) => d.discharge_kw], ["Grid", "var(--s2)", (d) => d.grid_import_kw],
  ];
  const top = Math.max(...dispatch.map((d, i) => Math.max(load[i] ?? 0, SRCS.reduce((a, s) => a + s[2](d), 0))), 1) * 1.08;
  const bot = Math.max(...dispatch.map((d) => d.charge_kw), 0) * 1.05;
  const step = niceStep(top + bot, 5), yTop = Math.ceil(top / step) * step, yBot = bot > 0 ? Math.ceil(bot / step) * step : 0;
  const X = (i: number) => m.l + (i / n) * (W - m.l - m.r), bw = (W - m.l - m.r) / n;
  const Y = (v: number) => m.t + ((yTop - v) / (yTop + yBot)) * (H - m.t - m.b);
  const ticks: number[] = []; for (let v = -yBot; v <= yTop + 1e-9; v += step) ticks.push(Math.round(v * 100) / 100);
  const hour = (i: number) => new Date(dispatch[i].timestamp).getHours();
  const line = dispatch.map((_, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(load[i] ?? 0).toFixed(1)} L${(X(i) + bw).toFixed(1)},${Y(load[i] ?? 0).toFixed(1)}`).join("");
  const onMove = (e: React.PointerEvent) => { const r = box.current!.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W; setHover(Math.min(Math.max(Math.floor(((px - m.l) / (W - m.l - m.r)) * n), 0), n - 1)); };
  const h = hover;
  return (
    <div style={{ position: "relative" }} ref={box} onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Hourly microgrid sources: solar, wind, battery and grid stacked against the demand line">
        {ticks.map((v) => (<g key={v}><line className="grid" x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} /><text x={m.l - 8} y={Y(v) + 4} textAnchor="end">{v}</text></g>))}
        <text x={m.l} y={11}>kW</text>
        {dispatch.map((d, i) => {
          let acc = 0;
          return (<g key={i}>
            {SRCS.map(([, c, get], k) => { const v = get(d), y0 = Y(acc); acc += v; return v > 0.01 ? <rect key={k} x={X(i)} y={Y(acc)} width={Math.max(bw - 0.5, 0.6)} height={y0 - Y(acc)} fill={c} opacity={h === i ? 1 : 0.88} /> : null; })}
            {d.charge_kw > 0.01 && <rect x={X(i)} y={Y(0)} width={Math.max(bw - 0.5, 0.6)} height={Y(-d.charge_kw) - Y(0)} fill="var(--ml)" opacity={0.3} />}
            {d.unserved_kw > 0.01 && <rect x={X(i)} y={Y(acc + d.unserved_kw)} width={Math.max(bw - 0.5, 0.6)} height={Y(acc) - Y(acc + d.unserved_kw)} fill="var(--bad)" opacity={0.5} />}
          </g>);
        })}
        <path d={line} fill="none" stroke="var(--ink)" strokeWidth={1.8} />
        <line x1={m.l} x2={W - m.r} y1={Y(0)} y2={Y(0)} stroke="var(--ink)" opacity={0.8} />
        {dispatch.map((_, i) => i % 6 === 0 && <text key={i} x={X(i)} y={H - m.b + 18} textAnchor="middle" style={{ fontSize: 12 }}>{String(hour(i)).padStart(2, "0")}:00</text>)}
        {h != null && <line x1={X(h) + bw / 2} x2={X(h) + bw / 2} y1={m.t} y2={H - m.b} stroke="var(--ink)" strokeWidth={1} opacity={0.5} />}
      </svg>
      {h != null && (
        <div className="tip" style={{ left: `clamp(8px, calc(${((X(h) + bw / 2) / W) * 100}% - 90px), calc(100% - 200px))`, top: 6 }}>
          <b>{String(hour(h)).padStart(2, "0")}:00</b><br />Demand <b>{(load[h] ?? 0).toFixed(0)}</b> kW<br />
          Solar <b>{dispatch[h].solar_kw.toFixed(0)}</b> · Wind <b>{dispatch[h].wind_kw.toFixed(0)}</b><br />
          Battery <b>{(dispatch[h].discharge_kw - dispatch[h].charge_kw).toFixed(0)}</b> · Grid <b>{dispatch[h].grid_import_kw.toFixed(0)}</b><br />
          Charge level <b>{dispatch[h].soc_pct.toFixed(0)}</b>%{dispatch[h].unserved_kw > 0.01 ? <><br />Unserved <b>{dispatch[h].unserved_kw.toFixed(0)}</b> kW</> : null}
        </div>
      )}
      <div className="legend" style={{ marginTop: 6 }}>
        {SRCS.map(([n2, c]) => <span key={n2}><i style={{ background: c, height: 10, width: 10 }} />{n2}</span>)}
        <span><i style={{ background: "var(--ml)", opacity: 0.3, height: 10, width: 10 }} />Battery charging (below axis)</span>
        <span><i style={{ background: "var(--bad)", opacity: 0.5, height: 10, width: 10 }} />Unserved</span>
        <span><i style={{ background: "var(--ink)" }} />Demand</span>
      </div>
    </div>
  );
}
