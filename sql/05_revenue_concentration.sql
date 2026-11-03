-- How concentrated is revenue? Customers are ranked into deciles by spend over
-- the last 24 months, with the cumulative share of revenue from the top down.
WITH customers AS (
    SELECT user_id, SUM(sale_price) AS revenue
    FROM `{dataset}.order_items`
    WHERE status NOT IN ('Cancelled', 'Returned')
      AND created_at <  TIMESTAMP('{analysis_end}')
      AND created_at >= TIMESTAMP(DATE_SUB(DATE '{analysis_end}', INTERVAL 24 MONTH))
    GROUP BY user_id
),
deciles AS (
    SELECT revenue, NTILE(10) OVER (ORDER BY revenue DESC) AS decile
    FROM customers
),
by_decile AS (
    SELECT decile, COUNT(*) AS customers, SUM(revenue) AS revenue, MIN(revenue) AS min_customer_revenue
    FROM deciles
    GROUP BY decile
)
SELECT
    decile,
    customers,
    revenue,
    min_customer_revenue,
    revenue / SUM(revenue) OVER ()                                                    AS share_of_revenue,
    SUM(revenue) OVER (ORDER BY decile ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / SUM(revenue) OVER ()                                                        AS cumulative_share_of_revenue
FROM by_decile
ORDER BY decile
