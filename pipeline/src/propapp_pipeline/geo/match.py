import re
from collections import defaultdict

import psycopg

from propapp_pipeline.geo.allocate import CorrespondenceIndex

_PARENTHETICAL = re.compile(r"\([^)]*\)")
_MT = re.compile(r"\bMT\b")


def normalise_name(name: str) -> str:
    name = _PARENTHETICAL.sub(" ", name.upper())
    name = _MT.sub("MOUNT", name)
    return " ".join(name.split())


class SuburbMatcher:
    """Matches locality names (plus optional postcode) to SAL codes within a state."""

    def __init__(self, index: CorrespondenceIndex) -> None:
        self._index = index
        self._candidates: dict[tuple[str, str], list[str]] = defaultdict(list)

    @classmethod
    def from_rows(
        cls, suburbs: list[tuple[str, str, str]], index: CorrespondenceIndex
    ) -> "SuburbMatcher":
        matcher = cls(index)
        for sal_code, name, state in suburbs:
            matcher._candidates[(normalise_name(name), state)].append(sal_code)
        return matcher

    @classmethod
    def load(cls, conn: psycopg.Connection, index: CorrespondenceIndex) -> "SuburbMatcher":
        rows = conn.execute("select sal_code, name, state from data.suburbs").fetchall()
        return cls.from_rows(rows, index)

    def match(self, name: str, state: str, postcode: str | None = None) -> str | None:
        candidates = self._candidates.get((normalise_name(name), state), [])
        if len(candidates) == 1:
            return candidates[0]
        if not candidates or not postcode:
            return None
        ratios = {t.sal_code: t.ratio for t in self._index.targets("POA", postcode.strip())}
        in_postcode = [c for c in candidates if c in ratios]
        if not in_postcode:
            return None
        return max(in_postcode, key=ratios.__getitem__)
