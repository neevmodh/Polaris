"use client";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

export type Api<T> = { data: T | null; error: string | null; loading: boolean };
type Settled<T> = { data: T | null; error: string | null; key: string | null };

/** POST `body` to `url` (debounced). Keeps the last good result while a new request is in flight. */
export function usePost<T>(url: string, body: unknown, opts: { debounce?: number; enabled?: boolean } = {}): Api<T> {
  const { debounce = 250, enabled = true } = opts;
  const key = JSON.stringify(body);
  const [s, setS] = useState<Settled<T>>({ data: null, error: null, key: null });
  useEffect(() => {
    if (!enabled) return;
    const ctl = new AbortController();
    const t = setTimeout(async () => {
      try {
        const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: key, signal: ctl.signal });
        const j = await r.json();
        setS((p) => (r.ok ? { data: j as T, error: null, key } : { data: p.data, error: j.error ?? `Request failed (${r.status})`, key }));
      } catch (e) {
        if ((e as Error).name !== "AbortError") setS((p) => ({ data: p.data, error: "Cannot reach the server", key }));
      }
    }, debounce);
    return () => { clearTimeout(t); ctl.abort(); };
  }, [url, key, debounce, enabled]);
  return { data: s.data, error: s.error, loading: enabled && s.key !== key };
}

export function useGet<T>(url: string): Api<T> {
  const [s, setS] = useState<Settled<T>>({ data: null, error: null, key: null });
  useEffect(() => {
    let live = true;
    fetch(url).then(async (r) => {
      const j = await r.json();
      if (live) setS(r.ok ? { data: j, error: null, key: url } : { data: null, error: j.error ?? "Request failed", key: url });
    }).catch(() => live && setS({ data: null, error: "Cannot reach the server", key: url }));
    return () => { live = false; };
  }, [url]);
  return { data: s.data, error: s.error, loading: s.key !== url };
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
