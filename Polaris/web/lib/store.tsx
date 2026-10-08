"use client";
import { useSyncExternalStore, type ReactNode } from "react";
import type { CalcInputs, DispatchSaving, MlEstimate, Scenario, Scenarios } from "./types";

export const EXAMPLE: CalcInputs = {
  fuel: { diesel_l: 84000, petrol_l: 0, lpg_kg: 0, natural_gas_m3: 0 },
  kwh: 500000, td_loss: 0, spend_lakh: { steel: 50, freight: 40, it_services: 30 },
};
export const EMPTY: CalcInputs = { fuel: { diesel_l: 0, petrol_l: 0, lpg_kg: 0, natural_gas_m3: 0 }, kwh: 0, td_loss: 0, spend_lakh: {} };

/** Tiny external store: inputs and saved scenarios persist in localStorage, the ML estimate lives for the session.
 *  useSyncExternalStore keeps server and first client render identical, then switches to saved values. */
const KEY = "scope.inputs.v1", SKEY = "scope.scenarios.v1", DKEY = "scope.dispatch.v1";
type Snap = { inputs: CalcInputs; ml: MlEstimate | null; scenarios: Scenarios; dispatch: DispatchSaving | null };
let snap: Snap | null = null;
const listeners = new Set<() => void>();
const SERVER: Snap = { inputs: EXAMPLE, ml: null, scenarios: { A: null, B: null }, dispatch: null };

function sane(i: unknown): CalcInputs {
  const o = (i ?? {}) as Partial<CalcInputs>;
  return { fuel: { ...EXAMPLE.fuel, ...(o.fuel ?? {}) }, kwh: Number(o.kwh) >= 0 ? Number(o.kwh) : 0,
           td_loss: Math.min(Math.max(Number(o.td_loss) || 0, 0), 0.25), spend_lakh: { ...(o.spend_lakh ?? {}) } };
}
function read(): Snap {
  if (snap) return snap;
  let inputs = EXAMPLE, scenarios: Scenarios = { A: null, B: null };
  try { const s = localStorage.getItem(KEY); if (s) inputs = sane(JSON.parse(s)); } catch {}
  try { const s = localStorage.getItem(SKEY); if (s) { const j = JSON.parse(s); scenarios = { A: j.A ? { ...j.A, inputs: sane(j.A.inputs) } : null, B: j.B ? { ...j.B, inputs: sane(j.B.inputs) } : null }; } } catch {}
  let dispatch: DispatchSaving | null = null;
  try { const raw = localStorage.getItem(DKEY); const d = raw ? JSON.parse(raw) : null; if (d && Number.isFinite(d.frac) && d.frac >= 0 && d.frac <= 1 && typeof d.label === "string") dispatch = d; } catch {}
  return (snap = { inputs, ml: null, scenarios, dispatch });
}
function write(next: Partial<Snap>) {
  snap = { ...read(), ...next };
  try {
    if (next.inputs) localStorage.setItem(KEY, JSON.stringify(next.inputs));
    if (next.scenarios) localStorage.setItem(SKEY, JSON.stringify(next.scenarios));
    if ("dispatch" in next) { if (next.dispatch) localStorage.setItem(DKEY, JSON.stringify(next.dispatch)); else localStorage.removeItem(DKEY); }
  } catch {}
  listeners.forEach((l) => l());
}
const subscribe = (cb: () => void) => { listeners.add(cb); return () => { listeners.delete(cb); }; };

/** Share links carry the inputs: base64url(JSON). */
export function encodeInputs(i: CalcInputs): string {
  return btoa(unescape(encodeURIComponent(JSON.stringify(i)))).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}
export function decodeInputs(s: string): CalcInputs | null {
  try { return sane(JSON.parse(decodeURIComponent(escape(atob(s.replaceAll("-", "+").replaceAll("_", "/")))))); } catch { return null; }
}

// Stable module-level actions: components can list them in effect dependencies without re-running on every render.
const setInputs = (inputs: CalcInputs) => write({ inputs });
const setMl = (ml: MlEstimate | null) => write({ ml });
const setDispatch = (dispatch: DispatchSaving | null) => write({ dispatch });
const saveScenario = (slot: "A" | "B", name: string) => {
  const sc: Scenario = { name, inputs: read().inputs, savedAt: new Date().toISOString() };
  write({ scenarios: { ...read().scenarios, [slot]: sc } });
};
const clearScenario = (slot: "A" | "B") => write({ scenarios: { ...read().scenarios, [slot]: null } });

export function useStore() {
  const s = useSyncExternalStore(subscribe, read, () => SERVER);
  return { inputs: s.inputs, ml: s.ml, scenarios: s.scenarios, dispatch: s.dispatch, setInputs, setMl, setDispatch, saveScenario, clearScenario };
}
export function StoreProvider({ children }: { children: ReactNode }) { return <>{children}</>; }
