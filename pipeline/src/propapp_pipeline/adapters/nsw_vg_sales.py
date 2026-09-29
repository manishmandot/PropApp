from dataclasses import dataclass
from datetime import date, datetime, timedelta

import httpx

from propapp_pipeline.adapters.base import Adapter, NormaliseResult, register
from propapp_pipeline.adapters.common import zip_members
from propapp_pipeline.http import download
from propapp_pipeline.models import Observation, Period
from propapp_pipeline.parsing import SourceLayoutError
from propapp_pipeline.raw_store import RawFile

WEEKLY_FILES = 4
# On catch-up, re-fetch from this long before the last successful run.
CATCH_UP_OVERLAP = timedelta(weeks=2)
MAX_WEEKLY_FILES = 104
# Nominal-price transfers and extreme outliers are dropped per sale so one record can
# never fail a whole batch (and with it, that week's sales).
MIN_PRICE, MAX_PRICE = 10_000, 50_000_000
# Field positions in a current-format (2001+) "B" sale record.
F_PROPERTY_ID, F_UNIT, F_HOUSE, F_STREET, F_LOCALITY, F_POSTCODE = 2, 6, 7, 8, 9, 10
F_CONTRACT, F_PRICE, F_NATURE, F_STRATA, F_INTEREST, F_DEALING = 13, 15, 17, 19, 22, 23
B_RECORD_FIELDS = 24


@dataclass(frozen=True)
class Sale:
    dealing_number: str
    property_id: str
    contract_date: date
    price: float
    is_strata: bool
    locality: str
    postcode: str
    address: str


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, months: int) -> date:
    index = d.year * 12 + d.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


