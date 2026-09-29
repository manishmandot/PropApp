-- PropApp scoring engine schema (spec §5). Like the pipeline tables, everything is in
-- schema `data` with no API grants; the web app gets views later.

create table data.score_runs (
    id             bigserial primary key,
    model_version  text not null,
    as_of          date not null,
    started_at     timestamptz not null default now(),
    finished_at    timestamptz,
    status         text not null check (status in ('running', 'success', 'failed')),
    suburbs_scored integer,
    error          text
);

-- One snapshot per suburb, model version and month (`as_of` is the month's first day;
-- `cutoff` is the date the data was cut at).
create table data.scores (
    suburb_code        text not null references data.suburbs (sal_code) on delete cascade,
    model_version      text not null,
    as_of              date not null,
    cutoff             date not null,
    run_id             bigint not null references data.score_runs (id),
    propapp_score      double precision,
    fundamentals_score double precision,
    market_score       double precision,
    coverage           text not null
        check (coverage in ('fundamentals_market', 'fundamentals', 'insufficient')),
    top_drivers        text[] not null default '{}',
    watch_outs         text[] not null default '{}',
    primary key (suburb_code, model_version, as_of)
);

create index scores_version_as_of_idx on data.scores (model_version, as_of);

-- Factor detail; kept for the latest snapshot per model version only.
create table data.score_factors (
    suburb_code   text not null,
    model_version text not null,
    as_of         date not null,
    factor        text not null,
    layer         text not null check (layer in ('fundamentals', 'market')),
    raw_value     double precision,
    percentile    double precision not null,
    weight        double precision not null,
    contribution  double precision not null,
    primary key (suburb_code, model_version, as_of, factor),
    foreign key (suburb_code, model_version, as_of)
        references data.scores (suburb_code, model_version, as_of) on delete cascade
);

create table data.backtest_results (
    id                bigserial primary key,
    run_at            timestamptz not null default now(),
    model_version     text not null,
    horizon_months    integer not null check (horizon_months in (12, 24)),
    split             text not null check (split in ('train', 'holdout')),
    spearman          double precision,
    top_decile_excess double precision,
    n_dates           integer not null,
    mean_suburbs      double precision
);
