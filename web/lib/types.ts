export type State = "NSW" | "VIC" | "QLD" | "SA" | "WA" | "TAS" | "NT" | "ACT" | "OT";
export const STATES: State[] = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT", "OT"];

export type Coverage = "fundamentals_market" | "fundamentals" | "insufficient";
export const COVERAGES: Coverage[] = ["fundamentals_market", "fundamentals", "insufficient"];

export type SuburbRow = {
  sal_code: string;
  name: string;
  state: State;
  slug: string;
  propapp_score: number | null;
  fundamentals_score: number | null;
  market_score: number | null;
  coverage: Coverage | null;
  top_drivers: string[];
  watch_outs: string[];
  as_of: string | null;
  median_price: number | null;
  dwelling_type: "house" | "unit" | null;
  gross_yield: number | null;
  population_growth_3y: number | null;
  supply_pressure: number | null;
  market_reason: string | null;
};

export type HistoryPoint = {
  as_of: string;
  propapp_score: number | null;
  fundamentals_score: number | null;
  market_score: number | null;
};

export type FactorRow = {
  sal_code: string;
  factor: string;
  layer: "fundamentals" | "market";
  raw_value: number | null;
  percentile: number;
  weight: number;
};

export type Freshness = {
  id: string;
  name: string;
  attribution: string | null;
  licence: string | null;
  last_success: string | null;
  cadence_days: number;
  is_stale: boolean;
};

export type BacktestRow = {
  model_version: string;
  horizon_months: number;
  split: "train" | "holdout";
  spearman: number | null;
  top_decile_excess: number | null;
  n_dates: number;
  run_at: string;
};
