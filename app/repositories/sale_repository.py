from __future__ import annotations

import json
from time import monotonic

from app.core.db_access import query_db
from app.utils.pagination import decode_cursor, encode_cursor, keyset_pagination_context, paginated_rows, pagination_context, parse_pagination
from app.core.search import fts_query, sqlite_fts_enabled


_SELLABLE_ITEMS_CACHE = {
    "expires_at": 0.0,
    "data": None,
}


def _is_other_operation_item(name: str | None) -> bool:
    return str(name or "").strip().casefold() == "autre"


def invalidate_sellable_items_cache() -> None:
    _SELLABLE_ITEMS_CACHE["expires_at"] = 0.0
    _SELLABLE_ITEMS_CACHE["data"] = None


def _load_sellable_items():
    items = []
    for product in query_db("SELECT id, name, default_unit AS unit, stock_qty, sale_price, avg_cost FROM finished_products ORDER BY name"):
        items.append(
            {
                "key": f"finished:{product['id']}",
                "label": f"{product['name']} - produit final",
                "unit": product["unit"],
                "stock_qty": product["stock_qty"],
                "sale_price": product["sale_price"],
                "avg_cost": product["avg_cost"],
                "force_unit": "",
                "custom_name_required": "",
            }
        )
    for raw_material in query_db(
        """
        SELECT id, name, unit, stock_qty, sale_price, avg_cost
        FROM raw_materials
        ORDER BY CASE WHEN upper(trim(name)) = 'AUTRE' THEN 1 ELSE 0 END, name
        """
    ):
        is_other = _is_other_operation_item(raw_material["name"])
        items.append(
            {
                "key": f"raw:{raw_material['id']}",
                "label": f"{raw_material['name']} - {'autre produit' if is_other else 'matière première'}",
                "unit": raw_material["unit"],
                "stock_qty": raw_material["stock_qty"],
                "sale_price": raw_material["sale_price"],
                "avg_cost": raw_material["avg_cost"],
                "force_unit": "unite" if is_other else "",
                "custom_name_required": "1" if is_other else "",
            }
        )
    return items


def build_sellable_items():
    now = monotonic()
    data = _SELLABLE_ITEMS_CACHE["data"]
    if data is not None and now < float(_SELLABLE_ITEMS_CACHE["expires_at"] or 0):
        return data
    data = _load_sellable_items()
    _SELLABLE_ITEMS_CACHE["data"] = data
    _SELLABLE_ITEMS_CACHE["expires_at"] = now + 30.0
    return data


def list_sales_page_context(args=None):
    items = build_sellable_items()
    page, page_size, offset = parse_pagination(args or {})
    cursor = decode_cursor(str((args or {}).get("cursor", "") or ""), 2)
    where: list[str] = []
    params: list[object] = []
    q = str((args or {}).get("q", "") or "").strip()
    sale_date = str((args or {}).get("date", "") or "").strip()
    if q:
        if sqlite_fts_enabled("sales_fts"):
            where.append("row_sort_key IN (SELECT row_key FROM sales_fts WHERE sales_fts MATCH ?)")
            params.append(fts_query(q))
        else:
            where.append("LOWER(COALESCE(client_name, '') || ' ' || COALESCE(item_name, '') || ' ' || COALESCE(item_kind, '')) LIKE LOWER(?)")
            params.append(f"%{q}%")
    if sale_date:
        where.append("sale_date = ?")
        params.append(sale_date)
    query = """
        SELECT * FROM (
            SELECT s.id, s.document_id, s.client_id, s.sale_date, 'finished:' || s.id AS row_sort_key, COALESCE(c.name, 'Comptoir') AS client_name, f.name AS item_name, s.quantity, s.unit, s.total, s.amount_paid, s.balance_due, s.profit_amount, 'Produit final' AS item_kind, 'finished' AS row_kind
            FROM sales s
            LEFT JOIN clients c ON c.id = s.client_id
            JOIN finished_products f ON f.id = s.finished_product_id
            UNION ALL
            SELECT rs.id, rs.document_id, rs.client_id, rs.sale_date, 'raw:' || rs.id AS row_sort_key, COALESCE(c.name, 'Comptoir') AS client_name, COALESCE(NULLIF(rs.custom_item_name, ''), r.name) AS item_name, rs.quantity, rs.unit, rs.total, rs.amount_paid, rs.balance_due, rs.profit_amount, 'Matière première' AS item_kind, 'raw' AS row_kind
            FROM raw_sales rs
            LEFT JOIN clients c ON c.id = rs.client_id
            JOIN raw_materials r ON r.id = rs.raw_material_id
        ) x
    """
    if where:
        query += " WHERE " + " AND ".join(where)
    count_query = query
    total_row = query_db(f"SELECT COUNT(*) AS c FROM ({count_query}) sales_count", tuple(params), one=True)
    total = int(total_row["c"] if total_row else 0)
    cursor_where = ""
    cursor_params: list[object] = []
    if cursor:
        cursor_where = " AND " if where else " WHERE "
        cursor_where += "(sale_date < ? OR (sale_date = ? AND row_sort_key < ?))"
        cursor_params.extend([cursor[0], cursor[0], cursor[1]])
    rows_plus = query_db(
        f"{query}{cursor_where} ORDER BY sale_date DESC, row_sort_key DESC LIMIT ?",
        tuple(params + cursor_params + [page_size + 1]),
    )
    has_next = len(rows_plus) > page_size
    rows = rows_plus[:page_size]
    next_cursor = ""
    if has_next and rows:
        last = rows[-1]
        next_cursor = encode_cursor(last["sale_date"], last["row_sort_key"])
    return {
        "sales": rows,
        "clients": query_db("SELECT * FROM clients ORDER BY name"),
        "sellable_items": items,
        "sellable_json": json.dumps(items),
        "filters": {"q": q, "date": sale_date},
        "pagination": keyset_pagination_context(
            "sales",
            args or {},
            total=total,
            page=page,
            page_size=page_size,
            returned=len(rows),
            next_cursor=next_cursor,
        ),
    }


