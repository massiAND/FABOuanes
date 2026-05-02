from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import api_error, api_success, require_api_user
from app.api.v1._common import append_date_range, append_text_search, json_response, payload_to_form_data, production_payload, query_list
from app.core.db_access import query_db
from app.core.permissions import PERMISSION_PRODUCTION_DELETE, PERMISSION_PRODUCTION_READ, PERMISSION_PRODUCTION_WRITE
from app.services.production_service import create_production_from_form, delete_production_by_id


router = APIRouter(prefix="/api/v1", tags=["production"])


@router.api_route("/production-batches", methods=["GET", "POST"])
async def api_production_batches(request: Request):
    require_api_user(request, PERMISSION_PRODUCTION_WRITE if request.method == "POST" else PERMISSION_PRODUCTION_READ)
    if request.method == "POST":
        payload = await request.json()
        result = create_production_from_form(
            payload_to_form_data(
                {
                    "finished_product_id": payload.get("finished_product_id"),
                    "output_quantity": payload.get("output_quantity"),
                    "production_date": payload.get("production_date"),
                    "notes": payload.get("notes", ""),
                    "recipe_name": payload.get("recipe_name", ""),
                    "save_recipe": payload.get("save_recipe", 0),
                    "raw_material_id[]": payload.get("raw_material_id[]", payload.get("raw_material_ids", [])),
                    "quantity[]": payload.get("quantity[]", payload.get("quantities", [])),
                }
            )
        )
        return json_response(api_success({"batch": production_payload(result["batch_id"]), "recipe_id": result["recipe_id"]}, status_code=201))

    where: list[str] = []
    params: list[object] = []
    append_text_search(request, where, params, "fp.name", "pb.notes")
    append_date_range(request, where, params, "pb.production_date")
    query = """
        SELECT pb.*, fp.name AS product_name, fp.default_unit AS product_unit
        FROM production_batches pb
        JOIN finished_products fp ON fp.id = pb.finished_product_id
    """
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY pb.production_date DESC, pb.id DESC"
    rows, meta = query_list(request, query, tuple(params))
    return json_response(api_success(rows, meta))


@router.api_route("/production-batches/{batch_id}", methods=["GET", "DELETE"])
async def api_production_batch_detail(request: Request, batch_id: int):
    require_api_user(request, PERMISSION_PRODUCTION_DELETE if request.method == "DELETE" else PERMISSION_PRODUCTION_READ)
    batch = production_payload(batch_id)
    if not batch:
        api_error("not_found", "Production introuvable.", 404)
    if request.method == "DELETE":
        if not delete_production_by_id(batch_id):
            api_error("conflict", "Suppression impossible.", 409)
        return json_response(api_success({"deleted": True}))
    items = query_db("SELECT * FROM production_batch_items WHERE batch_id = ? ORDER BY id", (batch_id,))
    payload = dict(batch)
    payload["items"] = [dict(item) for item in items]
    return json_response(api_success(payload))


@router.get("/recipes")
async def api_recipes(request: Request):
    require_api_user(request, PERMISSION_PRODUCTION_READ)
    rows, meta = query_list(
        request,
        """
        SELECT sr.*, fp.name AS finished_product_name
        FROM saved_recipes sr
        JOIN finished_products fp ON fp.id = sr.finished_product_id
        ORDER BY sr.id DESC
        """,
    )
    return json_response(api_success(rows, meta))


@router.get("/recipes/{recipe_id}")
async def api_recipe_detail(request: Request, recipe_id: int):
    require_api_user(request, PERMISSION_PRODUCTION_READ)
    row = query_db("SELECT * FROM saved_recipes WHERE id = ?", (recipe_id,), one=True)
    if not row:
        api_error("not_found", "Recette introuvable.", 404)
    items = query_db("SELECT * FROM saved_recipe_items WHERE recipe_id = ? ORDER BY position, id", (recipe_id,))
    payload = dict(row)
    payload["items"] = [dict(item) for item in items]
    return json_response(api_success(payload))
