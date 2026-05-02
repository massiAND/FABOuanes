import os

import uvicorn

from app.core.logging import log_server_start
from app.main import app

if __name__ == '__main__':
    host = os.environ.get('FAB_HOST') or os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('FAB_PORT') or os.environ.get('PORT', '5000'))
    log_server_start()
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
