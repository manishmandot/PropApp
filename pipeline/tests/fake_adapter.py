"""A registered test adapter: 3 observations for seeded suburbs, configurable via options."""
from propapp_pipeline.adapters.base import Adapter, NormaliseResult, RawFile, register
from propapp_pipeline.models import Observation, Period

FAKE_CONFIG = {
    "name": "Fake source",
    "url": "https://example.test/fake.csv",
    "licence": "CC BY 4.0",
    "attribution": "Fake",
    "commercial_use": "confirmed",
    "cadence_days": 30,
}
CFG = {"sources": {"fake": FAKE_CONFIG}}
SUBURBS = ["10001", "10002", "10003"]


@register
class FakeAdapter(Adapter):
    source_id = "fake"

    def fetch(self, http, config):
        return [RawFile("fake.csv", b"a,b\n1,2\n")]

    def parse(self, raw):
        if self.options.get("raise_in_parse"):
            raise ValueError("bad file")
        return list(SUBURBS)

    def normalise(self, rows, ctx):
        value = float(self.options.get("value", 1.0))
        obs = [Observation(code, "population", Period.year(2024), value, "fake", "SAL")
               for code in rows]
        return NormaliseResult(obs, len(obs), len(obs))
