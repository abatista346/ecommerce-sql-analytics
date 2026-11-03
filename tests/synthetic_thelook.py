"""Build a small DuckDB database with the same tables and columns as theLook."""

import duckdb
import numpy as np
import pandas as pd

SOURCES = ["Search", "Organic", "Facebook", "Email", "Display"]
CATEGORIES = [("Women", "Dresses"), ("Women", "Tops & Tees"), ("Men", "Jeans"), ("Men", "Outerwear & Coats")]


def build(seed: int = 0, n_users: int = 2_000, analysis_end: str = "2026-11-01") -> duckdb.DuckDBPyConnection:
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(analysis_end)
    start = end - pd.DateOffset(months=30)

    users = pd.DataFrame({
        "id": np.arange(1, n_users + 1),
        "traffic_source": rng.choice(SOURCES, n_users),
        "created_at": start + pd.to_timedelta(rng.uniform(0, (end - start).days, n_users), unit="D"),
    })

    products = pd.DataFrame({
        "id": np.arange(1, 41),
        "department": [CATEGORIES[i % 4][0] for i in range(40)],
        "category": [CATEGORIES[i % 4][1] for i in range(40)],
        "retail_price": rng.uniform(20, 200, 40).round(2),
    })
    products["cost"] = (products["retail_price"] * rng.uniform(0.4, 0.6, 40)).round(2)

    orders, items = [], []
    order_id = item_id = 0
    for _, u in users.iterrows():
        for k in range(rng.poisson(1.6)):
            order_id += 1
            created = u["created_at"] + pd.Timedelta(days=float(rng.uniform(0, 300)) * k)
            status = rng.choice(["Complete", "Shipped", "Processing", "Cancelled", "Returned"], p=[0.5, 0.2, 0.1, 0.12, 0.08])
            orders.append({"order_id": order_id, "user_id": u["id"], "status": status, "created_at": created, "num_of_item": 0})
            for _ in range(rng.integers(1, 4)):
                item_id += 1
                p = products.sample(1, random_state=int(rng.integers(1e9))).iloc[0]
                items.append({"id": item_id, "order_id": order_id, "user_id": u["id"], "product_id": p["id"],
                              "status": status, "created_at": created, "sale_price": float(p["retail_price"])})
    orders, items = pd.DataFrame(orders), pd.DataFrame(items)

    events, ev_id = [], 0
    for s in range(6_000):
        source = rng.choice(SOURCES)
        when = end - pd.Timedelta(days=float(rng.uniform(1, 400)))
        stages = ["home", "department", "product"]
        if rng.random() < 0.35:
            stages.append("cart")
            if rng.random() < (0.45 if source == "Email" else 0.30):
                stages.append("purchase")
        for seq, ev in enumerate(stages, 1):
            ev_id += 1
            events.append({"id": ev_id, "user_id": None, "sequence_number": seq, "session_id": f"s{s}",
                           "created_at": when + pd.Timedelta(minutes=seq), "traffic_source": source, "event_type": ev})
    events = pd.DataFrame(events)

    # BigQuery TIMESTAMP columns are absolute (UTC) instants; mirror that type.
    for df in (users, orders, items, events):
        df["created_at"] = pd.to_datetime(df["created_at"]).dt.tz_localize("UTC")

    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    con.execute("CREATE SCHEMA thelook")
    for name, df in {"users": users, "products": products, "orders": orders, "order_items": items, "events": events}.items():
        con.register(f"{name}_df", df)
        con.execute(f"CREATE TABLE thelook.{name} AS SELECT * FROM {name}_df")
    return con
