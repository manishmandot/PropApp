-- Fixed seed for web tests: 4 suburbs covering every coverage state plus an unscored VIC
-- suburb, two monthly snapshots, one stale source and backtest rows.
insert into data.suburbs (sal_code, name, state, geom) values
  ('10001', 'Alpha', 'NSW', extensions.st_multi(extensions.st_geomfromtext(
      'POLYGON((151 -33, 151.02 -33, 151.02 -33.02, 151 -33.02, 151 -33))', 4326))),
  ('10002', 'Beta Heights', 'NSW', null),
  ('10003', 'Gamma (NSW)', 'NSW', null),
  ('20004', 'Delta', 'VIC', null);

insert into data.sources (id, name, attribution, licence, commercial_use, cadence_days) values
  ('abs_census', 'ABS Census 2021', 'Source: Australian Bureau of Statistics', 'CC BY 4.0', 'confirmed', 1826),
  ('nsw_vg_sales', 'NSW Valuer General sales', 'Contains data from the Valuer General NSW', 'Terms of use', 'pending', 7);

insert into data.ingestion_runs (source, started_at, finished_at, status) values
  ('abs_census', now() - interval '30 days', now() - interval '30 days', 'success'),
  ('nsw_vg_sales', now() - interval '40 days', now() - interval '40 days', 'success');

insert into data.observations (suburb_code, metric, period_start, period_granularity, value, source, source_geography) values
  ('10001', 'sales_count_house_12m', '2025-09-01', 'month', 60, 'nsw_vg_sales', 'SAL'),
  ('10001', 'sales_count_unit_12m', '2025-09-01', 'month', 10, 'nsw_vg_sales', 'SAL'),
  ('10001', 'median_sale_price_house_12m', '2025-09-01', 'month', 1250000, 'nsw_vg_sales', 'SAL');

insert into data.score_runs (id, model_version, as_of, started_at, finished_at, status, suburbs_scored) values
  (1, 'v1', '2025-11-01', now() - interval '31 days', now() - interval '31 days', 'success', 3),
  (2, 'v1', '2025-12-01', now() - interval '1 day', now() - interval '1 day', 'success', 3);

insert into data.scores (suburb_code, model_version, as_of, cutoff, run_id, propapp_score, fundamentals_score, market_score, coverage, top_drivers, watch_outs) values
  ('10001', 'v1', '2025-11-01', '2025-11-30', 1, 68, 70, 66, 'fundamentals_market', '{}', '{}'),
  ('10002', 'v1', '2025-11-01', '2025-11-30', 1, 51, 51, null, 'fundamentals', '{}', '{}'),
  ('10003', 'v1', '2025-11-01', '2025-11-30', 1, null, null, null, 'insufficient', '{}', '{}'),
  ('10001', 'v1', '2025-12-01', '2025-12-31', 2, 72.4, 75, 69.8, 'fundamentals_market',
     '{"Population grew 2.1% a year over 3 years (higher than 88% of suburbs)"}',
     '{"Unemployment of 5.2% (lower than 21% of suburbs)"}'),
  ('10002', 'v1', '2025-12-01', '2025-12-31', 2, 48.2, 48.2, null, 'fundamentals',
     '{"Median household income of $2,100 a week (higher than 80% of suburbs)"}', '{}'),
  ('10003', 'v1', '2025-12-01', '2025-12-31', 2, null, null, null, 'insufficient', '{}', '{}');

insert into data.score_factors (suburb_code, model_version, as_of, factor, layer, raw_value, percentile, weight, contribution) values
  ('10001', 'v1', '2025-12-01', 'population_growth_3y', 'fundamentals', 0.021, 88, 0.3, 26.4),
  ('10001', 'v1', '2025-12-01', 'supply_pressure', 'fundamentals', 6.5, 60, 0.2, 12),
  ('10001', 'v1', '2025-12-01', 'unemployment_rate', 'fundamentals', 5.2, 21, 0.1, 2.1),
  ('10001', 'v1', '2025-12-01', 'gross_yield', 'market', 0.038, 55, 0.25, 13.75),
  ('10001', 'v1', '2025-12-01', 'price_growth_12m', 'market', 0.06, 70, 0.25, 17.5),
  ('10002', 'v1', '2025-12-01', 'median_household_income', 'fundamentals', 2100, 80, 0.15, 12);

insert into data.backtest_results (model_version, horizon_months, split, spearman, top_decile_excess, n_dates, mean_suburbs) values
  ('v1', 12, 'train', 0.21, 0.031, 10, 850),
  ('v1', 24, 'train', 0.18, 0.052, 8, 840),
  ('v1', 12, 'holdout', 0.14, 0.019, 5, 870),
  ('v1', 24, 'holdout', 0.11, 0.027, 3, 860);

refresh materialized view api.suburbs;
