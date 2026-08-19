"""
PipeCore control-plane API entrypoint.

    uvicorn app.main:app --reload      # dev
    PIPECORE_DB=postgresql+psycopg2://... uvicorn app.main:app   # prod

Serves the REST API (management + reporting) and the static dashboard.
"""
from __future__ import annotations

import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import SessionLocal, init_db
from .seed import seed
from .core.licensing import require_license
from .api import (auth, customers, ip_groups, pipes, policies, reports,
                  license_api, interfaces_api)

app = FastAPI(
    title="PipeCore — Bandwidth Management Control Plane",
    version="0.1.0",
    description="Open-source, Allot NetXplorer–class bandwidth management for ISPs.",
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# Always-open routers so an operator can recover a node (log in, see status,
# upload a fresh license) even when unlicensed or expired.
for r in (auth.router, license_api.router):
    app.include_router(r, prefix="/api")

# Operational routers — blocked with HTTP 402 when there is no valid license.
_licensed = [Depends(require_license())]
for r in (customers.router, ip_groups.router, pipes.router,
          policies.router, reports.router, interfaces_api.router):
    app.include_router(r, prefix="/api", dependencies=_licensed)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    with SessionLocal() as db:
        seed(db)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "pipecore-control-plane", "version": "0.1.0"}


# --- static dashboard (ui/) ------------------------------------------------
_UI_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "ui"))
if os.path.isdir(_UI_DIR):
    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(os.path.join(_UI_DIR, "console.html"))

    app.mount("/ui", StaticFiles(directory=_UI_DIR, html=True), name="ui")
