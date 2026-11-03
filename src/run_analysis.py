"""Run every SQL file against BigQuery, chart the results, test the funnel
differences statistically, and write the Results section of README.md.

Usage:
    gcloud auth application-default login
    python src/run_analysis.py --project YOUR_GCP_PROJECT [--analysis-end 2026-11-01]

The queries read the free public dataset `bigquery-public-data.thelook_ecommerce`;
--project is the project billed for (and usually covered by the free tier of)
the query bytes scanned.
"""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency
from statsmodels.stats.proportion import proportion_confint, proportions_ztest

from queries import QUERIES, run_bigquery

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
FIG = OUT / "figures"
README = ROOT / "README.md"
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
DEFAULT_ANALYSIS_END = "2026-11-01"

ACCENT = "#1D5FD6"
SECONDARY = "#4A5B6E"
MUTED = "#9AAABB"
GRID = "#D7E3F0"


# ---------- analysis helpers (pure functions, unit-tested) ----------

def retention_matrix(cohorts: pd.DataFrame, analysis_end: str) -> pd.DataFrame:
    """Pivot cohort rows into a cohort x month matrix; months not yet observable are NaN, not 0."""
    m = cohorts.pivot_table(index="cohort_month", columns="months_since_first", values="retention_rate")
    m = m.reindex(columns=range(12))
    end = pd.Timestamp(analysis_end)
    for cohort in m.index:
        months_observable = (end.year - pd.Timestamp(cohort).year) * 12 + (end.month - pd.Timestamp(cohort).month)
        m.loc[cohort, m.columns >= months_observable] = np.nan
        m.loc[cohort, (m.columns < months_observable) & m.loc[cohort].isna()] = 0.0
    return m


def funnel_tests(funnel: pd.DataFrame) -> dict:
    by_source = funnel[funnel["traffic_source"] != "All sources"].copy()
    purchases = by_source["purchase_sessions"].astype(int).to_numpy()
    sessions = by_source["sessions"].astype(int).to_numpy()
    chi2, p, dof, _ = chi2_contingency(np.vstack([purchases, sessions - purchases]))
    lo, hi = proportion_confint(purchases, sessions, method="wilson")
    by_source["ci_low"], by_source["ci_high"] = lo, hi
    by_source = by_source.sort_values("session_conversion_rate", ascending=False)
    best, worst = by_source.iloc[0], by_source.iloc[-1]
    z, p_pair = proportions_ztest([int(best["purchase_sessions"]), int(worst["purchase_sessions"])],
                                  [int(best["sessions"]), int(worst["sessions"])])
    return {
        "chi2": float(chi2), "dof": int(dof), "p_value": float(p),
        "best_source": best["traffic_source"], "best_rate": float(best["session_conversion_rate"]),
        "worst_source": worst["traffic_source"], "worst_rate": float(worst["session_conversion_rate"]),
        "best_vs_worst_p": float(p_pair),
        "by_source": by_source,
    }


# ---------- charts ----------

def plot_monthly(kpis: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(pd.to_datetime(kpis["month"]), kpis["revenue"] / 1e3, width=20, color=MUTED, label="Monthly revenue")
    ax.plot(pd.to_datetime(kpis["month"]), kpis["revenue_3m_avg"] / 1e3, color=ACCENT, linewidth=2.2, label="3-month moving average")
    ax.set_ylabel("Revenue (US$ thousands)")
    ax.set_title("Monthly net revenue, last 24 complete months", loc="left", fontsize=12, fontweight="bold")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG / "01_monthly_revenue.png", dpi=150)
    plt.close(fig)