@register
class NswVgSalesAdapter(Adapter):
    """NSW Valuer General bulk property sales (weekly files, or yearly files for backfill).

    Sales are kept address-level in data.nsw_sales; only rolling suburb medians and counts
    become observations.
    """

    source_id = "nsw_vg_sales"
    # Output size depends on which months a batch touches (weekly vs backfill), so a
    # row-count comparison is meaningless; every fetched file must contain sales instead.
    row_count_tolerance = None

    def fetch(self, http, config):
        if years := self.options.get("years"):
            first, _, last = years.partition("-")
            return [self._get(http, config["yearly_url_template"].format(year=y), f"{y}.zip")
                    for y in range(int(first), int(last or first) + 1)]
        as_of = date.fromisoformat(self.options.get("as_of", date.today().isoformat()))
        newest_monday = as_of - timedelta(days=as_of.weekday())
        oldest = newest_monday - timedelta(weeks=WEEKLY_FILES - 1)
        if self.last_success:
            oldest = min(oldest, self.last_success - CATCH_UP_OVERLAP)
        weeks = min((newest_monday - oldest).days // 7 + 1, MAX_WEEKLY_FILES)
        files = []
        for i in range(weeks):
            monday = newest_monday - timedelta(weeks=i)
            url = config["weekly_url_template"].format(date=monday)
            try:
                files.append(self._get(http, url, f"{monday:%Y%m%d}.zip"))
            except httpx.HTTPStatusError as exc:
                if i == 0 and exc.response.status_code == 404:
                    continue  # this week's file is not published yet
                raise
        return files

    @staticmethod
    def _get(http, url: str, filename: str) -> RawFile:
        return RawFile(filename, download(http, url))

    def parse(self, raw):
        sales: dict[tuple[str, str], Sale] = {}
        for file in raw:
            records = 0
            for name, data in zip_members(file.content):
                if not name.upper().endswith(".DAT"):
                    continue
                for line in data.decode("latin-1").splitlines():
                    fields = line.split(";")
                    if fields[0] != "B":
                        continue
                    records += 1
                    if len(fields) < B_RECORD_FIELDS:
                        raise SourceLayoutError(
                            f"{self.source_id}: B record has {len(fields)} fields in {name}")
                    sale = _sale(fields)
                    if sale:
                        sales[(sale.dealing_number, sale.property_id)] = sale
            if records == 0:
                raise SourceLayoutError(f"{self.source_id}: no sale records in {file.filename}")
        return list(sales.values())

    def normalise(self, rows, ctx):
        matched = [(s, ctx.matcher.match(s.locality, "NSW", s.postcode)) for s in rows]
        _store_sales(ctx.conn, matched)
        last_month = _month_start(ctx.today)
        months = sorted({
            m for s in rows for k in range(12)
            if (m := _add_months(_month_start(s.contract_date), k)) <= last_month
        })
        observations = _rolling_observations(ctx.conn, months, self.source_id)
        return NormaliseResult(observations, sum(1 for _, sal in matched if sal), len(rows))


def _sale(f: list[str]) -> Sale | None:
    try:
        price = float(f[F_PRICE] or 0)
    except ValueError:
        return None
    interest = f[F_INTEREST].strip()
    if (f[F_NATURE] != "R" or not MIN_PRICE <= price <= MAX_PRICE
            or interest not in ("", "100") or not f[F_CONTRACT]):
        return None
    address = " ".join(p.strip() for p in (f[F_UNIT], f[F_HOUSE], f[F_STREET],
                                             f[F_LOCALITY], f[F_POSTCODE]) if p.strip())
    return Sale(
        dealing_number=f[F_DEALING].strip(),
        property_id=f[F_PROPERTY_ID].strip(),
        contract_date=datetime.strptime(f[F_CONTRACT], "%Y%m%d").date(),
        price=price,
        is_strata=bool(f[F_STRATA].strip()),
        locality=f[F_LOCALITY].strip(),
        postcode=f[F_POSTCODE].strip(),
        address=address,
    )


def _store_sales(conn, matched: list[tuple[Sale, str | None]]) -> None:
    with conn.cursor() as cur:
        cur.execute("drop table if exists _sales")
        cur.execute("create temp table _sales (like data.nsw_sales)")
        with cur.copy("copy _sales (dealing_number, property_id, contract_date, price, "
                      "is_strata, locality, postcode, address, sal_code) from stdin") as copy:
            for s, sal in matched:
                copy.write_row((s.dealing_number, s.property_id, s.contract_date, s.price,
                                s.is_strata, s.locality, s.postcode, s.address, sal))
        cur.execute("""
            insert into data.nsw_sales select * from _sales
            on conflict (dealing_number, property_id) do update set
                contract_date = excluded.contract_date, price = excluded.price,
                is_strata = excluded.is_strata, locality = excluded.locality,
                postcode = excluded.postcode, address = excluded.address,
                sal_code = excluded.sal_code
        """)
        cur.execute("drop table _sales")


ROLLING_SQL = """
    with months as (select unnest(%s::date[]) as m)
    select m, s.sal_code, s.is_strata, count(*),
           percentile_cont(0.5) within group (order by s.price),
           percentile_cont(0.5) within group (order by s.price)
               filter (where s.contract_date >= m - interval '2 months')
    from months
    join data.nsw_sales s
      on s.contract_date >= m - interval '11 months'
     and s.contract_date < m + interval '1 month'
     and s.sal_code is not null
     -- multi-property dealings repeat the full price on every property: exclude them
     and not exists (select 1 from data.nsw_sales o
                     where o.dealing_number = s.dealing_number
                       and o.property_id <> s.property_id)
    group by m, s.sal_code, s.is_strata
"""


def _rolling_observations(conn, months: list[date], source: str) -> list[Observation]:
    if not months:
        return []
    observations = []
    for month, sal, is_strata, count, median_12m, median_3m in conn.execute(
            ROLLING_SQL, (months,)):
        kind = "unit" if is_strata else "house"
        period = Period.month(month.year, month.month)
        values = {f"sales_count_{kind}_12m": count, f"median_sale_price_{kind}_12m": median_12m,
                  f"median_sale_price_{kind}_3m": median_3m}
        observations.extend(Observation(sal, metric, period, float(v), source, "SAL")
                            for metric, v in values.items() if v is not None)
    return observations
