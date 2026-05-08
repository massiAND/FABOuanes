from __future__ import annotations

import re

from app.core.config import settings
from app.core.db import connect_database
from app.core.schema import init_db


def _adapt_schema_sql(sql: str) -> str:
    """
    Adapt schema SQL from PostgreSQL to target database (SQLite, etc).
    """
    if not settings.database_url.startswith("sqlite"):
        return sql
    
    # Process the schema for SQLite
    # First, do global replacements
    sql = re.sub(r'\bBIGSERIAL\s+PRIMARY\s+KEY\b', 'INTEGER PRIMARY KEY AUTOINCREMENT', sql)
    sql = re.sub(r'\bBIGSERIAL\b', 'INTEGER', sql)
    sql = re.sub(r'\bDOUBLE\s+PRECISION\b', 'REAL', sql)
    sql = sql.replace('::text', '')
    
    # For SQLite, use CURRENT_TIMESTAMP instead of datetime('now')
    # SQLite supports CURRENT_TIMESTAMP as a special keyword
    sql = sql.replace("CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP")
    
    # Remove CHECK constraints - handle nested parens
    # First, remove CHECK(...) with nested parentheses
    while 'CHECK' in sql:
        # Find and remove CHECK(...) - matching nested parentheses
        match = re.search(r'\s*CHECK\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)', sql, re.IGNORECASE)
        if match:
            sql = sql[:match.start()] + sql[match.end():]
        else:
            break
    
    # Clean up any dangling commas left by CHECK removal
    sql = re.sub(r',\s*\)', ')', sql)
    sql = re.sub(r',\s*,', ',', sql)
    
    # Remove ON DELETE CASCADE and other constraint clauses that might cause issues
    sql = re.sub(r'\s+ON\s+(DELETE|UPDATE)\s+\w+', '', sql, flags=re.IGNORECASE)
    
    return sql


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'operator' CHECK(role IN ('admin','manager','operator')),
    must_change_password INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    last_login_at TEXT,
    last_password_change_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
);

CREATE TABLE IF NOT EXISTS clients (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT,
    address TEXT,
    notes TEXT,
    opening_credit DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
);

CREATE TABLE IF NOT EXISTS suppliers (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT,
    address TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
);

