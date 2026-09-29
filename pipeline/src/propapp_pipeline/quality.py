from dataclasses import dataclass, field

from propapp_pipeline.adapters.base import NormaliseResult
from propapp_pipeline.models import METRICS

MAX_RANGE_EXAMPLES = 10


class QualityError(Exception):
    """A load failed its quality checks; nothing is written."""


@dataclass
class QualityReport:
    passed: bool
    failures: list[str] = field(default_factory=list)


def check(
    result: NormaliseResult,
    previous_rows: int | None,
    tolerance: float | None,
    min_match_rate: float = 0.98,
) -> QualityReport:
    failures: list[str] = []
    rows = len(result.observations)
    if previous_rows and tolerance is not None:
        change = abs(rows - previous_rows) / previous_rows
        if change > tolerance:
            failures.append(
                f"row count {rows} vs previous {previous_rows} is outside ±{tolerance:.0%}")
    match_rate = result.matched / result.total if result.total else 1.0
    if match_rate < min_match_rate:
        failures.append(
            f"match rate {match_rate:.1%} ({result.matched}/{result.total}) "
            f"below {min_match_rate:.0%}")
    out_of_range = [
        o for o in result.observations
        if not METRICS[o.metric].min <= o.value <= METRICS[o.metric].max
    ]
    if out_of_range:
        examples = ", ".join(f"{o.metric}={o.value} ({o.suburb_code}, {o.period.start})"
                             for o in out_of_range[:MAX_RANGE_EXAMPLES])
        failures.append(f"{len(out_of_range)} values out of range: {examples}")
    return QualityReport(not failures, failures)