def plot_cohorts(matrix: pd.DataFrame) -> None:
    shown = matrix.drop(columns=0).dropna(how="all")  # month 0 is 100% by definition; drop cohorts with nothing observable yet
    fig, ax = plt.subplots(figsize=(10, 5.5))
    im = ax.imshow(shown.to_numpy() * 100, cmap="Blues", aspect="auto")
    ax.set_xticks(range(shown.shape[1]), shown.columns)
    ax.set_yticks(range(shown.shape[0]), [pd.Timestamp(c).strftime("%Y-%m") for c in shown.index])
    for i in range(shown.shape[0]):
        for j in range(shown.shape[1]):
            v = shown.iloc[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v * 100:.1f}", ha="center", va="center", fontsize=7,
                        color="white" if v * 100 > np.nanmax(shown.to_numpy()) * 60 else "#1A2433")
    ax.set_xlabel("Months since first purchase")
    ax.set_ylabel("Acquisition cohort")
    ax.set_title("Repeat-purchase rate by cohort (%) — blank cells are not yet observable", loc="left", fontsize=11, fontweight="bold")
    fig.colorbar(im, ax=ax, label="% of cohort buying that month")
    fig.tight_layout()
    fig.savefig(FIG / "02_cohort_retention.png", dpi=150)
    plt.close(fig)


def plot_funnel(by_source: pd.DataFrame, overall: float) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.5))
    x = np.arange(len(by_source))
    rate = by_source["session_conversion_rate"].to_numpy() * 100
    err = np.vstack([rate - by_source["ci_low"].to_numpy() * 100, by_source["ci_high"].to_numpy() * 100 - rate])
    ax.bar(x, rate, color=ACCENT)
    ax.errorbar(x, rate, yerr=err, fmt="none", ecolor=SECONDARY, capsize=4)
    ax.axhline(overall * 100, color=SECONDARY, linestyle="--", linewidth=1.2, label="All sources")
    ax.set_xticks(x, by_source["traffic_source"])
    ax.set_ylabel("Sessions ending in purchase (%)")
    ax.set_title("Session conversion by traffic source (95% Wilson intervals)", loc="left", fontsize=12, fontweight="bold")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG / "03_conversion_by_source.png", dpi=150)
    plt.close(fig)


def plot_rfm(rfm: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.5))
    x = np.arange(len(rfm))
    ax.bar(x - 0.2, rfm["share_of_customers"] * 100, width=0.4, color=MUTED, label="Share of customers")
    ax.bar(x + 0.2, rfm["share_of_revenue"] * 100, width=0.4, color=ACCENT, label="Share of revenue")
    ax.set_xticks(x, rfm["segment"], fontsize=9)
    ax.set_ylabel("%")
    ax.set_title("RFM segments: customers vs. revenue", loc="left", fontsize=12, fontweight="bold")
    ax.legend(frameon=False, ncol=2, loc="lower right", bbox_to_anchor=(1.0, 1.0))
    fig.tight_layout()
    fig.savefig(FIG / "04_rfm_segments.png", dpi=150)
    plt.close(fig)


def plot_concentration(conc: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 5))
    x = np.concatenate([[0], conc["decile"].to_numpy() * 10])
    y = np.concatenate([[0], conc["cumulative_share_of_revenue"].to_numpy() * 100])
    ax.plot([0, 100], [0, 100], color=GRID, linestyle="--", label="Equal spend")
    ax.plot(x, y, marker="o", color=ACCENT, label="Actual")
    ax.set_xlabel("Top % of customers by spend")
    ax.set_ylabel("% of revenue")
    ax.set_title("Revenue concentration", loc="left", fontsize=12, fontweight="bold")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG / "05_revenue_concentration.png", dpi=150)
    plt.close(fig)


