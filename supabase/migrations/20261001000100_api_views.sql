-- Read-only views for the public web app (spec §6.3). The app connects as `web_reader`,
-- which can read these views and nothing else. Views run with their owner's rights, so
-- web_reader needs no access to schema `data`.

create schema if not exists api;

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'web_reader') then
        create role web_reader nologin;
    end if;
end
$$;

-- The model version of the latest successful scoring run (no row before the first run).
create view api.current_model as
select model_version
from data.score_runs
where status = 'success'
order by finished_at desc nulls last, id desc
limit 1;

-- One row per suburb with its latest snapshot and key figures. Materialized because the
-- key figures come from millions of observations; `run_scoring` refreshes it.
create materialized view api.suburbs as
with latest as (
    select distinct on (s.suburb_code) s.*
    from data.scores s
    join api.current_model cm using (model_version)
    order by s.suburb_code, s.as_of desc
),
factors as (
    select f.suburb_code,
           max(f.raw_value) filter (where f.factor = 'gross_yield') as gross_yield,
           max(f.raw_value) filter (where f.factor = 'population_growth_3y') as population_growth_3y,
           max(f.raw_value) filter (where f.factor = 'supply_pressure') as supply_pressure
    from data.score_factors f
    join latest l using (suburb_code, model_version, as_of)
    group by f.suburb_code
),
latest_obs as (
    select distinct on (suburb_code, metric) suburb_code, metric, value
    from data.observations
    where metric in ('sales_count_house_12m', 'sales_count_unit_12m',
                     'median_sale_price_house_12m', 'median_sale_price_unit_12m')
    order by suburb_code, metric, period_start desc, source
),
dwelling as (
    select suburb_code,
           case when coalesce(max(value) filter (where metric = 'sales_count_house_12m'), 0)
                  >= coalesce(max(value) filter (where metric = 'sales_count_unit_12m'), 0)
                then 'house' else 'unit' end as dwelling_type
    from latest_obs
    where metric like 'sales_count_%'
    group by suburb_code
),
states_with_market as (
    select distinct sub.state
    from latest l join data.suburbs sub on sub.sal_code = l.suburb_code
    where l.market_score is not null
)
select sub.sal_code,
       sub.name,
       sub.state,
       sub.sal_code || '-'
           || trim(both '-' from regexp_replace(
                  lower(regexp_replace(sub.name, '\s*\([^)]*\)', '', 'g')), '[^a-z0-9]+', '-', 'g'))
           || '-' || lower(sub.state) as slug,
       l.propapp_score,
       l.fundamentals_score,
       l.market_score,
       l.coverage,
       coalesce(l.top_drivers, '{}') as top_drivers,
       coalesce(l.watch_outs, '{}') as watch_outs,
       l.as_of,
       price.value as median_price,
       d.dwelling_type,
       f.gross_yield,
       f.population_growth_3y,
       f.supply_pressure,
       case
           when l.market_score is not null then null
           when sm.state is null then 'No market data for this state yet'
           else 'Fewer than 20 sales in the last 12 months, or no recent sales data'
       end as market_reason
from data.suburbs sub
left join latest l on l.suburb_code = sub.sal_code
left join factors f on f.suburb_code = sub.sal_code
left join dwelling d on d.suburb_code = sub.sal_code
left join latest_obs price
       on price.suburb_code = sub.sal_code
      and price.metric = 'median_sale_price_' || d.dwelling_type || '_12m'
left join states_with_market sm on sm.state = sub.state;

create unique index suburbs_sal_code_idx on api.suburbs (sal_code);
create index suburbs_state_score_idx on api.suburbs (state, propapp_score desc nulls last);

create view api.score_history as
select s.suburb_code as sal_code, s.as_of, s.propapp_score, s.fundamentals_score, s.market_score
from data.scores s
join api.current_model cm using (model_version);

create view api.suburb_factors as
select f.suburb_code as sal_code, f.factor, f.layer, f.raw_value, f.percentile, f.weight
from data.score_factors f
join api.current_model cm using (model_version)
where f.as_of = (select max(as_of) from data.scores s where s.model_version = cm.model_version);

create view api.source_freshness as
select src.id, src.name, src.attribution, src.licence, runs.last_success, src.cadence_days,
       runs.last_success is null
           or runs.last_success < now() - make_interval(days => src.cadence_days) * 1.5
           as is_stale
from data.sources src
left join (
    select source, max(coalesce(finished_at, started_at)) as last_success
    from data.ingestion_runs
    where status = 'success'
    group by source
) runs on runs.source = src.id;

create view api.backtest_summary as
select distinct on (b.model_version, b.horizon_months, b.split)
       b.model_version, b.horizon_months, b.split, b.spearman, b.top_decile_excess,
       b.n_dates, b.run_at
from data.backtest_results b
join api.current_model cm using (model_version)
order by b.model_version, b.horizon_months, b.split, b.run_at desc;

create view api.suburb_shapes as
select sal_code,
       extensions.st_asgeojson(extensions.st_simplifypreservetopology(geom, 0.0005), 5)::json
           as geojson
from data.suburbs
where geom is not null;

grant usage on schema api to web_reader;
grant usage on schema extensions to web_reader;
grant select on all tables in schema api to web_reader;
