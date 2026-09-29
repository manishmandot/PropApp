import { formatPct } from "@/lib/format";

/** Display names and raw-value formatting for the 11 scoring factors (spec §5.1). */
export const FACTORS: { key: string; label: string; format: (v: number) => string }[] = [
  { key: "population_growth_3y", label: "Population growth (a year, 3 yrs)", format: (v) => formatPct(v, true) },
  { key: "supply_pressure", label: "Dwellings approved per 1,000 homes", format: (v) => v.toFixed(1) },
  { key: "median_household_income", label: "Median household income (week)", format: (v) => `A$${Math.round(v).toLocaleString("en-AU")}` },
  { key: "unemployment_rate", label: "Unemployment rate", format: (v) => `${v.toFixed(1)}%` },
  { key: "unemployment_change", label: "Unemployment change (12 months)", format: (v) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1)} pts` },
  { key: "owner_occupier_share", label: "Owner-occupied homes", format: (v) => formatPct(v) },
  { key: "price_growth_12m", label: "Price growth (12 months)", format: (v) => formatPct(v, true) },
  { key: "momentum", label: "Momentum vs 12-month trend", format: (v) => formatPct(v, true) },
  { key: "gross_yield", label: "Gross rental yield", format: (v) => formatPct(v) },
  { key: "rent_growth_12m", label: "Rent growth (12 months)", format: (v) => formatPct(v, true) },
  { key: "sales_volume_change", label: "Sales volume change (12 months)", format: (v) => formatPct(v, true) },
];

