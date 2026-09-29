import pytest

from propapp_pipeline.db import connect

from .helpers import frame, monthly, quarterly, yearly

SUBURBS = [("10001", "Alpha", "NSW"), ("10002", "Beta", "NSW"), ("10003", "Gamma", "NSW")]


def fundamentals(suburb, pop_then, pop_now, income, share):
    return [
        yearly(suburb, "population", 2021, pop_then), yearly(suburb, "population", 2024, pop_now),
        yearly(suburb, "median_household_income_weekly", 2021, income, "abs_census"),
        yearly(suburb, "owner_occupier_share", 2021, share, "abs_census"),
        quarterly(suburb, "unemployed_count", 2024, 4, 30),
        quarterly(suburb, "labour_force_count", 2024, 4, 800),
        quarterly(suburb, "unemployed_count", 2023, 4, 40),
        quarterly(suburb, "labour_force_count", 2023, 4, 800),
    ]


SEED_ROWS = [
    *fundamentals("10001", 1000, 1100, 2000, 0.7),
    *fundamentals("10002", 1000, 1050, 1500, 0.6),
    yearly("10003", "owner_occupier_share", 2021, 0.5, "abs_census"),
    monthly("10001", "sales_count_house_12m", 2025, 9, 30),
    monthly("10001", "sales_count_house_12m", 2024, 9, 25),
    monthly("10001", "median_sale_price_house_12m", 2025, 9, 1_100_000),
    monthly("10001", "median_sale_price_house_12m", 2024, 9, 1_000_000),
    monthly("10001", "median_sale_price_house_3m", 2025, 9, 1_120_000),
    monthly("10001", "median_sale_price_house_3m", 2025, 6, 1_080_000),
    quarterly("10001", "median_weekly_rent_house_q", 2025, 3, 900),
    quarterly("10001", "median_weekly_rent_house_q", 2024, 3, 850),
]


def insert_observations(db_url, rows):
    df = frame(rows)
    with connect(db_url) as conn, conn.cursor() as cur:
        cur.executemany(
            "insert into data.observations (suburb_code, metric, period_start, "
            "period_granularity, value, source, source_geography) values (%s,%s,%s,%s,%s,%s,'SAL')",
            [(r.suburb_code, r.metric, r.period_start.date(), r.granularity, r.value, r.source)
             for r in df.itertuples()])


@pytest.fixture
def seeded(db_url):
    with connect(db_url) as conn:
        conn.cursor().executemany(
            "insert into data.suburbs (sal_code, name, state) values (%s,%s,%s)", SUBURBS)
    insert_observations(db_url, SEED_ROWS)
    return db_url
