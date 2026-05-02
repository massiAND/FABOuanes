from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import api_error, api_success, require_api_user
from app.api.v1._common import (
    append_date_range,
    append_text_search,
    filtered_sellable_items,
    json_response,
    payload_to_form_data,
    query_list,
    sale_document_payload,
    sale_payload,
)
from app.core.permissions import PERMISSION_CATALOG_READ, PERMISSION_OPERATIONS_DELETE, PERMISSION_OPERATIONS_READ, PERMISSION_OPERATIONS_WRITE
from app.services.sale_service import (
    create_sale_from_form,
    delete_sale_by_id,
    edit_sale_document_from_form,
    edit_sale_from_form,
)


router = APIRouter(prefix="/api/v1", tags=["sales"])


@router.get("/sellable-items")
async def api_sellable_items(request: Request):
    require_api_user(request, PERMISSION_CATALOG_READ)
    return json_response(filtered_sellable_items(request))


@router.api_route("/sales", methods=["GET", "POST"])
async def api_sales(request: Request):
    require_api_user(request, PERMISSION_OPERATIONS_WRITE if request.method == "POST" else PERMISSION_OPERATIONS_READ)
    if request.method == "POST":
        created = create_sale_from_form(payload_to_form_data(await request.json()))
        if created["mode"] == "line":
            payload = {
                "mode": "line",
                "kind": created["first_line_kind"],
                "sale": sale_payload(created["first_line_kind"], int(created["first_line_id"])),
            }
        else:
            payload = {
                "mode": "document",
                "document_id": int(created["document_id"]),
                "line_count": int(created["line_count"]),
                "print_doc_type": created["print_doc_type"],
                "print_item_id": int(created["print_item_id"]),
            }
        return json_response(api_success(payload, status_code=201))

    where: list[str] = []
    params: list[object] = []
    append_text_search(request, where, params, "client_name", "item_name", "notes")
    append_date_range(request, where, params, "sale_date")
    kind_filter = str(request.query_params.get("kind", "") or "").strip().lower()
    status_filter = str(request.query_params.get("status", "") or "").strip().lower()
    if kind_filter in {"finished", "raw"}:
        where.append("row_kind = ?")
        params.append(kind_filter)
    if status_filter == "paid":
        where.append("balance_due <= 0")
    elif status_filter == "due":
        where.append("balance_due > 0")
    elif status_filter in {"cash", "credit"}:
        where.append("sale_type = ?")
        params.append(status_filter)
    query = """
        SELECT * FROM (
            SELECT s.id, s.sale_date, COALESCE(c.name, 'Comptoir') AS client_name, f.name AS item_name,
                   s.document_id, s.quantity, s.unit, s.total, s.amount_paid, s.balance_due, s.profit_amount, s.sale_type, s.notes,
                   'Produit fini' AS item_kind, 'finished' AS row_kind
            FROM sales s
            LEFT JOIN clients c ON c.id = s.client_id
            JOIN finished_products f ON f.id = s.finished_product_id
            UNION ALL
            SELECT rs.id, rs.sale_date, COALESCE(c.name, 'Comptoir') AS client_name, r.name AS item_name,
                   rs.document_id, rs.quantity, rs.unit, rs.total, rs.amount_paid, rs.balance_due, rs.profit_amount, rs.sale_type, rs.notes,
                   'Matiere premiere' AS item_kind, 'raw' AS row_kind
            FROM raw_sales rs
            LEFT JOIN clients c ON c.id = rs.client_id
            JOIN raw_materials r ON r.id = rs.raw_material_id
        ) x
    """
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY sale_date DESC, id DESC"
    rows, meta = query_list(request, query, tuple(params))
    return json_response(api_success(rows, meta))


@router.api_route("/sales/{kind}/{row_id}", methods=["GET", "PUT", "DELETE"])
async def api_sale_detail(request: Request, kind: str, row_id: int):
    permission = {
        "GET": PERMISSION_OPERATIONS_READ,
        "PUT": PERMISSION_OPERATIONS_WRITE,
        "DELETE": PERMISSION_OPERATIONS_DELETE,
    }[request.method]
    require_api_user(request, permission)
    sale = sale_payload(kind, row_id)
    if not sale:
        api_error("not_found", "Vente introuvable.", 404)
    if request.method == "PUT":
        if sale.get("document_id"):
            api_error(
                "document_edit_required",
                "Cette ligne appartient deja a une facture multi-lignes.",
                409,
                {"document_id": int(sale["document_id"])},
            )
        try:
            result = edit_sale_from_form(kind, row_id, payload_to_form_data(await request.json()))
        except ValueError as exc:
            if "versements" in str(exc).lower():
                api_error("document_has_payments", str(exc), 409)
            api_error("sale_update_invalid", str(exc), 400)
        if result["mode"] == "document":
            return json_response(
                api_success(
                    {
                        "mode": "document",
                        "document_id": int(result["document_id"]),
                        "document": sale_document_payload(int(result["document_id"])),
                    }
                )
            )
        sale = sale_payload(result["first_line_kind"], int(result["first_line_id"])) or sale
    elif request.method == "DELETE":
        if not delete_sale_by_id(kind, row_id):
            api_error("conflict", "Suppression impossible.", 409)
        return json_response(api_success({"deleted": True}))
    return json_response(api_success(sale))


