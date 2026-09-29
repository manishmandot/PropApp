from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

import psycopg

from propapp_pipeline.models import METRICS, GeoValue, Kind, Observation, Period


@dataclass(frozen=True)
class Correspondence:
    from_geography: str
    from_code: str
    sal_code: str
    weight: float
    ratio: float


class CorrespondenceIndex:
    def __init__(self, sal_codes: set[str] | None = None) -> None:
        self._by_source: dict[tuple[str, str], list[Correspondence]] = defaultdict(list)
        self.sal_codes = sal_codes

    @classmethod
    def from_rows(
        cls, rows: Iterable[Correspondence], sal_codes: set[str] | None = None
    ) -> "CorrespondenceIndex":
        """`sal_codes` limits SAL pass-through values to known suburbs (None allows any)."""
        index = cls(sal_codes)
        for row in rows:
            index._by_source[(row.from_geography, row.from_code)].append(row)
        return index

    @classmethod
    def load(cls, conn: psycopg.Connection) -> "CorrespondenceIndex":
        rows = conn.execute(
            "select from_geography, from_code, sal_code, weight, ratio "
            "from data.geo_correspondences"
        )
        sal_codes = {r[0] for r in conn.execute("select sal_code from data.suburbs")}
        return cls.from_rows((Correspondence(*r) for r in rows), sal_codes)

    def is_known_sal(self, code: str) -> bool:
        return self.sal_codes is None or code in self.sal_codes

    def targets(self, geography: str, code: str) -> list[Correspondence]:
        return self._by_source.get((geography, code), [])


@dataclass
class AllocationResult:
    observations: list[Observation]
    matched: int
    total: int


def allocate(
    values: Iterable[GeoValue], index: CorrespondenceIndex, source: str
) -> AllocationResult:
    """Allocate area values to SAL suburbs.

    Additive metrics are split by ratio; intensive metrics become the weight-averaged
    value of the source areas overlapping each suburb. SAL values pass straight through.
    """
    observations: list[Observation] = []
    additive: dict[tuple[str, str, Period, str], float] = defaultdict(float)
    weighted: dict[tuple[str, str, Period, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    matched = total = 0

    for v in values:
        total += 1
        if v.geography == "SAL":
            if not index.is_known_sal(v.code):
                continue
            matched += 1
            observations.append(Observation(v.code, v.metric, v.period, v.value, source, "SAL"))
            continue
        targets = index.targets(v.geography, v.code)
        if not targets:
            continue
        matched += 1
        intensive = METRICS[v.metric].kind is Kind.INTENSIVE
        for t in targets:
            key = (t.sal_code, v.metric, v.period, v.geography)
            if intensive:
                weighted[key][0] += v.value * t.weight
                weighted[key][1] += t.weight
            else:
                additive[key] += v.value * t.ratio

    for (sal, metric, period, geography), value in additive.items():
        observations.append(Observation(sal, metric, period, value, source, geography))
    for (sal, metric, period, geography), (numerator, weight) in weighted.items():
        if weight > 0:
            observations.append(
                Observation(sal, metric, period, numerator / weight, source, geography))
    return AllocationResult(observations, matched, total)
