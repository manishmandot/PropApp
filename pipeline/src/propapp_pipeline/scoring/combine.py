"""Percentile normalisation and layer combination (spec §5.2–5.3)."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from propapp_pipeline.scoring.factors import FACTORS
from propapp_pipeline.scoring.weights import Weights

WINSOR = (0.01, 0.99)
EPSILON = 1e-9
LAYERS = ("fundamentals", "market")


def _rank(values: pd.Series, direction: str) -> pd.Series:
    present = values.dropna()
    if present.empty:
        return values
    low, high = present.quantile(WINSOR[0]), present.quantile(WINSOR[1])
    ranks = present.clip(low, high).rank(method="average")
    n = len(present)
    pct = (ranks - 1) / (n - 1) * 100 if n > 1 else pd.Series(50.0, index=present.index)
    if direction == "lower":
        pct = 100 - pct
    return pct.reindex(values.index)


def percentiles(raw: pd.DataFrame, groups: pd.Series | None = None) -> pd.DataFrame:
    """Winsorise at 1/99 and rank each factor 0–100 (inverted for `lower` factors).

    With `groups` (e.g. state per suburb), each group is winsorised and ranked on its own.
    """
    out = pd.DataFrame(index=raw.index, columns=raw.columns, dtype=float)
    for column in raw.columns:
        direction = FACTORS[column].direction
        values = raw[column].astype(float)
        if groups is None:
            out[column] = _rank(values, direction)
        else:
            keys = groups.reindex(raw.index)
            for _, members in values.groupby(keys):
                out.loc[members.index, column] = _rank(members, direction)
    return out


@dataclass
class Combined:
    scores: pd.DataFrame   # index suburb; fundamentals/market/propapp score, coverage
    factors: pd.DataFrame  # long: suburb_code, factor, layer, percentile, weight, contribution


def _layer(pct: pd.DataFrame, layer: str, weights: Weights) -> tuple[pd.Series, pd.DataFrame]:
    w = weights.layer(layer)
    long = (pct.reindex(columns=list(w)).rename_axis("suburb_code").reset_index()
            .melt(id_vars="suburb_code", var_name="factor", value_name="percentile")
            .dropna(subset=["percentile"]))
    long["percentile"] = long["percentile"].astype(float)
    long["weight"] = long["factor"].map(w)
    present = long.groupby("suburb_code")["weight"].transform("sum")
    long = long[(1 - present <= weights.max_missing_weight + EPSILON) & (present > 0)]
    long["weight"] = long["weight"] / long.groupby("suburb_code")["weight"].transform("sum")
    long["contribution"] = long["weight"] * long["percentile"]
    long["layer"] = layer
    score = long.groupby("suburb_code")["contribution"].sum()
    return score, long


def combine(pct_fund: pd.DataFrame, pct_market: pd.DataFrame, weights: Weights) -> Combined:
    fund_score, fund_factors = _layer(pct_fund, "fundamentals", weights)
    market_score, market_factors = _layer(pct_market, "market", weights)
    index = pct_fund.index.union(pct_market.index)
    scores = pd.DataFrame({
        "fundamentals_score": fund_score.reindex(index),
        "market_score": market_score.reindex(index),
    }, index=index, dtype=float)
    has_fund = scores["fundamentals_score"].notna()
    has_market = scores["market_score"].notna()
    blend = weights.blend_fundamentals
    scores["propapp_score"] = np.where(
        has_fund & has_market,
        blend * scores["fundamentals_score"] + (1 - blend) * scores["market_score"],
        scores["fundamentals_score"])
    scores["coverage"] = np.select(
        [~has_fund, has_market], ["insufficient", "fundamentals_market"], "fundamentals")
    scores.index.name = "suburb_code"
    factors = pd.concat([fund_factors, market_factors], ignore_index=True)
    factors = factors[factors["suburb_code"].isin(scores.index[has_fund])]
    columns = ["suburb_code", "factor", "layer", "percentile", "weight", "contribution"]
    return Combined(scores, factors[columns].reset_index(drop=True))
