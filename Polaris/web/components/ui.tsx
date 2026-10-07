"use client";
import { useState, type ReactNode } from "react";
import { useCountUp } from "@/lib/hooks";
import { fmtT } from "@/lib/format";

/** Sheet header: eyebrow, title and the question the sheet answers. */
export function PageHead({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <header className="head fade">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1 className="title">{title}</h1>
        {children && <p className="lede">{children}</p>}
      </div>
    </header>
  );
}

/** Jargon with a plain-language tooltip (hover or keyboard focus). */
export function Term({ children, tip }: { children: ReactNode; tip: string }) {
  return <span className="term" tabIndex={0} data-tip={tip}>{children}</span>;
}

export function Panel({ title, tick, right, children, className = "" }: { title: string; tick?: string; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-h"><span className="tick">{tick && <i style={{ background: tick }} />}{title}</span>{right}</div>
      <div className="panel-b">{children}</div>
    </section>
  );
}

/** Number field that lets you clear and retype (no stuck leading zeros), clamps to [0, max], and commits on every keystroke. */
export function NumInput({ id, value, onChange, max = 1e10, step = "any" }: { id: string; value: number; onChange: (v: number) => void; max?: number; step?: string }) {
  const [txt, setTxt] = useState<string | null>(null);        // non-null only while the user is editing
  const shown = txt ?? (Number.isFinite(value) ? String(value) : "");
  return (
    <input id={id} type="number" inputMode="decimal" min={0} max={max} step={step} value={shown}
      onFocus={() => setTxt(String(value))}
      onBlur={() => setTxt(null)}
      onKeyDown={(e) => { if (["-", "+", "e", "E"].includes(e.key)) e.preventDefault(); }}
      onChange={(e) => {
        setTxt(e.target.value);
        const v = e.target.value === "" ? 0 : Number(e.target.value);
        onChange(Number.isFinite(v) ? Math.min(Math.max(v, 0), max) : 0);
      }} />
  );
}

export function Num({ label, unit, value, onChange, hint, max = 1e10, step = "any", id }: {
  label: string; unit?: string; value: number; onChange: (v: number) => void; hint?: string; max?: number; step?: string; id?: string;
}) {
  const fid = id ?? `f-${label.replace(/\W+/g, "-").toLowerCase()}`;
  return (
    <div className="field">
      <label htmlFor={fid}>{label}{hint && <em>{hint}</em>}</label>
      <div className="inp">
        <NumInput id={fid} value={value} onChange={onChange} max={max} step={step} />
        {unit && <span className="unit">{unit}</span>}
      </div>
    </div>
  );
}

export function Slider({ label, value, min, max, step, onChange, format }: {
  label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void; format: (v: number) => string;
}) {
  const id = `s-${label.replace(/\W+/g, "-").toLowerCase()}`;
  return (
    <div className="field">
      <label htmlFor={id}>{label}<span className="rowval">{format(value)}</span></label>
      <input id={id} className="range" type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  );
}

/** Large figure that counts toward new values. Mounts only once a value exists, so first paint is the real number. */
export function BigNum({ value, unit, size }: { value: number; unit: string; size?: string }) {
  const v = useCountUp(value);
  return <div className="big" style={size ? { fontSize: size } : undefined}>{fmtT(v)}<small>{unit}</small></div>;
}

export function ErrorNote({ message }: { message: string | null }) {
  return message ? <div className="alert err" role="alert">{message}</div> : null;
}

/** Signed decimal field (coordinates): free typing, committed only when it parses to a finite number. */
export function CoordInput({ id, label, value, onChange, hint }: { id: string; label: string; value: number; onChange: (v: number) => void; hint?: string }) {
  const [txt, setTxt] = useState<string | null>(null);
  return (
    <div className="field">
      <label htmlFor={id}>{label}{hint && <em>{hint}</em>}</label>
      <div className="inp">
        <input id={id} inputMode="decimal" value={txt ?? String(value)} aria-invalid={txt !== null && !Number.isFinite(Number(txt))}
          onFocus={() => setTxt(String(value))} onBlur={() => setTxt(null)}
          onChange={(e) => { setTxt(e.target.value); const v = Number(e.target.value); if (e.target.value.trim() !== "" && Number.isFinite(v)) onChange(v); }} />
      </div>
    </div>
  );
}
