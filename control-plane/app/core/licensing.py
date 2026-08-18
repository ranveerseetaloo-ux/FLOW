"""
VectraOne-Flow licensing.

A license is a signed token the vendor issues to a customer. It is bound to the
server's Host ID, carries a bandwidth tier and feature flags (e.g. DPI), and
expires after its term. The product ships ONLY the vendor's PUBLIC key, so
customers cannot forge or extend a license — only the vendor, holding the
matching private key, can mint one.

License string format:
    base64url(payload_json) + "." + base64url(ed25519_signature)

Enforcement: `require_license()` is a FastAPI dependency put on the operational
routers. If there is no valid, unexpired license, those endpoints return HTTP
402 and the system effectively stops operating until a new license is uploaded.
The license-status/upload, auth and health endpoints stay open so the operator
can always recover by uploading a fresh key.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import uuid
from dataclasses import dataclass, asdict
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# ---------------------------------------------------------------------------
# Vendor public key (hex, Ed25519 raw). REPLACE the demo value with your own
# public key from tools/vendor_keygen.py before selling. The matching PRIVATE
# key must NEVER ship inside the product.
# ---------------------------------------------------------------------------
VENDOR_PUBLIC_KEY_HEX = os.getenv(
    "PIPECORE_VENDOR_PUBKEY",
    "2d5d1c58759dd647e91fdb3ed83870882f4edbf25423d97dec5810af103f523a",  # DEMO KEY
)

# Bandwidth tiers the vendor sells (label -> Mbps ceiling for the whole node).
TIERS: dict[str, int] = {
    "1G": 1000,
    "2.5G": 2500,
    "10G": 10000,
    "25G": 25000,
    "40G": 40000,
    "100G": 100000,
}

SUPPORT_STANDARD = "Standard 24/7/365, 6-hour response"

# where the active license file lives on the node
_LICENSE_PATH = os.getenv(
    "PIPECORE_LICENSE_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "license.key"),
)
# allow turning enforcement off for development only
_ENFORCE = os.getenv("PIPECORE_ENFORCE_LICENSE", "true").lower() == "true"


# ---------------------------------------------------------------------------
# Host identity
# ---------------------------------------------------------------------------
def get_host_id() -> str:
    """Stable per-machine ID: 12 hex chars derived from the machine-id / MAC."""
    seed = ""
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(path) as fh:
                seed = fh.read().strip()
                if seed:
                    break
        except OSError:
            continue
    if not seed:
        seed = f"{uuid.getnode():012x}"  # MAC fallback
    return hashlib.sha256(seed.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# License model + verification
# ---------------------------------------------------------------------------
@dataclass
class LicenseStatus:
    licensed: bool
    reason: str = ""                 # why invalid, if not licensed
    host_id: str = ""
    licensee: str = ""
    model: str = ""
    tier: str = ""
    max_mbps: int = 0
    dpi: bool = False
    support: str = ""
    issued: str = ""
    expires: str = ""
    days_left: int = 0
    serial: str = ""

    def public_dict(self) -> dict:
        return asdict(self)


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _verify_signature(payload_bytes: bytes, sig: bytes) -> bool:
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(VENDOR_PUBLIC_KEY_HEX))
        pub.verify(sig, payload_bytes)
        return True
    except (InvalidSignature, ValueError):
        return False


def verify_license(license_str: str, *, host_id: Optional[str] = None) -> LicenseStatus:
    host = host_id or get_host_id()
    try:
        payload_b64, sig_b64 = license_str.strip().split(".", 1)
    except ValueError:
        return LicenseStatus(False, "malformed license", host_id=host)

    payload_bytes = _b64url_decode(payload_b64)
    if not _verify_signature(payload_bytes, _b64url_decode(sig_b64)):
        return LicenseStatus(False, "signature invalid (not issued by this vendor)", host_id=host)

    try:
        p = json.loads(payload_bytes)
    except json.JSONDecodeError:
        return LicenseStatus(False, "corrupt payload", host_id=host)

    # host binding ("ANY" allows install on any host, for demos/site licenses)
    lic_host = p.get("host_id", "ANY")
    if lic_host != "ANY" and lic_host != host:
        return LicenseStatus(False, f"license is bound to host {lic_host}, not {host}", host_id=host)

    # expiry
    try:
        expires = dt.date.fromisoformat(p["expires"])
    except (KeyError, ValueError):
        return LicenseStatus(False, "missing/invalid expiry", host_id=host)
    today = dt.datetime.now(dt.timezone.utc).date()
    days_left = (expires - today).days
    tier = p.get("tier", "")
    st = LicenseStatus(
        licensed=days_left >= 0,
        reason="" if days_left >= 0 else "license expired",
        host_id=host,
        licensee=p.get("licensee", ""),
        model=p.get("model", f"VectraOne-Flow VF-{tier}"),
        tier=tier,
        max_mbps=int(p.get("max_mbps", TIERS.get(tier, 0))),
        dpi=bool(p.get("dpi", False)),
        support=p.get("support", SUPPORT_STANDARD),
        issued=p.get("issued", ""),
        expires=p.get("expires", ""),
        days_left=days_left,
        serial=p.get("serial", ""),
    )
    return st


# ---------------------------------------------------------------------------
# Active license (loaded from disk, cached)
# ---------------------------------------------------------------------------
_cache: Optional[LicenseStatus] = None


def load_active_license(force: bool = False) -> LicenseStatus:
    global _cache
    if _cache is not None and not force:
        return _cache
    if not os.path.exists(_LICENSE_PATH):
        _cache = LicenseStatus(False, "no license installed", host_id=get_host_id())
        return _cache
    with open(_LICENSE_PATH) as fh:
        _cache = verify_license(fh.read())
    return _cache


def install_license(license_str: str) -> LicenseStatus:
    """Validate then persist a license. Returns the resulting status."""
    st = verify_license(license_str)
    if not st.licensed:
        return st                     # do not persist an invalid license
    with open(_LICENSE_PATH, "w") as fh:
        fh.write(license_str.strip())
    global _cache
    _cache = st
    return st


# ---------------------------------------------------------------------------
# FastAPI enforcement dependency
# ---------------------------------------------------------------------------
def require_license(feature: Optional[str] = None):
    """
    Dependency factory. Put `Depends(require_license())` on operational routes;
    use `Depends(require_license("dpi"))` on DPI-gated routes.
    """
    def _dep():
        if not _ENFORCE:
            return
        from fastapi import HTTPException
        st = load_active_license()
        if not st.licensed:
            raise HTTPException(status_code=402,
                                detail=f"License required: {st.reason}. Upload a valid license to continue.")
        if feature == "dpi" and not st.dpi:
            raise HTTPException(status_code=403,
                                detail="Deep Packet Inspection is not included in this license.")
    return _dep
