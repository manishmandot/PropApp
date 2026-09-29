from dataclasses import dataclass
from pathlib import Path

import yaml

from propapp_pipeline.scoring.factors import FACTORS

WEIGHTS_DIR = Path(__file__).resolve().parents[3] / "scoring" / "weights"
TOLERANCE = 1e-9


@dataclass(frozen=True)
class Weights:
    model_version: str
    fundamentals: dict[str, float]
    market: dict[str, float]
    blend_fundamentals: float
    max_missing_weight: float
    thin_market_min_sales: int
    market_lag_months: int
    market_max_age_months: int

    def layer(self, name: str) -> dict[str, float]:
        return self.fundamentals if name == "fundamentals" else self.market


def validate_layer(name: str, weights: dict[str, float]) -> None:
    for key, weight in weights.items():
        if key not in FACTORS or FACTORS[key].layer != name:
            raise ValueError(f"{key} is not a {name} factor")
        if weight < 0:
            raise ValueError(f"{name}.{key} has a negative weight")
    total = sum(weights.values())
    if abs(total - 1) > TOLERANCE:
        raise ValueError(f"{name} weights sum to {total}, not 1")


def load_weights(path: Path) -> Weights:
    data = yaml.safe_load(Path(path).read_text())
    weights = Weights(
        model_version=Path(path).stem,
        fundamentals={k: float(v) for k, v in data["fundamentals"].items()},
        market={k: float(v) for k, v in data["market"].items()},
        blend_fundamentals=float(data["blend_fundamentals"]),
        max_missing_weight=float(data["max_missing_weight"]),
        thin_market_min_sales=int(data["thin_market_min_sales"]),
        market_lag_months=int(data["market_lag_months"]),
        market_max_age_months=int(data["market_max_age_months"]),
    )
    validate_layer("fundamentals", weights.fundamentals)
    validate_layer("market", weights.market)
    return weights


def weights_to_yaml(weights: Weights) -> str:
    return yaml.safe_dump({
        "fundamentals": weights.fundamentals,
        "market": weights.market,
        "blend_fundamentals": weights.blend_fundamentals,
        "max_missing_weight": weights.max_missing_weight,
        "thin_market_min_sales": weights.thin_market_min_sales,
        "market_lag_months": weights.market_lag_months,
        "market_max_age_months": weights.market_max_age_months,
    }, sort_keys=False)


def latest_weights_path(directory: Path = WEIGHTS_DIR) -> Path:
    versions = sorted(directory.glob("v*.yaml"), key=lambda p: int(p.stem[1:]))
    if not versions:
        raise FileNotFoundError(f"no weights files in {directory}")
    return versions[-1]
