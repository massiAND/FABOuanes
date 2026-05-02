from __future__ import annotations

from app.repositories.transaction_repository import list_transactions_context


def list_operations_api(args=None) -> tuple[list[dict], dict]:
    context = list_transactions_context(args)
    pagination = dict(context.get("pagination") or {})
    meta = {
        "page": int(pagination.get("page") or 1),
        "limit": int(pagination.get("page_size") or 50),
        "page_size": int(pagination.get("page_size") or 50),
        "total": int(pagination.get("total") or 0),
        "returned": len(context.get("transactions") or []),
        "has_next": bool(pagination.get("has_next")),
        "next_url": pagination.get("next_url") or "",
    }
    return [dict(row) for row in context.get("transactions") or []], meta


__all__ = ["list_operations_api", "list_transactions_context"]
