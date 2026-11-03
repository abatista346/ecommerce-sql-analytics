-- Category performance over the last 12 months: revenue, gross margin and return rate,
-- ranked within each department.
-- Revenue and margin exclude cancelled and returned items; the return rate is
-- computed over all non-cancelled items, since a return is only possible after a sale.
WITH items AS (
    SELECT
        p.department,
        p.category,
        oi.status,
        oi.sale_price,
        p.cost
    FROM `{dataset}.order_items` AS oi
    JOIN `{dataset}.products`    AS p ON oi.product_id = p.id
    WHERE oi.status != 'Cancelled'
      AND oi.created_at <  TIMESTAMP('{analysis_end}')
      AND oi.created_at >= TIMESTAMP(DATE_SUB(DATE '{analysis_end}', INTERVAL 12 MONTH))
),
by_category AS (
    SELECT
        department,
        category,
        COUNT(*)                                                         AS items_sold,
        COUNTIF(status = 'Returned')                                     AS items_returned,
        SUM(IF(status != 'Returned', sale_price, 0))                     AS net_revenue,
        SUM(IF(status != 'Returned', sale_price - cost, 0))              AS gross_margin
    FROM items
    GROUP BY department, category
)
SELECT
    department,
    category,
    items_sold,
    items_returned,
    net_revenue,
    gross_margin,
    SAFE_DIVIDE(gross_margin, net_revenue)                                         AS margin_rate,
    SAFE_DIVIDE(items_returned, items_sold)                                        AS return_rate,
    RANK() OVER (PARTITION BY department ORDER BY gross_margin DESC)               AS margin_rank_in_department,
    net_revenue / SUM(net_revenue) OVER (PARTITION BY department)                  AS share_of_department_revenue
FROM by_category
ORDER BY department, margin_rank_in_department