def plot_categories(cats: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 5.5))
    colors = {d: c for d, c in zip(sorted(cats["department"].unique()), [ACCENT, SECONDARY, MUTED])}
    for dept, g in cats.groupby("department"):
        ax.scatter(g["return_rate"] * 100, g["margin_rate"] * 100, s=g["net_revenue"] / cats["net_revenue"].max() * 600,
                   alpha=0.7, color=colors[dept], label=dept)
    for _, r in cats.nlargest(6, "net_revenue").iterrows():
        ax.annotate(r["category"], (r["return_rate"] * 100, r["margin_rate"] * 100), fontsize=8, xytext=(5, 4), textcoords="offset points")
    ax.set_xlabel("Return rate (%)")
    ax.set_ylabel("Gross margin rate (%)")
    ax.set_title("Categories: margin vs. returns (bubble size = net revenue)", loc="left", fontsize=12, fontweight="bold")
    legend = ax.legend(frameon=False, markerscale=0.4)
    for handle in legend.legend_handles:
        handle.set_sizes([60])
    fig.tight_layout()
    fig.savefig(FIG / "06_category_margin_vs_returns.png", dpi=150)
    plt.close(fig)


# ---------- README ----------

def pct(x: float, d: int = 1) -> str:
    return f"{x * 100:.{d}f}%"


