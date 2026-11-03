-- Monthly acquisition cohorts: what share of customers who first bought in month M
-- buy again in M+1, M+2, ... M+11?
-- A customer's cohort is their first non-cancelled order across the full history,
-- so a customer who first bought years ago is never counted as "new" in a recent cohort.
WITH valid_orders AS (
    SELECT DISTINCT
        user_id,
        DATE_TRUNC(DATE(created_at), MONTH) AS order_month
    FROM `{dataset}.orders`
    WHERE status != 'Cancelled'
      AND created_at < TIMESTAMP('{analysis_end}')
),
first_purchase AS (
    SELECT user_id, MIN(order_month) AS cohort_month
    FROM valid_orders
    GROUP BY user_id
),
cohort_size AS (
    SELECT cohort_month, COUNT(*) AS cohort_customers
    FROM first_purchase
    GROUP BY cohort_month
),
activity AS (
    SELECT
        v.user_id,
        f.cohort_month,
        DATE_DIFF(v.order_month, f.cohort_month, MONTH) AS months_since_first
    FROM valid_orders AS v
    JOIN first_purchase AS f ON v.user_id = f.user_id
)
SELECT
    a.cohort_month,
    c.cohort_customers,
    a.months_since_first,
    COUNT(DISTINCT a.user_id)                       AS active_customers,
    COUNT(DISTINCT a.user_id) / c.cohort_customers  AS retention_rate
FROM activity AS a
JOIN cohort_size AS c ON a.cohort_month = c.cohort_month
WHERE a.cohort_month >= DATE_SUB(DATE '{analysis_end}', INTERVAL 12 MONTH)
  AND a.months_since_first BETWEEN 0 AND 11
GROUP BY a.cohort_month, c.cohort_customers, a.months_since_first
ORDER BY a.cohort_month, a.months_since_first
