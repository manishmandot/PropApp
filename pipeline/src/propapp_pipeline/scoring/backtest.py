"""NSW backtest and weight tuning (spec §5.5).

Scores are recomputed at past dates from data available then (the 2021 Census is treated
as fixed), and compared with the median price growth that followed.
"""
import math
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from propapp_pipeline.db import connect
from propapp_pipeline.scoring.combine import combine, percentiles
from propapp_pipeline.scoring.fundamentals import compute_fundamentals
from propapp_pipeline.scoring.market import compute_market
from propapp_pipeline.scoring.observations import (
    as_of_view,
    load_observations,
    load_suburb_states,
    value_at,
)
from propapp_pipeline.scoring.weights import WEIGHTS_DIR, Weights, weights_to_yaml

REPORTS_DIR = WEIGHTS_DIR.parent / "reports"
HORIZONS = (12, 24)
MIN_SUBURBS = 3
TOP_SHARE = 0.10
BACKTEST_STATE = "NSW"
FAR_FUTURE = date(2200, 1, 1)  # outcome lookups may use every observation
LIMITATIONS = """\
## Known limitations

- **Fixed Census.** The 2021 Census is the only Census loaded, so income, owner-occupier
  share and dwelling counts are treated as available at every backtest date (a small
  look-ahead before 2022).
- **Revisions.** Census and population figures are revised after release; the backtest
  uses current releases.
- **NSW late lodgements.** NSW sales history includes sales lodged after each backtest
  date, so past 12-month medians and counts are slightly more complete than they were
  at the time.
"""


def backtest_dates(first_year: int, last_year: int) -> list[date]:
    return [d for y in range(first_year, last_year + 1)
            for d in (date(y, 6, 30), date(y, 12, 31))]


def outcomes(future_view: pd.DataFrame, reference_month: pd.Series, dwelling: pd.Series,
             horizon_months: int) -> pd.Series:
    """Growth of the dominant type's 12-month median from L to L + horizon (future data)."""
    later = reference_month + pd.DateOffset(months=horizon_months)
    growth = {}
    for kind in ("house", "unit"):
        metric = f"median_sale_price_{kind}_12m"
        start = value_at(future_view, metric, reference_month)
        end = value_at(future_view, metric, later)
        growth[kind] = end / start.where(start > 0) - 1
    return growth["house"].where(dwelling == "house", growth["unit"])


def rank_metrics(score: pd.Series, outcome: pd.Series) -> tuple[float, float, int]:
    """Spearman correlation, top-decile excess median outcome, and suburbs compared."""
    both = pd.concat([score.rename("s"), outcome.rename("o")], axis=1).dropna()
    n = len(both)
    if n < MIN_SUBURBS:
        return math.nan, math.nan, n
    ranks = both.rank(method="average")
    rho = float(np.corrcoef(ranks["s"], ranks["o"])[0, 1])
    top = both.nlargest(max(1, math.ceil(n * TOP_SHARE)), "s")
    return rho, float(top["o"].median() - both["o"].median()), n


@dataclass
class Prepared:
    """One backtest date: percentiles (reused across weight candidates) and outcomes."""

    as_of: date
    pct_fund: pd.DataFrame
    pct_market: pd.DataFrame
    outcomes: dict[int, pd.Series]


def prepare(obs: pd.DataFrame, states: pd.Series, dates: list[date],
            weights: Weights) -> list[Prepared]:
    future_view = as_of_view(obs, FAR_FUTURE)
    nsw = states.index[states == BACKTEST_STATE]
    prepared = []
    for d in dates:
        view = as_of_view(obs, d, census_fixed=True)
        fundamentals = compute_fundamentals(view)
        market = compute_market(view, d, weights)
        pct_fund = percentiles(fundamentals)
        pct_market = percentiles(market.values, states)
        prepared.append(Prepared(
            d,
            pct_fund[pct_fund.index.isin(nsw)],
            pct_market[pct_market.index.isin(nsw)],
            {h: outcomes(future_view, market.reference_month, market.dwelling_type, h)
             for h in HORIZONS},
        ))
    return prepared


@dataclass
class DateMetrics:
    as_of: date
    spearman: float
    top_decile_excess: float
    suburbs: int


def evaluate(prepared: list[Prepared], weights: Weights, horizon: int) -> list[DateMetrics]:
    results = []
    for p in prepared:
        score = combine(p.pct_fund, p.pct_market, weights).scores["propapp_score"]
        rho, excess, n = rank_metrics(score, p.outcomes[horizon])
        results.append(DateMetrics(p.as_of, rho, excess, n))
    return results


