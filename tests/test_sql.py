"""Every SQL file is transpiled from BigQuery to DuckDB and run against a
synthetic database with theLook's schema; the tests check the business logic
against independent pandas calculations and structural invariants."""

import pandas as pd
import pytest

from queries import QUERIES, render, run_duckdb, to_duckdb
from synthetic_thelook import build

END = "2026-11-01"


@pytest.fixture(scope="module")
def con():
    return build(seed=0, analysis_end=END)


@pytest.fixture(scope="module")
def items(con):
    return con.execute("SELECT * FROM thelook.order_items").df()


@pytest.mark.parametrize("name", QUERIES)
def test_every_query_transpiles_and_runs(con, name):
    sql = to_duckdb(render(name, "thelook", END))
    assert con.execute(sql).df() is not None


def test_data_quality_counts_future_rows(con):
    dq = run_duckdb("00_data_quality", END, con).iloc[0]
    orders = con.execute("SELECT * FROM thelook.orders").df()
    assert dq["n_orders"] == len(orders)
    assert dq["n_orders_after_cutoff"] == (orders["created_at"] >= pd.Timestamp(END, tz="UTC")).sum()
    assert dq["n_orders_without_items"] == 0 and dq["n_duplicate_item_ids"] == 0


def test_monthly_revenue_matches_pandas(con, items):
    kpis = run_duckdb("01_monthly_kpis", END, con)
    end = pd.Timestamp(END, tz="UTC")
    valid = items[~items["status"].isin(["Cancelled", "Returned"])
                  & (items["created_at"] < end) & (items["created_at"] >= end - pd.DateOffset(months=24))]
    assert kpis["revenue"].sum() == pytest.approx(valid["sale_price"].sum())
    assert len(kpis) <= 24
    assert kpis["cumulative_revenue"].iloc[-1] == pytest.approx(kpis["revenue"].sum())
    first = kpis.iloc[1]
    assert first["mom_growth"] == pytest.approx(first["revenue"] / kpis.iloc[0]["revenue"] - 1)


def test_cohort_month_zero_is_full_cohort(con):
    cohorts = run_duckdb("02_cohort_retention", END, con)
    month0 = cohorts[cohorts["months_since_first"] == 0]
    assert (month0["retention_rate"] == 1.0).all()
    assert (cohorts["retention_rate"] <= 1.0).all()
    assert cohorts["months_since_first"].between(0, 11).all()


def test_cohort_assignment_uses_full_history(con):
    """A customer whose first order predates the window must not appear as new in a recent cohort."""
    cohorts = run_duckdb("02_cohort_retention", END, con)
    orders = con.execute("SELECT * FROM thelook.orders WHERE status != 'Cancelled'").df()
    orders = orders[orders["created_at"] < pd.Timestamp(END, tz="UTC")]
    first = orders.groupby("user_id")["created_at"].min().dt.tz_localize(None).dt.to_period("M")
    expected = first.value_counts()
    for _, row in cohorts[cohorts["months_since_first"] == 0].iterrows():
        assert row["cohort_customers"] == expected[pd.Timestamp(row["cohort_month"]).to_period("M")]


def test_funnel_is_monotonic_and_rollup_totals(con):
    f = run_duckdb("03_funnel_by_source", END, con)
    assert (f["sessions"] >= f["product_view_sessions"]).all()
    assert (f["product_view_sessions"] >= f["cart_sessions"]).all()
    assert (f["cart_sessions"] >= f["purchase_sessions"]).all()
    total = f[f["traffic_source"] == "All sources"].iloc[0]
    by_source = f[f["traffic_source"] != "All sources"]
    assert total["sessions"] == by_source["sessions"].sum()
    assert total["purchase_sessions"] == by_source["purchase_sessions"].sum()


def test_rfm_shares_sum_to_one(con):
    rfm = run_duckdb("04_rfm_segments", END, con)
    assert rfm["share_of_customers"].sum() == pytest.approx(1.0)
    assert rfm["share_of_revenue"].sum() == pytest.approx(1.0)
    single = rfm.set_index("segment").loc[["New customers", "Needs nurturing", "Hibernating"], "avg_orders"]
    assert (single == 1).all()  # single-order segments only ever hold one-order customers


def test_revenue_concentration_is_ordered(con):
    conc = run_duckdb("05_revenue_concentration", END, con)
    assert list(conc["decile"]) == list(range(1, 11))
    assert conc["cumulative_share_of_revenue"].iloc[-1] == pytest.approx(1.0)
    assert conc["share_of_revenue"].is_monotonic_decreasing


def test_category_ranks_and_rates(con):
    cats = run_duckdb("06_category_performance", END, con)
    assert cats["return_rate"].between(0, 1).all()
    assert (cats.groupby("department")["margin_rank_in_department"].min() == 1).all()
    assert cats.groupby("department")["share_of_department_revenue"].sum().to_numpy() == pytest.approx(1.0)