@router.api_route("/sale-documents/{document_id}", methods=["GET", "PUT"])
async def api_sale_document_detail(request: Request, document_id: int):
    require_api_user(request, PERMISSION_OPERATIONS_WRITE if request.method == "PUT" else PERMISSION_OPERATIONS_READ)
    document = sale_document_payload(document_id)
    if not document:
        api_error("not_found", "Facture introuvable.", 404)
    if request.method == "PUT":
        try:
            edit_sale_document_from_form(document_id, payload_to_form_data(await request.json()))
        except ValueError as exc:
            if "versements" in str(exc).lower():
                api_error("document_has_payments", str(exc), 409, {"document_id": document_id})
            api_error("sale_document_invalid", str(exc), 400)
        document = sale_document_payload(document_id)
    return json_response(api_success(document))


@router.get("/recent-operations")
async def api_recent_operations(request: Request):
    require_api_user(request, PERMISSION_OPERATIONS_READ)
    where: list[str] = []
    params: list[object] = []
    append_text_search(request, where, params, "partner_name", "item_name", "notes", "operation_label")
    append_date_range(request, where, params, "event_date")
    kind_filter = str(request.query_params.get("kind", "") or "").strip().lower()
    if kind_filter in {"sale", "payment", "purchase", "production"}:
        where.append("operation_type = ?")
        params.append(kind_filter)
    query = """
        SELECT * FROM (
            SELECT 'sale' AS operation_type, s.id AS row_id, s.sale_date AS event_date,
                   COALESCE(c.name, 'Comptoir') AS partner_name, f.name AS item_name, s.notes,
                   s.total AS amount, s.balance_due AS balance_due, 'Vente produit final' AS operation_label
            FROM sales s
            LEFT JOIN clients c ON c.id = s.client_id
            JOIN finished_products f ON f.id = s.finished_product_id
            UNION ALL
            SELECT 'sale' AS operation_type, rs.id AS row_id, rs.sale_date AS event_date,
                   COALESCE(c.name, 'Comptoir') AS partner_name, r.name AS item_name, rs.notes,
                   rs.total AS amount, rs.balance_due AS balance_due, 'Vente matiere premiere' AS operation_label
            FROM raw_sales rs
            LEFT JOIN clients c ON c.id = rs.client_id
            JOIN raw_materials r ON r.id = rs.raw_material_id
            UNION ALL
            SELECT 'payment' AS operation_type, p.id AS row_id, p.payment_date AS event_date,
                   c.name AS partner_name,
                   CASE WHEN p.payment_type = 'avance' THEN 'Avance client' ELSE 'Versement client' END AS item_name,
                   p.notes, p.amount AS amount, 0 AS balance_due,
                   CASE WHEN p.payment_type = 'avance' THEN 'Avance' ELSE 'Versement' END AS operation_label
            FROM payments p
            JOIN clients c ON c.id = p.client_id
            UNION ALL
            SELECT 'purchase' AS operation_type, p.id AS row_id, p.purchase_date AS event_date,
                   COALESCE(s.name, 'Sans fournisseur') AS partner_name, r.name AS item_name, p.notes,
                   p.total AS amount, 0 AS balance_due, 'Achat' AS operation_label
            FROM purchases p
            LEFT JOIN suppliers s ON s.id = p.supplier_id
            JOIN raw_materials r ON r.id = p.raw_material_id
            UNION ALL
            SELECT 'production' AS operation_type, pb.id AS row_id, pb.production_date AS event_date,
                   '' AS partner_name, fp.name AS item_name, pb.notes,
                   pb.production_cost AS amount, 0 AS balance_due, 'Production' AS operation_label
            FROM production_batches pb
            JOIN finished_products fp ON fp.id = pb.finished_product_id
        ) x
    """
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY event_date DESC, row_id DESC"
    rows, meta = query_list(request, query, tuple(params))
    return json_response(api_success(rows, meta))
