import os

import uvicorn

from app.core.database import bootstrap_and_migrate
from app.core.logging import log_server_start
from app.core.runtime_paths import ensure_runtime_dirs
from app.main import app

init_db = bootstrap_and_migrate

__all__ = ["app", "ensure_runtime_dirs", "init_db", "log_server_start"]

if __name__ == "__main__":
    host = os.environ.get("FAB_HOST", "0.0.0.0")
    port = int(os.environ.get("FAB_PORT", "5000"))
    log_server_start()
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
