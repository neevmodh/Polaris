export type Meta = {
  fuels: { key: string; label: string; ef: number }[];
  scope3: { key: string; label: string; ghg: string; naics: number; ef_kg_per_usd: number }[];
  sigmas: { fuel: number; grid: number; spend: number };
  grid_ef: number; usd_to_inr: number; models_ready: boolean; data_source: string;
  sectors?: string[]; activities?: string[]; train_range?: { log_turnover: [number, number]; year: [number, number] };
};
export type Range = { p5: number; p50: number; p95: number };
export type Driver = { name: string; scope: number; share: number; tco2e_sd: number };
export type CalcResult = {
  point: Record<"scope1" | "scope2" | "scope3" | "total", number>;
  range: Record<"scope1" | "scope2" | "scope3" | "total", Range>;
  scope3_breakdown: { category: string; ghg_protocol: string; spend_inr: number; tco2e: number }[];
  drivers: Driver[];
};
export type Interval = { point: number; lo: number; hi: number; model: string };
export type PredictResult = { s1: Interval; s2: Interval; warnings: string[] };
export type Lever = { name: string; scope: number; abatement_t: number; cost_inr_per_t: number; grid_linked: boolean; cumulative_t: number; annual_net_cost_inr: number };
export type PathRow = { year: number; bau_p10: number; bau_p50: number; bau_p90: number; with_levers_p10: number; with_levers_p50: number; with_levers_p90: number; sbti_1p5C_line: number };
export type AbateResult = {
  baseline: { scope1: number; scope2: number; scope3: number; diesel_l: number; kwh: number };
  macc: Lever[]; pathway: PathRow[]; abated_2030_t: number; abated_2050_t: number; annual_net_cost_inr: number;
};
export type RunwayResult = {
  inputs: { stock_l: number; daily_l: number; delivery_day: number; cv: number; saving_frac: number; delay_days: number };
  nominal_runway_days: number;
  runway_days: { baseline: [number, number, number]; with_saving: [number, number, number] };
  p_ok_at_delivery: { baseline: number; with_saving: number };
  p_ok_with_delay: { baseline: number; with_saving: number };
  delay_curve: { delays: number[]; baseline: number[]; with_saving: number[] };
  saving_needed_for_target: number | null; target_p: number;
  diesel_to_delivery_l: { baseline: number; with_saving: number };
  co2_to_delivery_t: { baseline: number; with_saving: number };
  gap_days_median: number; assumptions: string;
};
export type ModelRow = { target: string; model: string; train_rmse_log?: number | null; cv_rmse_log?: number | null; rmse_log: number; r2_log: number; median_pct_error: number; overfit_ratio_test_over_train?: number | null; overfit_flag?: boolean | null };
export type TargetReport = {
  best_model: string; improvement_vs_baseline_rmse_pct: number; improvement_95ci_pct: [number, number];
  interval_method: string; interval_coverage_test: number; target_coverage: number; worst_sector_coverage: number; median_interval_factor: number;
  out_of_time_2024plus: { n: number; model_rmse_log: number; baseline_rmse_log: number } | null;
};
export type Report = { ready: boolean; metrics?: { data_source: string; alpha: number; features: string[]; s1: TargetReport; s2: TargetReport }; comparison?: ModelRow[]; plots?: string[] };
export type StressRow = { group: "accuracy" | "calibration" | "robustness" | "limits"; name: string; value: number; passed: boolean | null; detail: string };
export type Stress = { ready?: boolean; n_fresh_companies?: number; tests?: StressRow[]; passed?: number; total?: number };

export type CalcInputs = { fuel: Record<string, number>; kwh: number; td_loss: number; spend_lakh: Record<string, number> };
export type MlEstimate = { s1_t: number; s2_t: number; label: string; inputs?: unknown; fingerprint?: string; calculatedAt?: string | null };
export type Scenario = { name: string; inputs: CalcInputs; savedAt: string };
export type Scenarios = { A: Scenario | null; B: Scenario | null };

