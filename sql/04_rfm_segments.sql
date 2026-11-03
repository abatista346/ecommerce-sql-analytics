-- RFM segmentation of customers active in the last 24 months.
-- Recency and monetary value are scored in quintiles with NTILE.
-- Frequency is NOT scored with NTILE: most customers have one or two orders, and
-- NTILE would split identical order counts into different scores arbitrarily.
-- Fixed, interpretable buckets are used instead.
WITH customers AS (
    SELECT
        user_id,
        DATE_DIFF(DATE '{analysis_end}', DATE(MAX(created_at)), DAY) AS recency_days,
        COUNT(DISTINCT order_id)                                      AS frequency,
        SUM(sale_price)                                               AS monetary
    FROM `{dataset}.order_items`
    WHERE status NOT IN ('Cancelled', 'Returned')
      AND created_at <  TIMESTAMP('{analysis_end}')
      AND created_at >= TIMESTAMP(DATE_SUB(DATE '{analysis_end}', INTERVAL 24 MONTH))
    GROUP BY user_id
),
scored AS (
    SELECT
        *,
        NTILE(5) OVER (ORDER BY recency_days DESC) AS r_score,
        CASE WHEN frequency >= 4 THEN 4 ELSE frequency END AS f_bucket,
        NTILE(5) OVER (ORDER BY monetary)          AS m_score
    FROM customers
),
segmented AS (
    SELECT
        *,
        CASE
            WHEN r_score >= 4 AND f_bucket >= 2 THEN 'Champions'
            WHEN r_score >= 4 AND f_bucket = 1  THEN 'New customers'
            WHEN r_score  = 3 AND f_bucket >= 2 THEN 'Loyal'
            WHEN r_score  = 3 AND f_bucket = 1  THEN 'Needs nurturing'
            WHEN r_score <= 2 AND f_bucket >= 2 THEN 'At risk'
            ELSE 'Hibernating'
        END AS segment
    FROM scored
)
SELECT
    segment,
    COUNT(*)                                          AS customers,
    SUM(monetary)                                     AS revenue,
    AVG(recency_days)                                 AS avg_recency_days,
    AVG(frequency)                                    AS avg_orders,
    AVG(monetary)                                     AS avg_revenue_per_customer,
    COUNT(*) / SUM(COUNT(*)) OVER ()                  AS share_of_customers,
    SUM(monetary) / SUM(SUM(monetary)) OVER ()        AS share_of_revenue
FROM segmented
GROUP BY segment
ORDER BY revenue DESC
