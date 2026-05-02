from __future__ import annotations

from app.core.db_access import execute_db, query_db


def get_raw_material(material_id: int):
    return query_db("SELECT * FROM raw_materials WHERE id = ?", (material_id,), one=True)


def get_finished_product(product_id: int):
    return query_db("SELECT * FROM finished_products WHERE id = ?", (product_id,), one=True)


def update_raw_stock(material_id: int, stock_qty: float) -> None:
    execute_db("UPDATE raw_materials SET stock_qty = ? WHERE id = ?", (stock_qty, material_id))


def update_finished_stock(product_id: int, stock_qty: float) -> None:
    execute_db("UPDATE finished_products SET stock_qty = ? WHERE id = ?", (stock_qty, product_id))


def insert_stock_movement(
    item_kind: str,
    item_id: int,
    direction: str,
    quantity: float,
    unit: str,
    stock_before: float,
    stock_after: float,
    reason: str,
    reference_type: str,
    reference_id: int | None,
    username: str,
) -> None:
    execute_db(
        """
        INSERT INTO stock_movements (
            item_kind, item_id, direction, quantity, unit, stock_before, stock_after,
            reason, reference_type, reference_id, created_by_username, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            item_kind,
            int(item_id),
            direction,
            float(quantity),
            unit,
            float(stock_before),
            float(stock_after),
            reason,
            reference_type,
            reference_id,
            username,
        ),
    )
