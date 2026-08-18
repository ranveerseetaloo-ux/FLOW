"""License status, Host ID, and upload endpoints (always open, so an operator
can always recover a node by uploading a fresh key)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core import licensing
from .auth import require

router = APIRouter(prefix="/license", tags=["license"])


class LicenseUpload(BaseModel):
    license: str


@router.get("")
def status():
    """Current license status — drives the Licensing GUI page."""
    st = licensing.load_active_license()
    d = st.public_dict()
    d["tiers"] = licensing.TIERS
    d["enforced"] = licensing._ENFORCE
    return d


@router.get("/host-id")
def host_id():
    """The Host ID a customer gives the vendor to bind their license."""
    return {"host_id": licensing.get_host_id()}


@router.post("/upload")
def upload(body: LicenseUpload, _=Depends(require("admin"))):
    st = licensing.install_license(body.license)
    if not st.licensed:
        raise HTTPException(status_code=400, detail=f"License rejected: {st.reason}")
    return st.public_dict()
