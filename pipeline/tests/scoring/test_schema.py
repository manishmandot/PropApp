from propapp_pipeline.db import connect


def test_scoring_tables_exist(db_url):
    with connect(db_url) as conn:
        names = {r[0] for r in conn.execute(
            "select table_name from information_schema.tables where table_schema='data'")}
    assert {"score_runs", "scores", "score_factors", "backtest_results"} <= names


def test_score_factors_cascade(db_url):
    with connect(db_url) as conn:
        conn.execute("insert into data.suburbs (sal_code, name, state) values ('10001','A','NSW')")
        run_id = conn.execute("insert into data.score_runs (model_version, as_of, status) "
                              "values ('v1','2025-12-01','success') returning id").fetchone()[0]
        conn.execute("insert into data.scores (suburb_code, model_version, as_of, cutoff, run_id, "
                     "coverage) values ('10001','v1','2025-12-01','2025-12-31',%s,'fundamentals')",
                     (run_id,))
        conn.execute("insert into data.score_factors (suburb_code, model_version, as_of, factor, "
                     "layer, raw_value, percentile, weight, contribution) values "
                     "('10001','v1','2025-12-01','median_household_income','fundamentals',"
                     "1,50,1,50)")
        conn.execute("delete from data.scores")
        assert conn.execute("select count(*) from data.score_factors").fetchone()[0] == 0
