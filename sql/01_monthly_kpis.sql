-- Monthly revenue KPIs for the last 24 complete months, with growth rates and a
-- 3-month moving average computed with window functions.
-- Revenue = sale price of items that were neither cancelled nor returned.
WITH items AS (
    SELECT
        order_id,
        user_id,
        sale_price,
        DATE_TRUNC(DATE(created_at), MONTH) AS month
    FROM `{dataset}.order_items`
    WHERE status NOT IN ('Cancelled', 'Returned')
      AND created_at <  TIMESTAMP('{analysis_end}')
      AND created_at >= TIMESTAMP(DATE_SUB(DATE '{analysis_end}', INTERVAL 24 MONTH))
),
monthly AS (
    SELECT
        month,
        SUM(sale_price)          AS revenue,
        COUNT(DISTINCT order_id) AS orders,
        COUNT(DISTINCT user_id)  AS buyers
    FROM items
    GROUP BY month
)
SELECT
    month,
    revenue,
    orders,
    buyers,
    SAFE_DIVIDE(revenue, orders)                                                   AS avg_order_value,
    SAFE_DIVIDE(revenue - LAG(revenue) OVER w, LAG(revenue) OVER w)                AS mom_growth,
    SAFE_DIVIDE(revenue - LAG(revenue, 12) OVER w, LAG(revenue, 12) OVER w)        AS yoy_growth,
    AVG(revenue) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)    AS revenue_3m_avg,
    SUM(revenue) OVER (ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_revenue
FROM monthly
WINDOW w AS (ORDER BY month)
ORDER BY month