def get_sale(kind: str, row_id: int):
    if kind == "finished":
        return query_db(
            """
            SELECT s.*, COALESCE(c.name, 'Comptoir') AS client_name, f.name AS item_name,
                   '' AS custom_item_name, 'finished' AS row_kind, 'finished:' || s.finished_product_id AS item_key
            FROM sales s
            LEFT JOIN clients c ON c.id = s.client_id
            JOIN finished_products f ON f.id = s.finished_product_id
            WHERE s.id = ?
            """,
            (row_id,),
            one=True,
        )
    return query_db(
        """
        SELECT rs.*, COALESCE(c.name, 'Comptoir') AS client_name, COALESCE(NULLIF(rs.custom_item_name, ''), r.name) AS item_name,
               rs.custom_item_name, 'raw' AS row_kind, 'raw:' || rs.raw_material_id AS item_key
        FROM raw_sales rs
        LEFT JOIN clients c ON c.id = rs.client_id
        JOIN raw_materials r ON r.id = rs.raw_material_id
        WHERE rs.id = ?
        """,
        (row_id,),
        one=True,
    )


def get_sale_document(document_id: int):
    return query_db(
        """
        SELECT sd.*, COALESCE(c.name, 'Comptoir') AS client_name
        FROM sale_documents sd
        LEFT JOIN clients c ON c.id = sd.client_id
        WHERE sd.id = ?
        """,
        (document_id,),
        one=True,
    )


def list_sale_document_lines(document_id: int):
    return query_db(
        """
        SELECT * FROM (
            SELECT s.id AS row_id, s.document_id, s.client_id, s.sale_date, s.notes, s.sale_type,
                   s.quantity, s.unit, s.unit_price, s.total, s.amount_paid, s.balance_due,
                   f.name AS item_name, '' AS custom_item_name, 'Produit final' AS item_kind, 'finished' AS row_kind,
                   'finished:' || s.finished_product_id AS item_key
            FROM sales s
            JOIN finished_products f ON f.id = s.finished_product_id
            WHERE s.document_id = ?
            UNION ALL
            SELECT rs.id AS row_id, rs.document_id, rs.client_id, rs.sale_date, rs.notes, rs.sale_type,
                   rs.quantity, rs.unit, rs.unit_price, rs.total, rs.amount_paid, rs.balance_due,
                   COALESCE(NULLIF(rs.custom_item_name, ''), r.name) AS item_name, rs.custom_item_name, 'Matière première' AS item_kind, 'raw' AS row_kind,
                   'raw:' || rs.raw_material_id AS item_key
            FROM raw_sales rs
            JOIN raw_materials r ON r.id = rs.raw_material_id
            WHERE rs.document_id = ?
        ) lines
        ORDER BY row_id ASC
        """,
        (document_id, document_id),
    )
