import argparse
import logging
import sys
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

from propapp_pipeline.config import Settings
from propapp_pipeline.db import connect
from propapp_pipeline.geo.load import build_correspondences, load_suburbs, read_abs_table
from propapp_pipeline.http import download, make_client
from propapp_pipeline.raw_store import RawStore, SupabaseRawStore
from propapp_pipeline.runner import run_source
from propapp_pipeline.scoring.backtest import run_backtest
from propapp_pipeline.scoring.engine import run_scoring
from propapp_pipeline.scoring.weights import WEIGHTS_DIR, latest_weights_path, load_weights
from propapp_pipeline.sources import DEFAULT_CONFIG, load_config

MB = "MB_CODE_2021"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="propapp_pipeline")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="ingest one source")
    run.add_argument("source")
    run.add_argument("--years", help="year range for backfills, e.g. 2015-2025")
    run.add_argument("--option", action="append", default=[], metavar="KEY=VALUE")
    sub.add_parser("load-geo", help="load SAL suburbs and mesh-block correspondences")
    score = sub.add_parser("score", help="score every suburb and store this month's snapshot")
    score.add_argument("--cutoff", type=date.fromisoformat, default=date.today(),
                       help="use data with periods ending on or before this date")
    score.add_argument("--weights", help="weights version, e.g. v1 (default: newest)")
    backtest = sub.add_parser("backtest", help="backtest scores against NSW price growth")
    backtest.add_argument("--years", required=True, help="backtest years, e.g. 2016-2024")
    backtest.add_argument("--holdout-from", type=int, required=True,
                          help="first held-out year; earlier years are for training")
    backtest.add_argument("--weights", help="weights version to start from (default: newest)")
    backtest.add_argument("--tune", type=int, metavar="SAMPLES",
                          help="tune weights on training years with this many random draws")
    return parser.parse_args(argv)


def _weights(version: str | None):
    path = WEIGHTS_DIR / f"{version}.yaml" if version else latest_weights_path()
    return load_weights(path)


def _score(args: argparse.Namespace) -> int:
    settings = Settings.database_only()
    weights = _weights(args.weights)
    try:
        n = run_scoring(settings.database_url, args.cutoff, weights)
    except Exception:
        logging.getLogger(__name__).exception("scoring failed")
        return 1
    print(f"scored {n} suburbs with {weights.model_version} (cutoff {args.cutoff})")
    return 0


def _backtest(args: argparse.Namespace) -> int:
    settings = Settings.database_only()
    first, _, last = args.years.partition("-")
    report = run_backtest(settings.database_url, int(first), int(last or first),
                          args.holdout_from, _weights(args.weights), args.tune)
    for row in report.rows:
        print(f"{row['split']:>7} {row['horizon_months']}m: spearman={row['spearman']:.3f} "
              f"over {row['n_dates']} dates")
    print(f"report: scoring/reports/{report.model_version}-backtest.md")
    return 0


def _options(args: argparse.Namespace) -> dict[str, str]:
    options = dict(o.split("=", 1) if "=" in o else (o, "1") for o in args.option)
    if args.years:
        options["years"] = args.years
    return options


def _load_geo(settings: Settings, config: dict) -> None:
    geo = config["geo"]
    http = make_client()
    with tempfile.TemporaryDirectory() as tmp:
        url = geo["sal_boundaries_url"]
        boundaries = Path(tmp) / url.rsplit("/", 1)[-1]
        boundaries.write_bytes(download(http, url))

        def table(key: str) -> pd.DataFrame:
            u = geo[key]
            return read_abs_table(download(http, u), u.rsplit("/", 1)[-1], MB)

        allocation = (
            table("mb_allocation_url")[[MB, "SA2_CODE_2021", "AREA_ALBERS_SQKM"]]
            .merge(table("sal_allocation_url")[[MB, "SAL_CODE_2021"]], on=MB)
            .merge(table("poa_allocation_url")[[MB, "POA_CODE_2021"]], on=MB)
        )
        allocation["AREA_ALBERS_SQKM"] = allocation["AREA_ALBERS_SQKM"].astype(float)
        counts = table("mb_counts_url")[[MB, "Person"]]
        counts["Person"] = pd.to_numeric(counts["Person"], errors="coerce").fillna(0)
        with connect(settings.database_url) as conn:
            print(f"suburbs loaded: {load_suburbs(conn, boundaries)}")
            print(f"correspondences built: {build_correspondences(conn, allocation, counts)}")


def main(argv: list[str] | None = None, *, raw_store: RawStore | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "score":
        return _score(args)
    if args.command == "backtest":
        return _backtest(args)
    settings = Settings.from_env()
    config = load_config(args.config)
    if args.command == "load-geo":
        _load_geo(settings, config)
        return 0
    http = make_client()
    if raw_store is None:
        supabase = SupabaseRawStore(settings.supabase_url, settings.supabase_service_role_key, http)
        supabase.ensure_bucket()
        raw_store = supabase
    outcome = run_source(args.source, db_url=settings.database_url, raw_store=raw_store,
                         http=http, today=date.today(), config=config, options=_options(args))
    print(f"run {outcome.run_id}: {outcome.status}, {outcome.rows_written} rows written")
    return 0 if outcome.status == "success" else 1
