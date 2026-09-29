import pytest
import yaml

from propapp_pipeline.scoring.factors import FACTORS
from propapp_pipeline.scoring.weights import WEIGHTS_DIR, load_weights


def test_v1_loads():
    w = load_weights(WEIGHTS_DIR / "v1.yaml")
    assert w.model_version == "v1" and w.thin_market_min_sales == 20
    assert w.market_lag_months == 3 and w.market_max_age_months == 6
    assert set(w.fundamentals) | set(w.market) == set(FACTORS)
    assert w.fundamentals["population_growth_3y"] == 0.30


def test_factor_directions():
    assert FACTORS["supply_pressure"].direction == "lower"
    assert FACTORS["gross_yield"].layer == "market"
    assert len(FACTORS) == 11


def _write(tmp_path, **changes):
    data = yaml.safe_load((WEIGHTS_DIR / "v1.yaml").read_text())
    for section, values in changes.items():
        data[section] = values
    path = tmp_path / "v9.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_weights_must_sum_to_one(tmp_path):
    data = yaml.safe_load((WEIGHTS_DIR / "v1.yaml").read_text())
    fundamentals = dict(data["fundamentals"], population_growth_3y=0.20)
    with pytest.raises(ValueError, match="fundamentals"):
        load_weights(_write(tmp_path, fundamentals=fundamentals))


def test_factor_in_wrong_layer_rejected(tmp_path):
    data = yaml.safe_load((WEIGHTS_DIR / "v1.yaml").read_text())
    fundamentals = {**data["fundamentals"], "gross_yield": 0.0}
    with pytest.raises(ValueError, match="gross_yield"):
        load_weights(_write(tmp_path, fundamentals=fundamentals))


def test_negative_weight_rejected(tmp_path):
    data = yaml.safe_load((WEIGHTS_DIR / "v1.yaml").read_text())
    market = dict(data["market"], momentum=-0.2, gross_yield=0.65)
    with pytest.raises(ValueError, match="negative"):
        load_weights(_write(tmp_path, market=market))
