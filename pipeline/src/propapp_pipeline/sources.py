from pathlib import Path

import psycopg
import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "sources.yaml"


def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    """Load sources.yaml: a `geo` section and a `sources` mapping keyed by adapter id."""
    return yaml.safe_load(Path(path).read_text())


def sync_sources(conn: psycopg.Connection, config: dict) -> None:
    for source_id, s in (config.get("sources") or {}).items():
        conn.execute(
            """
            insert into data.sources (id, name, url, licence, attribution, commercial_use,
                                      cadence_days)
            values (%s, %s, %s, %s, %s, %s, %s)
            on conflict (id) do update set name = excluded.name, url = excluded.url,
                licence = excluded.licence, attribution = excluded.attribution,
                commercial_use = excluded.commercial_use, cadence_days = excluded.cadence_days
            """,
            (source_id, s["name"], s.get("url") or s.get("page_url"), s["licence"],
             s["attribution"], s["commercial_use"], s["cadence_days"]),
        )
