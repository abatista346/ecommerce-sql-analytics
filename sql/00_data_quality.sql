-- Data-quality checks before any analysis.
-- theLook is a synthetic dataset that is regenerated daily, so some rows carry
-- timestamps after the analysis cut-off; those are counted here and excluded downstream.
SELECT
    (SELECT COUNT(*) FROM `{dataset}.orders`)                                            AS n_orders,
    (SELECT COUNTIF(created_at >= TIMESTAMP('{analysis_end}')) FROM `{dataset}.orders`)  AS n_orders_after_cutoff,
    (SELECT MIN(created_at) FROM `{dataset}.orders`)                                     AS first_order_at,
    (SELECT COUNT(*)
       FROM `{dataset}.orders` AS o
      WHERE NOT EXISTS (SELECT 1 FROM `{dataset}.order_items` AS oi WHERE oi.order_id = o.order_id))
                                                                                         AS n_orders_without_items,
    (SELECT COUNT(*) - COUNT(DISTINCT id) FROM `{dataset}.order_items`)                  AS n_duplicate_item_ids,
    (SELECT COUNTIF(sale_price <= 0) FROM `{dataset}.order_items`)                       AS n_nonpositive_prices,
    (SELECT COUNT(*)
       FROM `{dataset}.orders` AS o
       LEFT JOIN `{dataset}.users` AS u ON o.user_id = u.id
      WHERE u.id IS NULL)                                                                AS n_orders_without_user,
    (SELECT COUNTIF(status = 'Cancelled') / COUNT(*) FROM `{dataset}.order_items`)       AS share_items_cancelled,
    (SELECT COUNTIF(status = 'Returned') / COUNT(*) FROM `{dataset}.order_items`)        AS share_items_returned
