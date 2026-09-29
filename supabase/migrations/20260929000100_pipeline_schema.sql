-- PropApp data pipeline schema.
-- Everything lives in schema `data`, which has no grants to anon/authenticated,
-- so none of it is reachable through the Supabase API. The app gets views later.

create schema if not exists extensions;
create extension if not exists postgis with schema extensions;

create schema if not exists data;

create table data.suburbs (
    sal_code  text primary key,
    name      text not null,
    state     text not null,
    geom      extensions.geometry(MultiPolygon, 4326),
    area_sqkm numeric
);

create table data.geo_correspondences (
    from_geography text not null,
    from_code      text not null,
    sal_code       text not null references data.suburbs (sal_code) on delete cascade,
    weight         double precision not null,
    ratio          double precision not null,
    primary key (from_geography, from_code, sal_code)
);

create table data.observations (
    suburb_code        text not null references data.suburbs (sal_code) on delete cascade,
    metric             text not null,
    period_start       date not null,
    period_granularity text not null check (period_granularity in ('month', 'quarter', 'year')),
    value              double precision not null,
    source             text not null,
    source_geography   text not null,
    ingested_at        timestamptz not null default now(),
    primary key (source, metric, suburb_code, period_start, period_granularity)
);

create index observations_suburb_metric_idx on data.observations (suburb_code, metric);

create table data.ingestion_runs (
    id          bigserial primary key,
    source      text not null,
    started_at  timestamptz not null default now(),
    finished_at timestamptz,
    status      text not null check (status in ('running', 'success', 'failed')),
    rows_parsed integer,
    rows_written integer,
    match_rate  double precision,
    error       text,
    raw_keys    text[]
);

create index ingestion_runs_source_idx on data.ingestion_runs (source, started_at desc);

create table data.sources (
    id             text primary key,
    name           text not null,
    url            text,
    licence        text,
    attribution    text,
    commercial_use text not null check (commercial_use in ('confirmed', 'pending', 'prohibited')),
    cadence_days   integer not null
);

-- Address-level NSW sales. Never exposed; only suburb aggregates leave this table.
create table data.nsw_sales (
    dealing_number text not null,
    property_id    text not null,
    contract_date  date not null,
    price          numeric not null,
    is_strata      boolean not null,
    locality       text,
    postcode       text,
    address        text,
    sal_code       text references data.suburbs (sal_code) on delete set null,
    primary key (dealing_number, property_id)
);

create index nsw_sales_sal_date_idx on data.nsw_sales (sal_code, contract_date);
