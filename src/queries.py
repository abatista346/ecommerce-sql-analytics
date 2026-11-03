"""Load, render and run the SQL files in sql/.

The SQL is written in BigQuery Standard SQL and runs against the public
`bigquery-public-data.thelook_ecommerce` dataset. For tests, the same files
are transpiled to DuckDB with sqlglot and run against small synthetic tables,
so every query's logic is checked in CI without BigQuery credentials.
"""

from pathlib import Path

import pandas as pd
import sqlglot

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
PUBLIC_DATASET = "bigquery-public-data.thelook_ecommerce"

QUERIES = [
    "00_data_quality",
    "01_monthly_kpis",
    "02_cohort_retention",
    "03_funnel_by_source",
    "04_rfm_segments",
    "05_revenue_concentration",
    "06_category_performance",
]


def render(name: str, dataset: str, analysis_end: str) -> str:
    """Fill the {dataset} and {analysis_end} placeholders of a SQL file."""
    template = (SQL_DIR / f"{name}.sql").read_text()
    return template.replace("{dataset}", dataset).replace("{analysis_end}", analysis_end)


def to_duckdb(bigquery_sql: str) -> str:
    return sqlglot.transpile(bigquery_sql, read="bigquery", write="duckdb")[0]


def run_bigquery(name: str, analysis_end: str, client=None, dataset: str = PUBLIC_DATASET) -> pd.DataFrame:
    from google.cloud import bigquery

    client = client or bigquery.Client()
    return client.query(render(name, dataset, analysis_end)).to_dataframe()


def run_duckdb(name: str, analysis_end: str, con, dataset: str = "thelook") -> pd.DataFrame:
    return con.execute(to_duckdb(render(name, dataset, analysis_end))).df()
