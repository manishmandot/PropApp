from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class Granularity(StrEnum):
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


@dataclass(frozen=True)
class Period:
    start: date
    granularity: Granularity

    def __post_init__(self) -> None:
        s = self.start
        if s.day != 1:
            raise ValueError(f"period must start on day 1, got {s}")
        if self.granularity is Granularity.QUARTER and s.month not in (1, 4, 7, 10):
            raise ValueError(f"quarter must start in Jan/Apr/Jul/Oct, got {s}")
        if self.granularity is Granularity.YEAR and s.month != 1:
            raise ValueError(f"year must start on 1 January, got {s}")

    @classmethod
    def month(cls, year: int, month: int) -> "Period":
        return cls(date(year, month, 1), Granularity.MONTH)

    @classmethod
    def quarter(cls, year: int, quarter: int) -> "Period":
        return cls(date(year, 3 * (quarter - 1) + 1, 1), Granularity.QUARTER)

    @classmethod
    def year(cls, year: int) -> "Period":
        return cls(date(year, 1, 1), Granularity.YEAR)


class Kind(StrEnum):
    ADDITIVE = "additive"
    INTENSIVE = "intensive"


@dataclass(frozen=True)
class MetricDef:
    name: str
    kind: Kind
    min: float
    max: float


def _defs(kind: Kind, lo: float, hi: float, *names: str) -> dict[str, MetricDef]:
    return {n: MetricDef(n, kind, lo, hi) for n in names}


ADD, INT = Kind.ADDITIVE, Kind.INTENSIVE

METRICS: dict[str, MetricDef] = {
    **_defs(ADD, 0, 250_000, "population", "population_census"),
    **_defs(ADD, 0, 120_000, "dwellings_total"),
    **_defs(ADD, 0, 5_000, "building_approvals_dwellings"),
    **_defs(ADD, 0, 50_000, "unemployed_count"),
    **_defs(ADD, 0, 200_000, "labour_force_count"),
    **_defs(INT, 0, 20_000, "median_household_income_weekly"),
    **_defs(INT, 0, 100, "median_age"),
    **_defs(INT, 0, 10, "avg_household_size"),
    **_defs(INT, 0, 1, "owner_occupier_share"),
    **_defs(ADD, 0, 10_000, "sales_count_house_12m", "sales_count_unit_12m"),
    **_defs(INT, 10_000, 50_000_000, "median_sale_price_house_12m", "median_sale_price_unit_12m",
            "median_sale_price_house_3m", "median_sale_price_unit_3m"),
    **_defs(INT, 50, 10_000, "median_weekly_rent_house_q", "median_weekly_rent_unit_q",
            "median_weekly_rent_all_q"),
    **_defs(ADD, 0, 10_000, "bonds_lodged_q"),
}


@dataclass(frozen=True)
class Observation:
    suburb_code: str
    metric: str
    period: Period
    value: float
    source: str
    source_geography: str

    def __post_init__(self) -> None:
        if self.metric not in METRICS:
            raise ValueError(f"unknown metric: {self.metric}")


@dataclass(frozen=True)
class GeoValue:
    """A value reported for some geography, before it is allocated to suburbs."""

    geography: str
    code: str
    metric: str
    period: Period
    value: float
