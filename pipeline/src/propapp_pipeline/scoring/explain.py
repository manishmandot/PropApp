"""Plain-English top drivers and watch-outs per suburb (spec §5.4)."""
import pandas as pd

MAX_ITEMS = 3
STATE = " in the state"

# `pct` is the factor's percentile after direction is applied (higher is always better).
TEMPLATES: dict[str, str] = {
    "population_growth_3y":
        "Population grew {raw:.1%} a year over 3 years (higher than {pct:.0f}% of suburbs)",
    "supply_pressure":
        "{raw:.0f} new dwellings approved per 1,000 homes in 12 months "
        "(less new supply than {pct:.0f}% of suburbs)",
    "median_household_income":
        "Median household income of ${raw:,.0f} a week (higher than {pct:.0f}% of suburbs)",
    "unemployment_rate":
        "Unemployment of {raw:.1f}% (lower than {pct:.0f}% of suburbs)",
    "unemployment_change":
        "Unemployment moved {raw:+.1f} points over 12 months "
        "(a better trend than {pct:.0f}% of suburbs)",
    "owner_occupier_share":
        "{raw:.0%} of homes are owner-occupied (more than {pct:.0f}% of suburbs)",
    "price_growth_12m":
        "Median price moved {raw:+.1%} over 12 months (stronger than {pct:.0f}% of suburbs"
        + STATE + ")",
    "momentum":
        "Recent price growth runs {raw:+.1%} a year versus the 12-month trend "
        "(stronger momentum than {pct:.0f}% of suburbs" + STATE + ")",
    "gross_yield":
        "Gross rental yield of {raw:.1%} (higher than {pct:.0f}% of suburbs" + STATE + ")",
    "rent_growth_12m":
        "Rents moved {raw:+.1%} over 12 months (stronger than {pct:.0f}% of suburbs"
        + STATE + ")",
    "sales_volume_change":
        "Sales volume moved {raw:+.0%} over 12 months (stronger demand than {pct:.0f}% of "
        "suburbs" + STATE + ")",
}




def explain(factors: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    """Up to 3 drivers (largest positive effect) and watch-outs (most negative effect).

    Effect = within-layer weight × (percentile − 50): how much a factor lifts or drags
    the layer score relative to an average suburb.
    """
    raw_long = raw.rename_axis("suburb_code").stack().rename("raw").reset_index()
    raw_long = raw_long.rename(columns={raw_long.columns[1]: "factor"})
    f = factors.assign(effect=factors["weight"] * (factors["percentile"] - 50))
    f = f.merge(raw_long, on=["suburb_code", "factor"], how="inner")
    f = f[f["effect"] != 0]
    f = f.assign(text=[TEMPLATES[r.factor].format(raw=r.raw, pct=r.percentile)
                       for r in f.itertuples()])
    out = pd.DataFrame(index=pd.Index(factors["suburb_code"].unique(), name="suburb_code"))
    positive = f[f["effect"] > 0].sort_values("effect", ascending=False)
    negative = f[f["effect"] < 0].sort_values("effect")
    out["top_drivers"] = positive.groupby("suburb_code")["text"].agg(
        lambda t: list(t)[:MAX_ITEMS]).reindex(out.index)
    out["watch_outs"] = negative.groupby("suburb_code")["text"].agg(
        lambda t: list(t)[:MAX_ITEMS]).reindex(out.index)
    for column in ("top_drivers", "watch_outs"):
        out[column] = out[column].apply(lambda v: v if isinstance(v, list) else [])
    return out
