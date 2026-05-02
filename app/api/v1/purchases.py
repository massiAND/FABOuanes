from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import api_error, api_success, require_api_user
from app.api.v1._common import append_date_range, append_text_search, json_response, payload_to_form_data, purchase_document_payload, purchase_payload, query_list
from app.core.permissions import PERMISSION_OPERATIONS_DELETE, PERMISSION_OPERATIONS_READ, PERMISSION_OPERATIONS_WRITE
from app.services.purchase_service import (
    create_purchase_from_form,
    delete_purchase_by_id,
    edit_purchase_document_from_form,
    edit_purchase_from_form,
)


router = APIRouter(prefix="/api/v1", tags=["purchases"])


@router.api_route("/purchases", methods=["GET", "POST"])
async def api_purchases(request: Request):
    require_api_user(request, PERMISSION_OPERATIONS_WRITE if request.method == "POST" else PERMISSION_OPERATIONS_READ)
    if request.method == "POST":
        created = create_purchase_from_form(payload_to_form_data(await request.json()))
        if created["mode"] == "line":
            payload = {"mode": "line", "purchase": purchase_payload(int(created["print_item_id"]))}
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
    append_text_search(request, where, params, "COALESCE(s.name, '')", "r.name", "p.notes")
    append_date_range(request, where, params, "p.purchase_date")
    query = """
        SELECT p.*, COALESCE(s.name, 'Sans fournisseur') AS supplier_name, r.name AS material_name, r.unit AS material_unit
        FROM purchases p
        LEFT JOIN suppliers s ON s.id = p.supplier_id
        JOIN raw_materials r ON r.id = p.raw_material_id
    """
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY p.purchase_date DESC, p.id DESC"
    rows, meta = query_list(request, query, tuple(params))
    return json_response(api_success(rows, meta))


@router.api_route("/purchases/{purchase_id}", methods=["GET", "PUT", "DELETE"])
async def api_purchase_detail(request: Request, purchase_id: int):
    permission = {
        "GET": PERMISSION_OPERATIONS_READ,
        "PUT": PERMISSION_OPERATIONS_WRITE,
        "DELETE": PERMISSION_OPERATIONS_DELETE,
    }[request.method]
    require_api_user(request, permission)
    purchase = purchase_payload(purchase_id)
    if not purchase:
        api_error("not_found", "Achat introuvable.", 404)
    if request.method == "PUT":
        if purchase.get("document_id"):
            api_error(
                "document_edit_required",
                "Cette ligne appartient deja a un bon multi-lignes.",
                409,
                {"document_id": int(purchase["document_id"])},
            )
        try:
            result = edit_purchase_from_form(purchase_id, payload_to_form_data(await request.json()))
        except ValueError as exc:
            api_error("purchase_update_invalid", str(exc), 400)
        if result["mode"] == "document":
            return json_response(
                api_success(
                    {
                        "mode": "document",
                        "document_id": int(result["document_id"]),
                        "document": purchase_document_payload(int(result["document_id"])),
                    }
                )
            )
        purchase = purchase_payload(int(result["print_item_id"]))
    elif request.method == "DELETE":
        if not delete_purchase_by_id(purchase_id):
            api_error("conflict", "Suppression impossible.", 409)
        return json_response(api_success({"deleted": True}))
    return json_response(api_success(purchase))


@router.api_route("/purchase-documents/{document_id}", methods=["GET", "PUT"])
async def api_purchase_document_detail(request: Request, document_id: int):
    require_api_user(request, PERMISSION_OPERATIONS_WRITE if request.method == "PUT" else PERMISSION_OPERATIONS_READ)
    document = purchase_document_payload(document_id)
    if not document:
        api_error("not_found", "Bon d'achat introuvable.", 404)
    if request.method == "PUT":
        try:
            edit_purchase_document_from_form(document_id, payload_to_form_data(await request.json()))
        except ValueError as exc:
            api_error("purchase_document_invalid", str(exc), 400)
        document = purchase_document_payload(document_id)
    return json_response(api_success(document))
