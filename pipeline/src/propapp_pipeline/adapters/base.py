from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any, ClassVar

import httpx
import psycopg

from propapp_pipeline.geo.allocate import CorrespondenceIndex
from propapp_pipeline.geo.match import SuburbMatcher
from propapp_pipeline.models import Observation
from propapp_pipeline.raw_store import RawFile

__all__ = ["REGISTRY", "Adapter", "NormaliseContext", "NormaliseResult", "RawFile", "register"]


@dataclass
class NormaliseResult:
    observations: list[Observation]
    matched: int
    total: int


@dataclass
class NormaliseContext:
    conn: psycopg.Connection
    index: CorrespondenceIndex
    matcher: SuburbMatcher
    http: httpx.Client | None
    source_config: dict
    today: date


class Adapter(ABC):
    """One public data source: fetch raw files, parse them, normalise to observations."""

    source_id: ClassVar[str]
    row_count_tolerance: ClassVar[float | None] = 0.25

    def __init__(self, **options: str) -> None:
        self.options = options

    @abstractmethod
    def fetch(self, http: httpx.Client, config: dict) -> list[RawFile]: ...

    @abstractmethod
    def parse(self, raw: list[RawFile]) -> list[Any]: ...

    @abstractmethod
    def normalise(self, rows: list[Any], ctx: NormaliseContext) -> NormaliseResult: ...


REGISTRY: dict[str, type[Adapter]] = {}


def register(cls: type[Adapter]) -> type[Adapter]:
    REGISTRY[cls.source_id] = cls
    return cls
