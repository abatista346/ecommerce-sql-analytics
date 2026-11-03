"""Tests for the Python analysis helpers and an end-to-end dry run of the report."""

import numpy as np
import pandas as pd
import pytest

import run_analysis
from queries import QUERIES, run_duckdb
from synthetic_thelook import build

END = "2026-11-01"


def test_retention_matrix_masks_unobservable_months():
    cohorts = pd.DataFrame({
        "cohort_month": ["2026-09-01", "2026-09-01", "2026-10-01"],
        "months_since_first": [0, 1, 0],
        "retention_rate": [1.0, 0.05, 1.0],
    })
    m = run_analysis.retention_matrix(cohorts, END)
    assert m.loc["2026-09-01", 1] == 0.05
    assert np.isnan(m.loc["2026-09-01", 2])  # November 2026 has not happened yet
    assert np.isnan(m.loc["2026-10-01", 1])


def test_retention_matrix_fills_observed_gaps_with_zero():
    cohorts = pd.DataFrame({"cohort_month": ["2026-06-01", "2026-06-01"], "months_since_first": [0, 2], "retention_rate": [1.0, 0.03]})
    m = run_analysis.retention_matrix(cohorts, END)
    assert m.loc["2026-06-01", 1] == 0.0  # observable, nobody bought: a real zero


def test_funnel_tests_detect_a_real_difference():
    funnel = pd.DataFrame({
        "traffic_source": ["All sources", "A", "B"],
        "sessions": [20_000, 10_000, 10_000],
        "purchase_sessions": [2_500, 1_500, 1_000],
        "session_conversion_rate": [0.125, 0.15, 0.10],
    })
    r = run_analysis.funnel_tests(funnel)
    assert r["best_source"] == "A" and r["worst_source"] == "B"
    assert r["p_value"] < 0.001


def test_end_to_end_report_on_synthetic_data(tmp_path, monkeypatch):
    con = build(seed=1, analysis_end=END)
    res = {q: run_duckdb(q, END, con) for q in QUERIES}
    readme = tmp_path / "README.md"
    readme.write_text("intro\n<!-- RESULTS:START -->\nplaceholder\n<!-- RESULTS:END -->\noutro\n")
    monkeypatch.setattr(run_analysis, "README", readme)
    monkeypatch.setattr(run_analysis, "FIG", tmp_path)

    matrix = run_analysis.retention_matrix(res["02_cohort_retention"], END)
    ft = run_analysis.funnel_tests(res["03_funnel_by_source"])
    run_analysis.plot_cohorts(matrix)
    run_analysis.plot_funnel(ft["by_source"], 0.1)
    run_analysis.write_readme({
        "dq": res["00_data_quality"].iloc[0], "kpis": res["01_monthly_kpis"], "funnel": ft,
        "rfm": res["04_rfm_segments"], "conc": res["05_revenue_concentration"],
        "cats": res["06_category_performance"], "matrix": matrix, "analysis_end_label": "October 2026",
    })
    text = readme.read_text()
    assert text.startswith("intro") and text.rstrip().endswith("outro")
    assert "placeholder" not in text and "## Results (data through October 2026)" in text
    assert (tmp_path / "02_cohort_retention.png").exists()
