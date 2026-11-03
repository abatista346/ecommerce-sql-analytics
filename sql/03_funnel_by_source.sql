-- Session funnel over the last 12 months: product view -> add to cart -> purchase,
-- split by traffic source, plus an overall row via ROLLUP.
-- Each stage counts sessions that reached that stage AND every stage before it,
-- so the funnel is strictly non-increasing.
WITH sessions AS (
    SELECT
        session_id,
        ANY_VALUE(traffic_source)                               AS traffic_source,
        MAX(IF(event_type = 'product', 1, 0))                   AS viewed_product,
        MAX(IF(event_type = 'cart', 1, 0))                      AS added_to_cart,
        MAX(IF(event_type = 'purchase', 1, 0))                  AS purchased
    FROM `{dataset}.events`
    WHERE created_at <  TIMESTAMP('{analysis_end}')
      AND created_at >= TIMESTAMP(DATE_SUB(DATE '{analysis_end}', INTERVAL 12 MONTH))
    GROUP BY session_id
),
staged AS (
    SELECT
        traffic_source,
        viewed_product                                   AS reached_product,
        viewed_product * added_to_cart                   AS reached_cart,
        viewed_product * added_to_cart * purchased       AS reached_purchase
    FROM sessions
)
SELECT
    COALESCE(traffic_source, 'All sources')                       AS traffic_source,
    COUNT(*)                                                      AS sessions,
    SUM(reached_product)                                          AS product_view_sessions,
    SUM(reached_cart)                                             AS cart_sessions,
    SUM(reached_purchase)                                         AS purchase_sessions,
    SAFE_DIVIDE(SUM(reached_cart), SUM(reached_product))          AS view_to_cart_rate,
    SAFE_DIVIDE(SUM(reached_purchase), SUM(reached_cart))         AS cart_to_purchase_rate,
    SAFE_DIVIDE(SUM(reached_purchase), COUNT(*))                  AS session_conversion_rate
FROM staged
GROUP BY ROLLUP (traffic_source)
ORDER BY sessions DESC
