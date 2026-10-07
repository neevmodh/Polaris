export type Kind = "forest" | "lake";
export type SceneInfo = {
  label: string; id: string; datetime: string; source: string; cloud_cover_scene_pct: number | null; processing_baseline: string | null;
  quality: string; crs: string; resolution_m: number; shape: [number, number]; clear_pct: number; bounds_wgs84: number[]; bands: string[];
};
export type CaseCard = {
  id: string; kind: Kind; name: string; location: string; before: SceneInfo; after: SceneInfo; size: [number, number];
  preset?: { bbox: number[]; before: string[]; after: string[] }; error?: string;
};
export type Confusion = { tn: number; fp: number; fn: number; tp: number };
export type Score = { precision: number; recall: number; f1: number; iou: number; average_precision: number; confusion_matrix: Confusion };
export type SatMetrics = {
  model: string; features: string[]; trained_samples: number; holdout_samples: number; holdout_positive_samples: number; training_positive_samples: number;
  spatial_split: string; holdout_bounds: string; reference: string; label_interval: string; rf: Score; ndvi_baseline: Score;
  feature_importance: Record<string, number>; probability_note: string; scene_ids: string[];
};
export type SatMeta = {
  cases: CaseCard[]; custom: { id: string; name: string; kind: Kind; bbox: number[] | null; before: string }[];
  forest_model: boolean; unet: boolean; metrics: SatMetrics | null; review_states: string[];
  presets: Record<Kind, { bbox: number[]; before: string[]; after: string[]; name: string }>;
};
export type Region = {
  region: number; area_ha: number; longitude: number; latitude: number; mean_index_change: number | null; mean_model_score: number | null;
  x: number; y: number; status: string; note: string;
};
export type Legend = { stops: [string, number][]; min: number; max: number };
export type Indicator = { indicator: string; meaning: string; before_median: number | null; after_median: number | null; change: number | null; units: string };
export type SatSummary = {
  analysis: string; method: string; region: string; observed_pair_pct: number; interpretation: string; parameters: Record<string, number>;
  observed_area_ha?: number; baseline_vegetation_area_ha?: number; baseline_support?: string; candidate_loss_area_ha?: number; alert_regions?: number;
  mean_ndvi_change?: number | null; before_open_water_ha?: number; after_open_water_ha?: number; common_water_ha?: number; algae_proxy_increase_ha?: number;
  indicators?: Indicator[]; comparison_support?: string;
};
export type SatAnalysis = {
  summary: SatSummary; layer: string; image: string; legend: Legend | null; size: [number, number]; regions: Region[]; region_total: number;
  reviewed: number; key: string; scores_available: boolean; prior_used: boolean | null; seconds: number;
};
export type SceneImages = { before: string; after: string; size: [number, number]; before_info: SceneInfo; after_info: SceneInfo };
export type FetchJob = { state: "running" | "done" | "error"; log: string[]; case: string; error: string | null };

export type Controls = {
  detector: "Trained random forest" | "NDVI screening baseline"; threshold: number; drop: number; vegetation: number; patches: number;
  water: "Spectral open-water mask" | "Pretrained U-Net"; mndwi: number; algae: number;
};
export const DEFAULT_CONTROLS: Controls = { detector: "Trained random forest", threshold: 0.5, drop: 0.2, vegetation: 0.6, patches: 4, water: "Spectral open-water mask", mndwi: 0, algae: 0.1 };

export const LAYERS: Record<Kind, { id: string; label: string; needs?: "scores" }[]> = {
  forest: [{ id: "alerts", label: "Loss alerts" }, { id: "rgb", label: "True colour" }, { id: "ndvi_change", label: "NDVI change" }, { id: "ml_score", label: "Model score", needs: "scores" }],
  lake: [{ id: "algae_change", label: "Algae proxy change" }, { id: "rgb", label: "True colour" }, { id: "algae", label: "Algae proxy" }, { id: "turbidity", label: "Turbidity proxy" }, { id: "water", label: "Water mask" }],
};

export async function satPost<T>(cmd: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const r = await fetch(`/api/sat/${cmd}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error ?? `Request failed (${r.status})`);
  return j as T;
}

export function downloadB64(name: string, mime: string, b64: string) {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: mime }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
