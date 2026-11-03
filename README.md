# E-commerce Analytics in SQL — Growth, Retention, Funnel and Customer Value

[![tests](https://github.com/abatista346/ecommerce-sql-analytics/actions/workflows/tests.yml/badge.svg)](https://github.com/abatista346/ecommerce-sql-analytics/actions/workflows/tests.yml)

> SQL-first analysis of an online fashion retailer on **BigQuery**: monthly KPIs, acquisition-cohort retention, a session funnel by traffic source with significance testing, RFM segmentation, revenue concentration and category margins. Every query is unit-tested in CI by transpiling it to DuckDB and running it against synthetic data.

## Business Questions

A head of e-commerce asks five things:

1. **Are we growing?** Monthly revenue, orders, average order value, month-over-month and year-over-year growth.
2. **Do new customers come back?** Repeat-purchase rate by monthly acquisition cohort.
3. **Which traffic sources convert?** Product view → cart → purchase, by source — and whether the differences are real or noise.
4. **Who drives revenue?** RFM segments and how concentrated revenue is among top customers.
5. **Which categories make money?** Gross margin and return rate by category, ranked within department.

## Data Source

[theLook eCommerce](https://console.cloud.google.com/marketplace/product/bigquery-public-data/thelook-ecommerce), a public BigQuery dataset (`bigquery-public-data.thelook_ecommerce`) published by Google with users, orders, order items, products and web events for a fictional clothing store. The data is synthetic and regenerated continuously — including some rows dated in the future — so every query uses a fixed cut-off date for reproducible results.

## SQL Techniques

| Query | What it answers | Techniques |
|---|---|---|
| [`00_data_quality.sql`](sql/00_data_quality.sql) | Can the data be trusted? | Scalar subqueries, `NOT EXISTS` anti-join, `COUNTIF` |
| [`01_monthly_kpis.sql`](sql/01_monthly_kpis.sql) | Are we growing? | CTEs, `LAG` with a named `WINDOW`, moving average and running total frames, `SAFE_DIVIDE` |
| [`02_cohort_retention.sql`](sql/02_cohort_retention.sql) | Do customers come back? | First-purchase cohorts over the full history, `DATE_DIFF` by month |
| [`03_funnel_by_source.sql`](sql/03_funnel_by_source.sql) | Which sources convert? | Session-level pivot with conditional aggregation, strict funnel stages, `ROLLUP` totals |
| [`04_rfm_segments.sql`](sql/04_rfm_segments.sql) | Who are our best customers? | `NTILE` scoring, segment rules, shares with `SUM(...) OVER ()` |
| [`05_revenue_concentration.sql`](sql/05_revenue_concentration.sql) | How concentrated is revenue? | Decile ranking, cumulative share with window frames |
| [`06_category_performance.sql`](sql/06_category_performance.sql) | Which categories make money? | Join to products, `RANK() OVER (PARTITION BY ...)`, share within department |

**Design choices worth noting**

- **Revenue** excludes cancelled and returned items; the **return rate** is computed over non-cancelled items, since only sold items can be returned.
- **Cohorts** use each customer's first purchase across the *full* history, so an old customer never shows up as "new" in a recent cohort. Months a cohort has not reached yet are shown as blank, not as 0% retention.
- **RFM frequency** uses fixed buckets (1, 2, 3, 4+ orders) instead of `NTILE`: most customers have one or two orders, and `NTILE` would assign identical order counts to different scores arbitrarily.
- **Funnel stages are strict**: a session counts as "cart" only if it also viewed a product, so the funnel can only narrow.

## Approach

1. **SQL** (`sql/`) — the analysis logic, in BigQuery Standard SQL.
2. **Runner** (`src/run_analysis.py`) — executes each query on BigQuery, saves results to `outputs/`, draws the charts, tests whether conversion differs by traffic source (χ² test of independence, Wilson intervals), and writes the *Results* section below from the computed numbers.
3. **Tests** (`tests/`) — each SQL file is transpiled to DuckDB with [sqlglot](https://github.com/tobymao/sqlglot) and run against a synthetic database with theLook's schema. The tests check the logic against independent pandas calculations (e.g. monthly revenue totals, cohort sizes) and structural rules (funnel never widens, shares sum to 100%, cohort month 0 is always 100%).

## Tech Stack

SQL (BigQuery, DuckDB), Python, pandas, SciPy, statsmodels, matplotlib, sqlglot, pytest, GitHub Actions

<!-- RESULTS:START -->

## Results

Run the pipeline in [Setup](#setup) to generate this section.

<!-- RESULTS:END -->

## Architecture

```
sql/                      <- one file per business question (BigQuery Standard SQL)
src/
  queries.py              <- renders, runs (BigQuery) and transpiles (DuckDB) the SQL
  run_analysis.py         <- runs every query, charts, significance test, README section
tests/
  synthetic_thelook.py    <- synthetic DuckDB database with theLook's schema
  test_sql.py             <- every query checked against pandas and structural rules
  test_analysis.py        <- analysis helpers and an end-to-end dry run of the report
outputs/
  *.csv                   <- query results
  figures/                <- charts used in this README
```

## Setup

1. `pip install -r requirements.txt`
2. Authenticate with Google Cloud: `gcloud auth application-default login`. Any Google Cloud project works, including a free [BigQuery sandbox](https://cloud.google.com/bigquery/docs/sandbox); the queries scan well under the 1 TB monthly free tier.
3. `python src/run_analysis.py --project YOUR_GCP_PROJECT` (optionally `--analysis-end 2026-11-01`, the exclusive cut-off date)

Run the tests with `pytest` — they need neither BigQuery nor credentials.

## Limitations and Next Steps

1. **Synthetic data.** theLook is generated, so patterns such as seasonality are weaker than in a real store; the value here is in the method and the SQL.
2. **No marketing cost data.** Conversion by source says nothing about return on ad spend; a real channel decision needs cost per session.
3. **Next:** model time-to-second-purchase with survival analysis (Kaplan–Meier by acquisition channel), and move the queries into dbt models with schema tests.