CREATE TABLE IF NOT EXISTS raw_materials (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    unit TEXT NOT NULL DEFAULT 'kg',
    stock_qty DOUBLE PRECISION NOT NULL DEFAULT 0,
    avg_cost DOUBLE PRECISION NOT NULL DEFAULT 0,
    sale_price DOUBLE PRECISION NOT NULL DEFAULT 0,
    alert_threshold DOUBLE PRECISION NOT NULL DEFAULT 0,
    threshold_qty DOUBLE PRECISION NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS finished_products (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    default_unit TEXT NOT NULL DEFAULT 'kg',
    stock_qty DOUBLE PRECISION NOT NULL DEFAULT 0,
    sale_price DOUBLE PRECISION NOT NULL DEFAULT 0,
    avg_cost DOUBLE PRECISION NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS purchase_documents (
    id BIGSERIAL PRIMARY KEY,
    supplier_id BIGINT REFERENCES suppliers(id) ON DELETE SET NULL,
    total DOUBLE PRECISION NOT NULL DEFAULT 0,
    purchase_date TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
);

CREATE TABLE IF NOT EXISTS sale_documents (
    id BIGSERIAL PRIMARY KEY,
    client_id BIGINT REFERENCES clients(id) ON DELETE SET NULL,
    sale_type TEXT NOT NULL CHECK(sale_type IN ('cash','credit')),
    total DOUBLE PRECISION NOT NULL DEFAULT 0,
    amount_paid DOUBLE PRECISION NOT NULL DEFAULT 0,
    balance_due DOUBLE PRECISION NOT NULL DEFAULT 0,
    sale_date TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
);

CREATE TABLE IF NOT EXISTS purchases (
    id BIGSERIAL PRIMARY KEY,
    supplier_id BIGINT REFERENCES suppliers(id) ON DELETE SET NULL,
    document_id BIGINT,
    raw_material_id BIGINT NOT NULL REFERENCES raw_materials(id) ON DELETE CASCADE,
    quantity DOUBLE PRECISION NOT NULL,
    unit TEXT NOT NULL DEFAULT 'kg',
    unit_price DOUBLE PRECISION NOT NULL,
    total DOUBLE PRECISION NOT NULL,
    purchase_date TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS production_batches (
    id BIGSERIAL PRIMARY KEY,
    finished_product_id BIGINT NOT NULL REFERENCES finished_products(id) ON DELETE CASCADE,
    output_quantity DOUBLE PRECISION NOT NULL,
    production_cost DOUBLE PRECISION NOT NULL DEFAULT 0,
    unit_cost DOUBLE PRECISION NOT NULL DEFAULT 0,
    production_date TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS production_batch_items (
    id BIGSERIAL PRIMARY KEY,
    batch_id BIGINT NOT NULL REFERENCES production_batches(id) ON DELETE CASCADE,
    raw_material_id BIGINT NOT NULL REFERENCES raw_materials(id) ON DELETE CASCADE,
    quantity DOUBLE PRECISION NOT NULL,
    unit_cost_snapshot DOUBLE PRECISION NOT NULL DEFAULT 0,
    line_cost DOUBLE PRECISION NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS saved_recipes (
    id BIGSERIAL PRIMARY KEY,
    finished_product_id BIGINT NOT NULL REFERENCES finished_products(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    notes TEXT,
    created_by_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
);

CREATE TABLE IF NOT EXISTS saved_recipe_items (
    id BIGSERIAL PRIMARY KEY,
    recipe_id BIGINT NOT NULL REFERENCES saved_recipes(id) ON DELETE CASCADE,
    raw_material_id BIGINT NOT NULL REFERENCES raw_materials(id) ON DELETE CASCADE,
    quantity DOUBLE PRECISION NOT NULL,
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sales (
    id BIGSERIAL PRIMARY KEY,
    client_id BIGINT REFERENCES clients(id) ON DELETE SET NULL,
    document_id BIGINT,
    finished_product_id BIGINT NOT NULL REFERENCES finished_products(id) ON DELETE CASCADE,
    quantity DOUBLE PRECISION NOT NULL,
    unit TEXT NOT NULL,
    unit_price DOUBLE PRECISION NOT NULL,
    total DOUBLE PRECISION NOT NULL,
    sale_type TEXT NOT NULL CHECK(sale_type IN ('cash','credit')),
    amount_paid DOUBLE PRECISION NOT NULL DEFAULT 0,
    balance_due DOUBLE PRECISION NOT NULL DEFAULT 0,
    cost_price_snapshot DOUBLE PRECISION NOT NULL DEFAULT 0,
    profit_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    sale_date TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS raw_sales (
    id BIGSERIAL PRIMARY KEY,
    client_id BIGINT REFERENCES clients(id) ON DELETE SET NULL,
    document_id BIGINT,
    raw_material_id BIGINT NOT NULL REFERENCES raw_materials(id) ON DELETE CASCADE,
    quantity DOUBLE PRECISION NOT NULL,
    unit TEXT NOT NULL,
    unit_price DOUBLE PRECISION NOT NULL,
    total DOUBLE PRECISION NOT NULL,
    sale_type TEXT NOT NULL CHECK(sale_type IN ('cash','credit')),
    amount_paid DOUBLE PRECISION NOT NULL DEFAULT 0,
    balance_due DOUBLE PRECISION NOT NULL DEFAULT 0,
    cost_price_snapshot DOUBLE PRECISION NOT NULL DEFAULT 0,
    profit_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    sale_date TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS payments (
    id BIGSERIAL PRIMARY KEY,
    client_id BIGINT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    sale_id BIGINT REFERENCES sales(id) ON DELETE SET NULL,
    raw_sale_id BIGINT REFERENCES raw_sales(id) ON DELETE SET NULL,
    sale_kind TEXT,
    payment_type TEXT NOT NULL DEFAULT 'versement',
    allocation_meta TEXT,
    amount DOUBLE PRECISION NOT NULL,
    payment_date TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
);

CREATE TABLE IF NOT EXISTS activity_logs (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id BIGINT,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
);

CREATE TABLE IF NOT EXISTS error_logs (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    route TEXT,
    error_type TEXT,
    message TEXT,
    traceback TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
);

CREATE TABLE IF NOT EXISTS system_logs (
    id BIGSERIAL PRIMARY KEY,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
);

CREATE TABLE IF NOT EXISTS performance_logs (
    id BIGSERIAL PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    elapsed_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
    route TEXT,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id BIGSERIAL PRIMARY KEY,
    item_kind TEXT NOT NULL,
    item_id BIGINT NOT NULL,
    direction TEXT NOT NULL,
    quantity DOUBLE PRECISION NOT NULL DEFAULT 0,
    unit TEXT,
    stock_before DOUBLE PRECISION NOT NULL DEFAULT 0,
    stock_after DOUBLE PRECISION NOT NULL DEFAULT 0,
    reason TEXT,
    reference_type TEXT,
    reference_id BIGINT,
    created_by_username TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    actor_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    actor_username TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'web',
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    status TEXT NOT NULL DEFAULT 'success',
    ip_address TEXT,
    user_agent TEXT,
    request_id TEXT,
    before_json TEXT,
    after_json TEXT,
    meta_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
);

CREATE TABLE IF NOT EXISTS backup_jobs (
    id BIGSERIAL PRIMARY KEY,
    reason TEXT NOT NULL,
    backup_type TEXT NOT NULL DEFAULT 'event',
    local_path TEXT NOT NULL,
    requested_by_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    context_json TEXT,
    cloud_file_id TEXT,
    cloud_file_name TEXT,
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS backup_runs (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES backup_jobs(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    cloud_file_id TEXT,
    cloud_file_name TEXT,
    details_json TEXT,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS api_refresh_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    token_hint TEXT,
    created_ip TEXT,
    user_agent TEXT,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    last_used_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
);

CREATE TABLE IF NOT EXISTS imported_client_history (
    id BIGSERIAL PRIMARY KEY,
    client_id BIGINT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    source_file TEXT,
    entry_date TEXT NOT NULL,
    designation TEXT,
    debit_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    credit_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    running_balance DOUBLE PRECISION NOT NULL DEFAULT 0,
    imported_by_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
);

CREATE INDEX IF NOT EXISTS idx_sales_client_id ON sales(client_id);
CREATE INDEX IF NOT EXISTS idx_sales_sale_date ON sales(sale_date);
CREATE INDEX IF NOT EXISTS idx_sales_client_date_id ON sales(client_id, sale_date, id);
CREATE INDEX IF NOT EXISTS idx_sales_date_id ON sales(sale_date, id);
CREATE INDEX IF NOT EXISTS idx_sales_document_id ON sales(document_id, id);
CREATE INDEX IF NOT EXISTS idx_sales_finished_product_id ON sales(finished_product_id);
CREATE INDEX IF NOT EXISTS idx_sales_type_date ON sales(sale_type, sale_date);
CREATE INDEX IF NOT EXISTS idx_raw_sales_client_id ON raw_sales(client_id);
CREATE INDEX IF NOT EXISTS idx_raw_sales_sale_date ON raw_sales(sale_date);
CREATE INDEX IF NOT EXISTS idx_raw_sales_client_date_id ON raw_sales(client_id, sale_date, id);
CREATE INDEX IF NOT EXISTS idx_raw_sales_date_id ON raw_sales(sale_date, id);
CREATE INDEX IF NOT EXISTS idx_raw_sales_document_id ON raw_sales(document_id, id);
CREATE INDEX IF NOT EXISTS idx_raw_sales_material_id ON raw_sales(raw_material_id);
CREATE INDEX IF NOT EXISTS idx_raw_sales_type_date ON raw_sales(sale_type, sale_date);
CREATE INDEX IF NOT EXISTS idx_payments_client_id ON payments(client_id);
CREATE INDEX IF NOT EXISTS idx_payments_client_date_id ON payments(client_id, payment_date, id);
CREATE INDEX IF NOT EXISTS idx_payments_date_id ON payments(payment_date, id);
CREATE INDEX IF NOT EXISTS idx_payments_type_client ON payments(payment_type, client_id);
CREATE INDEX IF NOT EXISTS idx_payments_sale_id ON payments(sale_id);
CREATE INDEX IF NOT EXISTS idx_payments_raw_sale_id ON payments(raw_sale_id);
CREATE INDEX IF NOT EXISTS idx_purchases_raw_material_id ON purchases(raw_material_id);
CREATE INDEX IF NOT EXISTS idx_purchases_supplier_id ON purchases(supplier_id);
CREATE INDEX IF NOT EXISTS idx_purchases_date_id ON purchases(purchase_date, id);
CREATE INDEX IF NOT EXISTS idx_purchases_supplier_date_id ON purchases(supplier_id, purchase_date, id);
CREATE INDEX IF NOT EXISTS idx_purchases_document_id ON purchases(document_id, id);
CREATE INDEX IF NOT EXISTS idx_clients_name ON clients(name);
CREATE INDEX IF NOT EXISTS idx_suppliers_name ON suppliers(name);
CREATE INDEX IF NOT EXISTS idx_raw_materials_name ON raw_materials(name);
CREATE INDEX IF NOT EXISTS idx_raw_materials_stock_alert ON raw_materials(stock_qty, alert_threshold);
CREATE INDEX IF NOT EXISTS idx_finished_products_name ON finished_products(name);
CREATE INDEX IF NOT EXISTS idx_purchase_documents_date_id ON purchase_documents(purchase_date, id);
CREATE INDEX IF NOT EXISTS idx_sale_documents_date_id ON sale_documents(sale_date, id);
CREATE INDEX IF NOT EXISTS idx_prod_batch_product_id ON production_batches(finished_product_id);
CREATE INDEX IF NOT EXISTS idx_prod_batch_date_id ON production_batches(production_date, id);
CREATE INDEX IF NOT EXISTS idx_prod_items_batch_id ON production_batch_items(batch_id);
CREATE INDEX IF NOT EXISTS idx_saved_recipes_product ON saved_recipes(finished_product_id);
CREATE INDEX IF NOT EXISTS idx_saved_recipe_items_recipe ON saved_recipe_items(recipe_id);
CREATE INDEX IF NOT EXISTS idx_activity_logs_action ON activity_logs(action);
CREATE INDEX IF NOT EXISTS idx_activity_logs_username ON activity_logs(username);
CREATE INDEX IF NOT EXISTS idx_activity_logs_created_at ON activity_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_error_logs_created_at ON error_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_system_logs_created_at ON system_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_performance_logs_created_at ON performance_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs(actor_username);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_backup_jobs_status ON backup_jobs(status);
CREATE INDEX IF NOT EXISTS idx_backup_runs_job ON backup_runs(job_id);
CREATE INDEX IF NOT EXISTS idx_api_refresh_tokens_user ON api_refresh_tokens(user_id);
"""


def bootstrap_schema() -> None:
    adapted_schema = _adapt_schema_sql(SCHEMA_SQL)
    conn = connect_database(settings.database_url)
    try:
        conn.executescript(adapted_schema)
        conn.commit()
    finally:
        conn.close()
    init_db()
