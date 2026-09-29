from dataclasses import dataclass
from typing import Literal

Layer = Literal["fundamentals", "market"]
Direction = Literal["higher", "lower"]


@dataclass(frozen=True)
class Factor:
    key: str
    layer: Layer
    direction: Direction


def _factors(layer: Layer, **directions: Direction) -> dict[str, Factor]:
    return {k: Factor(k, layer, d) for k, d in directions.items()}


FACTORS: dict[str, Factor] = {
    **_factors(
        "fundamentals",
        population_growth_3y="higher",
        supply_pressure="lower",
        median_household_income="higher",
        unemployment_rate="lower",
        unemployment_change="lower",
        owner_occupier_share="higher",
    ),
    **_factors(
        "market",
        price_growth_12m="higher",
        momentum="higher",
        gross_yield="higher",
        rent_growth_12m="higher",
        sales_volume_change="higher",
    ),
}

FUNDAMENTALS = [k for k, f in FACTORS.items() if f.layer == "fundamentals"]
MARKET = [k for k, f in FACTORS.items() if f.layer == "market"]