// ---- dispatch engine (SCOPE carbon/dispatch_eval results)
export type DispatchKey = "A" | "B" | "C";
export type DispatchMetrics = {
  name?: string; fuel_l: number; co2_t: number; fuel_cost_inr: number; generator_starts: number; generator_hours: number; generator_kwh: number;
  renewable_available_kwh: number; renewable_used_kwh: number; renewable_utilisation: number | null; curtailed_kwh: number; battery_throughput_kwh: number;
  demand_kwh: number; unmet_kwh: number; unmet_essential_kwh: number; shed_nonessential_kwh: number; flex_shifted_kwh: number; solves?: number; solve_seconds?: number;
  daily_fuel_l_p50: number; daily_fuel_l_p90: number; daily_fuel_cv: number;
};
export type ForecastScore = { mae: number; rmse: number; [k: string]: number };
export type ForecastRow = {
  lightgbm: ForecastScore; persistence: ForecastScore; seasonal_naive_24h: ForecastScore; climatology: ForecastScore;
  band_coverage_p20_p80: number; skill_vs_persistence: number; skill_vs_seasonal_naive_24h: number; n: number; mean_actual: number;
};
export type StressRun = {
  fuel_stock_daily: number[]; essential_unmet_daily_kwh: number[]; fuel_left_at_delivery_l: number; unmet_kwh: number; essential_unmet_kwh: number;
  essential_unmet_pct: number; shed_nonessential_kwh: number; flex_shifted_kwh: number; first_essential_unmet_day: number | null;
};
export type ModeRow = Pick<DispatchMetrics, "fuel_l" | "co2_t" | "fuel_cost_inr" | "generator_starts" | "renewable_utilisation" | "battery_throughput_kwh" | "unmet_kwh">;
export type DispatchProfile = {
  profile: { key: string; name: string; lat: number; lon: number; pv_kwp: number; wind_kw: number; battery_kwh: number; battery_kw: number; gen_kw: number; tank_l: number;
            base_kw: number; heat_kw_per_c: number; essential_frac: number; flexible_frac: number; fuel_price: number; gen_min_frac: number };
  weather_source: string; demand_source: string; split: Record<string, string>;
  forecast: Record<"demand" | "solar_cf" | "wind_cf", ForecastRow>;
  scenarios: Record<DispatchKey, DispatchMetrics>;
  monthly: Record<DispatchKey, { fuel_l: number[]; co2_t: number[]; renewable_used_kwh: number[]; demand_kwh: number[] }>;
  mode_compare: Record<string, { A: ModeRow; economy: ModeRow; green: ModeRow }>;
  stress: { start: string; days: number; delivery_day: number; tank_l: number; rule_based_daily_l: number; scenarios: Record<string, StressRun> };
};
export type DispatchSummary = { ready: boolean; profiles: Record<"polar" | "community", DispatchProfile> };
export type WeekSeries = { start: string; demand: number[]; pv_used: number[]; wind_used: number[]; discharge: number[]; charge: number[]; gen: number[]; soc: number[]; curtailed: number[]; fuel_l: number[]; unmet: number[] };
export type DispatchWeek = Record<DispatchKey, WeekSeries>;
export type DispatchSaving = { frac: number; label: string; profile?: string; savedAt?: string };

/* Task 1 (Atmos): regional greenhouse-gas histories and forecasts. */
export type AirCity = { name: string; station: string; latitude: number; longitude: number; unit: string; origin: string; scope: string; grid_bounds: number[]; last: string; source_rows: number; citation: string; license: string; url: string };
export type AirMeta = { cities: AirCity[]; models: string[]; horizons: number[]; gases: Record<string, { name: string; label: string; unit: string }> };
export type AirPoint = { date: string; value: number };
export type AirBand = { date: string; predicted: number; lower: number; upper: number };
export type AirScore = { model: string; mae: number; rmse: number; coverage_90: number; test_targets: number };
export type AirForecast = {
  city: string; station: string; unit: string; gas: string; selected: string; horizon: number; eval_horizon: number;
  latest: AirPoint & { date: string }; final: { value: number; date: string; lower: number; upper: number };
  mae: number; rmse: number; coverage: number; targets: number; persistence_mae: number; beats_persistence: boolean; skill_pct: number;
  metrics: AirScore[]; history: AirPoint[]; forecast: AirBand[]; importance: { feature: string; importance: number }[];
  split: { train_start: string; train_end_exclusive: string; test_start: string; training_rows: number; calibration_rows: number; test_rows: number };
  coverage_pct: number; first: string; last: string; scope: string; origin: string; citation: string; grid_bounds: number[];
};
export type AirAlerts = { unit: string; city: string; sigma: number; flagged: number; days: number; rows: { date: string; value: number; level: number | null; flag: boolean }[] };

/* NetZeroAI: grid-tied solar + wind + battery microgrid. */
export type GridKpis = { load_kwh: number; renewable_used_kwh: number; renewable_offered_kwh: number; renewable_spilled_kwh: number; renewable_utilization_pct: number; grid_import_kwh: number; grid_dependency_pct: number; grid_export_kwh: number; curtailment_kwh: number; unserved_kwh: number; grid_cost_rs: number; grid_co2_kg: number; critical_load_coverage_pct: number };
export type GridHour = { timestamp: string; solar_kw: number; wind_kw: number; charge_kw: number; discharge_kw: number; grid_import_kw: number; curtail_kw: number; unserved_kw: number; soc_pct: number };
export type GridForecastHour = { timestamp: string; solar_kw: number; wind_kw: number; load_kw: number; price: number; carbon: number };
export type GridPlan = { scenario: string; kpis: GridKpis; method: string; fallback_reason: string | null; dispatch: GridHour[]; forecast: GridForecastHour[]; forecast_is_trained: boolean };
export type GridMeta = { scenarios: string[]; config: Record<string, Record<string, number>>; accuracy: Record<string, { MAE: number; RMSE: number; baseline_MAE: number }>; data_ready: boolean; models_ready: boolean };
export type GridCompare = { rows: { scenario: string; kpis: GridKpis; method: string; fallback_reason: string | null }[] };