def _mean(values: list[float]) -> float:
    finite = [v for v in values if not math.isnan(v)]
    return sum(finite) / len(finite) if finite else math.nan


def next_version(weights_dir: Path) -> str:
    numbers = [int(p.stem[1:]) for p in weights_dir.glob("v*.yaml") if p.stem[1:].isdigit()]
    return f"v{max(numbers, default=0) + 1}"


def tune(prepared: list[Prepared], weights: Weights, samples: int = 200, seed: int = 7,
         weights_dir: Path = WEIGHTS_DIR) -> Weights:
    """Best of `weights` and `samples` Dirichlet(1) draws by mean 12-month Spearman."""
    rng = np.random.default_rng(seed)
    candidates = [weights]
    for _ in range(samples):
        f = rng.dirichlet(np.ones(len(weights.fundamentals)))
        m = rng.dirichlet(np.ones(len(weights.market)))
        candidates.append(replace(
            weights,
            fundamentals=dict(zip(weights.fundamentals, map(float, f), strict=True)),
            market=dict(zip(weights.market, map(float, m), strict=True)),
        ))

    def fitness(w: Weights) -> float:
        value = _mean([m.spearman for m in evaluate(prepared, w, 12)])
        return -math.inf if math.isnan(value) else value

    best = max(candidates, key=fitness)
    return replace(best, model_version=next_version(weights_dir))


@dataclass
class BacktestReport:
    model_version: str
    rows: list[dict]


def _summary(prepared: list[Prepared], weights: Weights, split: str) -> list[dict]:
    rows = []
    for horizon in HORIZONS:
        metrics = [m for m in evaluate(prepared, weights, horizon) if not math.isnan(m.spearman)]
        rows.append({
            "model_version": weights.model_version, "horizon_months": horizon, "split": split,
            "spearman": _mean([m.spearman for m in metrics]),
            "top_decile_excess": _mean([m.top_decile_excess for m in metrics]),
            "n_dates": len(metrics),
            "mean_suburbs": _mean([float(m.suburbs) for m in metrics]),
        })
    return rows


def _report(weights: Weights, rows: list[dict], first: int, last: int, holdout: int) -> str:
    def fmt(v: float, spec: str) -> str:
        return "n/a" if v is None or math.isnan(v) else format(v, spec)

    lines = [
        f"# Backtest: {weights.model_version}", "",
        f"NSW suburbs, dates 30 June and 31 December {first}–{last}. Train: before {holdout}; "
        f"held out: {holdout} onward. Only held-out results should be quoted.", "",
        "| Split | Horizon | Spearman | Top-decile excess growth | Dates | Suburbs per date |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['split']} | {r['horizon_months']} months | {fmt(r['spearman'], '.3f')}"
                     f" | {fmt(r['top_decile_excess'], '+.1%')} | {r['n_dates']} | "
                     f"{fmt(r['mean_suburbs'], '.0f')} |")
    lines += ["", "## Weights", "", "```yaml", weights_to_yaml(weights).rstrip(), "```", "",
              LIMITATIONS]
    return "\n".join(lines)


def run_backtest(db_url: str, first_year: int, last_year: int, holdout_from: int,
                 weights: Weights, tune_samples: int | None, *,
                 reports_dir: Path = REPORTS_DIR,
                 weights_dir: Path = WEIGHTS_DIR) -> BacktestReport:
    with connect(db_url) as conn:
        obs, states = load_observations(conn), load_suburb_states(conn)
    dates = backtest_dates(first_year, last_year)
    prepared = prepare(obs, states, dates, weights)
    train = [p for p in prepared if p.as_of.year < holdout_from]
    holdout = [p for p in prepared if p.as_of.year >= holdout_from]
    if tune_samples:
        weights = tune(train, weights, tune_samples, weights_dir=weights_dir)
        weights_dir.mkdir(parents=True, exist_ok=True)
        (weights_dir / f"{weights.model_version}.yaml").write_text(weights_to_yaml(weights))
    rows = _summary(train, weights, "train") + _summary(holdout, weights, "holdout")
    with connect(db_url) as conn, conn.cursor() as cur:
        cur.executemany(
            "insert into data.backtest_results (model_version, horizon_months, split, spearman, "
            "top_decile_excess, n_dates, mean_suburbs) values (%(model_version)s, "
            "%(horizon_months)s, %(split)s, %(spearman)s, %(top_decile_excess)s, %(n_dates)s, "
            "%(mean_suburbs)s)",
            [{k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in r.items()}
             for r in rows])
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / f"{weights.model_version}-backtest.md").write_text(
        _report(weights, rows, first_year, last_year, holdout_from))
    return BacktestReport(weights.model_version, rows)
