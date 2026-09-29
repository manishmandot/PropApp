import pandas as pd

from propapp_pipeline.scoring.explain import TEMPLATES, explain
from propapp_pipeline.scoring.factors import FACTORS


def rows(*items):
    return pd.DataFrame([{"suburb_code": "a", "factor": f, "layer": FACTORS[f].layer,
                          "percentile": p, "weight": w, "contribution": w * p}
                         for f, p, w in items])


RAW = pd.DataFrame({"population_growth_3y": [0.021], "supply_pressure": [4.0],
                    "median_household_income": [2100.0], "unemployment_rate": [3.1],
                    "gross_yield": [0.041], "owner_occupier_share": [0.7]}, index=["a"])


def test_every_factor_has_template():
    assert set(TEMPLATES) == set(FACTORS)
    for text in TEMPLATES.values():
        assert text.format(raw=0.05, pct=62.0)


def test_drivers_and_watch_outs_ordered():
    out = explain(rows(("population_growth_3y", 90, 0.3), ("supply_pressure", 80, 0.2),
                       ("median_household_income", 70, 0.15), ("owner_occupier_share", 60, 0.15),
                       ("unemployment_rate", 20, 0.2), ("gross_yield", 45, 0.5)), RAW)
    drivers, watch = out.loc["a", "top_drivers"], out.loc["a", "watch_outs"]
    assert len(drivers) == 3 and drivers[0].startswith("Population grew 2.1% a year")
    assert "higher than 90% of suburbs" in drivers[0]
    assert len(watch) == 2 and watch[0].startswith("Unemployment of 3.1%")


def test_neutral_factor_excluded():
    out = explain(rows(("population_growth_3y", 50, 1.0)), RAW)
    assert out.loc["a", "top_drivers"] == [] and out.loc["a", "watch_outs"] == []