def write_readme(r: dict) -> None:
    dq, kpis, ft, rfm, conc, cats, mat = r["dq"], r["kpis"], r["funnel"], r["rfm"], r["conc"], r["cats"], r["matrix"]
    last12 = kpis.tail(12)["revenue"].sum()
    prev12 = kpis.head(len(kpis) - 12)["revenue"].sum() if len(kpis) > 12 else float("nan")
    m1 = mat[1].dropna()
    top10 = float(conc.loc[conc["decile"] == 1, "share_of_revenue"].iloc[0])
    top20 = float(conc.loc[conc["decile"] == 2, "cumulative_share_of_revenue"].iloc[0])
    champions = rfm.set_index("segment").reindex(["Champions"]).iloc[0]
    at_risk = rfm.set_index("segment").reindex(["At risk"]).iloc[0]
    worst_ret = cats.sort_values("return_rate", ascending=False).iloc[0]
    best_margin = cats.sort_values("margin_rate", ascending=False).iloc[0]
    sig = ft["p_value"] < 0.05

    lines = [
        START, "",
        f"## Results (data through {r['analysis_end_label']})", "",
        "### Data quality", "",
        f"- {int(dq['n_orders']):,} orders in the dataset; **{int(dq['n_orders_after_cutoff']):,} are dated after the cut-off** (theLook generates future-dated rows) and are excluded everywhere.",
        f"- {int(dq['n_orders_without_items'])} orders without items, {int(dq['n_duplicate_item_ids'])} duplicate item ids, {int(dq['n_orders_without_user'])} orders without a user.",
        f"- {pct(dq['share_items_cancelled'])} of items are cancelled and {pct(dq['share_items_returned'])} returned; both are excluded from revenue.", "",
        "### Growth", "",
        f"Net revenue over the last 12 months was **US${last12:,.0f}**"
        + (f", {last12 / prev12 - 1:+.0%} versus the prior 12 months." if prev12 == prev12 and prev12 > 0 else "."),
        "", "![Monthly revenue](outputs/figures/01_monthly_revenue.png)", "",
        "### Retention", "",
        f"Across the last 12 acquisition cohorts, a median of **{pct(m1.median())}** of new customers buy again in their second month "
        f"(range {pct(m1.min())}–{pct(m1.max())})."
        + (" Retention is the weakest part of the business: most revenue depends on acquiring new buyers." if m1.median() < 0.10 else ""),
        "", "![Cohort retention](outputs/figures/02_cohort_retention.png)", "",
        "### Conversion by traffic source", "",
        f"Session conversion ranges from **{pct(ft['worst_rate'], 2)} ({ft['worst_source']})** to **{pct(ft['best_rate'], 2)} ({ft['best_source']})**. "
        + (f"The differences across sources are statistically significant (χ² = {ft['chi2']:.1f}, df = {ft['dof']}, p = {ft['p_value']:.1e})."
           if sig else
           f"The differences are **not** statistically significant (χ² = {ft['chi2']:.1f}, df = {ft['dof']}, p = {ft['p_value']:.2f}), so channel budget should not be reallocated on conversion alone."),
        "", "![Conversion by source](outputs/figures/03_conversion_by_source.png)", "",
        "### Who drives revenue", "",
        f"- The top 10% of customers generate **{pct(top10)}** of revenue, and the top 20% generate **{pct(top20)}**.",
        (f"- **Champions** (recent, repeat buyers) are {pct(champions['share_of_customers'])} of customers but {pct(champions['share_of_revenue'])} of revenue; "
         f"**At risk** customers (repeat buyers who have gone quiet) hold {pct(at_risk['share_of_revenue'])} of revenue."
         if champions.notna().all() and at_risk.notna().all() else "- See the segment table in `outputs/04_rfm_segments.csv`."),
        "", "![RFM segments](outputs/figures/04_rfm_segments.png)",
        "![Revenue concentration](outputs/figures/05_revenue_concentration.png)", "",
        "### Categories", "",
        f"Highest margin rate: **{best_margin['category']}** ({pct(best_margin['margin_rate'])}). "
        f"Highest return rate: **{worst_ret['category']}** ({pct(worst_ret['return_rate'])}).",
        "", "![Category margin vs returns](outputs/figures/06_category_margin_vs_returns.png)", "",
        "### Recommendations", "",
        (f"1. **Retention before acquisition.** With a median second-month repeat rate of {pct(m1.median())}, a post-purchase program aimed at first-time buyers "
         "has more room to grow revenue than further acquisition spend. Test it with a randomized holdout before scaling."
         if m1.median() < 0.10 else
         f"1. **Protect retention.** A median second-month repeat rate of {pct(m1.median())} is a strength; monitor it by cohort as acquisition scales."),
        "2. **Win back the *At risk* segment** first: these customers have already bought more than once, so reactivating them is cheaper than converting new ones.",
        ("3. **Shift acquisition budget toward the best-converting sources** only after checking cost per session per channel, which this dataset does not include."
         if sig else
         "3. **Do not reallocate channel budget on conversion rate alone**: the differences between sources are within sampling noise."),
        "", END,
    ]
    text = README.read_text()
    text = text.split(START)[0] + "\n".join(lines) + text.split(END)[1]
    README.write_text(text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, help="GCP project to run (and bill) the queries")
    parser.add_argument("--analysis-end", default=DEFAULT_ANALYSIS_END, help="Exclusive cut-off date, first day of a month (YYYY-MM-01)")
    args = parser.parse_args()

    from google.cloud import bigquery

    client = bigquery.Client(project=args.project)
    OUT.mkdir(exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    results = {}
    for q in QUERIES:
        df = run_bigquery(q, args.analysis_end, client=client)
        df.to_csv(OUT / f"{q}.csv", index=False)
        results[q] = df
        print(f"{q}: {len(df)} rows")

    dq = results["00_data_quality"].iloc[0]
    kpis, cohorts, funnel = results["01_monthly_kpis"], results["02_cohort_retention"], results["03_funnel_by_source"]
    rfm, conc, cats = results["04_rfm_segments"], results["05_revenue_concentration"], results["06_category_performance"]

    matrix = retention_matrix(cohorts, args.analysis_end)
    ft = funnel_tests(funnel)
    overall = float(funnel.loc[funnel["traffic_source"] == "All sources", "session_conversion_rate"].iloc[0])

    plot_monthly(kpis)
    plot_cohorts(matrix)
    plot_funnel(ft["by_source"], overall)
    plot_rfm(rfm)
    plot_concentration(conc)
    plot_categories(cats)

    summary = {k: v for k, v in ft.items() if k != "by_source"}
    (OUT / "funnel_significance.json").write_text(json.dumps(summary, indent=2, default=str))

    end_label = (pd.Timestamp(args.analysis_end) - pd.Timedelta(days=1)).strftime("%B %Y")
    write_readme({"dq": dq, "kpis": kpis, "funnel": ft, "rfm": rfm, "conc": conc, "cats": cats,
                  "matrix": matrix, "analysis_end_label": end_label})
    print("README results section updated")


if __name__ == "__main__":
    main()
