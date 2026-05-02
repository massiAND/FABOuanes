from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import api_error, api_success, require_api_user
from app.api.v1._common import append_date_range, append_text_search, json_response, payment_payload, query_list
from app.core.db_access import query_db
from app.core.permissions import PERMISSION_OPERATIONS_DELETE, PERMISSION_OPERATIONS_READ, PERMISSION_OPERATIONS_WRITE
from app.services.payment_service import create_payment_from_form, delete_payment_by_id, edit_payment_from_form


router = APIRouter(prefix="/api/v1", tags=["payments"])


@router.api_route("/payments", methods=["GET", "POST"])
async def api_payments(request: Request):
    require_api_user(request, PERMISSION_OPERATIONS_WRITE if request.method == "POST" else PERMISSION_OPERATIONS_READ)
    if request.method == "POST":
        payment_id, payment_type = create_payment_from_form(await request.json())
        return json_response(api_success({"payment_type": payment_type, "payment": payment_payload(payment_id)}, status_code=201))

    where: list[str] = []
    params: list[object] = []
    append_text_search(request, where, params, "c.name", "p.notes")
    append_date_range(request, where, params, "p.payment_date")
    kind_filter = str(request.query_params.get("kind", "") or "").strip().lower()
    if kind_filter in {"versement", "avance"}:
        where.append("p.payment_type = ?")
        params.append(kind_filter)
    query = """
        SELECT p.*, c.name AS client_name,
               CASE
                   WHEN p.sale_kind = 'finished' AND p.sale_id IS NOT NULL THEN 'Produit #' || p.sale_id
                   WHEN p.sale_kind = 'raw' AND p.raw_sale_id IS NOT NULL THEN 'Matiere #' || p.raw_sale_id
                   ELSE '-'
               END AS sale_ref
        FROM payments p
        JOIN clients c ON c.id = p.client_id
    """
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY p.payment_date DESC, p.id DESC"
    rows, meta = query_list(request, query, tuple(params))
    return json_response(api_success(rows, meta))


@router.api_route("/payments/{payment_id}", methods=["GET", "PUT", "DELETE"])
async def api_payment_detail(request: Request, payment_id: int):
    permission = {
        "GET": PERMISSION_OPERATIONS_READ,
        "PUT": PERMISSION_OPERATIONS_WRITE,
        "DELETE": PERMISSION_OPERATIONS_DELETE,
    }[request.method]
    require_api_user(request, permission)
    payment = payment_payload(payment_id)
    if not payment:
        api_error("not_found", "Paiement introuvable.", 404)
    if request.method == "PUT":
        edit_payment_from_form(payment_id, await request.json())
        latest = query_db("SELECT id FROM payments ORDER BY id DESC", one=True)
        payment = payment_payload(int(latest["id"])) if latest else None
    elif request.method == "DELETE":
        if not delete_payment_by_id(payment_id):
            api_error("conflict", "Suppression impossible.", 409)
        return json_response(api_success({"deleted": True}))
    return json_response(api_success(payment))
