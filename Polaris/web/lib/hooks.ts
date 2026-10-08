"use client";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

export type Api<T> = { data: T | null; error: string | null; loading: boolean; proof?: string | null; snapshotKey?: string; calculatedAt?: string | null; version?: string | null; retry?: () => void };
type Settled<T> = { data: T | null; error: string | null; key: string | null; proof?: string | null; calculatedAt?: string | null; version?: string | null };

/** A result is visible only for the exact current request. Superseded requests cannot settle. */
export function usePost<T>(url: string, body: unknown, opts: { debounce?: number; enabled?: boolean } = {}): Api<T> {
  const { debounce = 250, enabled = true } = opts;
  const payload = JSON.stringify(body);
  const [revision, setRevision] = useState(0);
  const key = `${url}\n${payload}\n${revision}`;
  const [s, setS] = useState<Settled<T>>({ data: null, error: null, key: null });
  useEffect(() => {
    if (!enabled) return;
    const ctl = new AbortController();
    let live = true;
    const t = setTimeout(async () => {
      try {
        const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: payload, signal: ctl.signal });
        const j = await r.json();
        if (live) setS(r.ok ? { data: j as T, error: null, key, proof: r.headers.get("x-polaris-evidence"), calculatedAt: r.headers.get("x-polaris-calculated-at") ?? new Date().toISOString(), version: r.headers.get("x-polaris-version") } : { data: null, error: j.error ?? `Request failed (${r.status})`, key });
      } catch (e) {
        if (live && (e as Error).name !== "AbortError") setS({ data: null, error: "Cannot reach the server", key });
      }
    }, debounce);
    return () => { live = false; clearTimeout(t); ctl.abort(); };
  }, [url, key, payload, debounce, enabled]);
  const current = enabled && s.key === key;
  return { data: current ? s.data : null, error: current ? s.error : null, loading: enabled && !current, proof: current ? s.proof : null, snapshotKey: key, calculatedAt: current ? s.calculatedAt : null, version: current ? s.version : null, retry: () => setRevision(v => v + 1) };
}

export function useGet<T>(url: string): Api<T> {
  const [s, setS] = useState<Settled<T>>({ data: null, error: null, key: null });
  const [revision, setRevision] = useState(0);
  const key = `${url}\n${revision}`;
  useEffect(() => {
    let live = true;
    fetch(url).then(async (r) => {
      const j = await r.json();
      if (live) setS(r.ok ? { data: j, error: null, key } : { data: null, error: j.error ?? "Request failed", key });
    }).catch(() => live && setS({ data: null, error: "Cannot reach the server", key }));
    return () => { live = false; };
  }, [url, key]);
  return { data: s.key === key ? s.data : null, error: s.key === key ? s.error : null, loading: s.key !== key, retry: () => setRevision(v => v + 1) };
}

const mq = () => window.matchMedia("(prefers-reduced-motion: reduce)");
export function useReducedMotion(): boolean {
  return useSyncExternalStore((cb) => { const m = mq(); m.addEventListener("change", cb); return () => m.removeEventListener("change", cb); }, () => mq().matches, () => false);
}

/** Animate a number toward `target` (no animation when the user prefers reduced motion). */
export function useCountUp(target: number, ms = 600): number {
  const reduce = useReducedMotion();
  const [v, setV] = useState(target);
  const cur = useRef(target);
  useEffect(() => {
    if (reduce || !Number.isFinite(target)) return;
    const from = cur.current, t0 = performance.now(); let raf = 0;
    const tick = (now: number) => {
      const p = Math.min((now - t0) / ms, 1), e = 1 - Math.pow(1 - p, 3);
      cur.current = from + (target - from) * e; setV(cur.current);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms, reduce]);
  return reduce ? target : v;
}

/** Theme: explicit data-theme wins, otherwise the OS setting. */
export function useIsDark(): boolean {
  return useSyncExternalStore((cb) => {
    const m = window.matchMedia("(prefers-color-scheme: dark)"); m.addEventListener("change", cb);
    const o = new MutationObserver(cb); o.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => { m.removeEventListener("change", cb); o.disconnect(); };
  }, () => { const t = document.documentElement.dataset.theme; return t ? t === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches; }, () => false);
}
