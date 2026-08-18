#!/usr/bin/env python3
"""
VENDOR TOOL — issue (mint) a license for a customer. You run this when a
customer buys or renews. It signs a license with your private key.

Examples:
    # 10G tier, DPI included, 1 year, bound to the customer's Host ID:
    python3 tools/issue_license.py \
        --licensee "Acme ISP" --tier 10G --dpi --host 3f9a1c22b7d0 \
        --out acme-10g.key

    # 1G tier, no DPI, site license (any host), custom term:
    python3 tools/issue_license.py --licensee "Beta Net" --tier 1G \
        --host ANY --days 365 --out beta-1g.key

The customer uploads the resulting .key file in the VectraOne-Flow GUI
(Licensing page) or drops it at control-plane/license.key.

Get the customer's Host ID from their Licensing page, or have them run:
    python3 -c "from app.core.licensing import get_host_id; print(get_host_id())"
"""
import argparse
import base64
import datetime as dt
import json
import os
import secrets

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

TIERS = {"1G": 1000, "2.5G": 2500, "10G": 10000, "25G": 25000, "40G": 40000, "100G": 100000}
SUPPORT_STANDARD = "Standard 24/7/365, 6-hour response"
PRIV_PATH = os.getenv(
    "PIPECORE_VENDOR_PRIVKEY",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vendor", "vendor_private.key"),
)


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def main() -> None:
    ap = argparse.ArgumentParser(description="Issue a VectraOne-Flow license")
    ap.add_argument("--licensee", required=True, help="customer name")
    ap.add_argument("--tier", required=True, choices=list(TIERS), help="bandwidth tier")
    ap.add_argument("--host", default="ANY", help="customer Host ID, or ANY for a site license")
    ap.add_argument("--dpi", action="store_true", help="include the Deep Packet Inspection add-on")
    ap.add_argument("--days", type=int, default=365, help="license term in days (default 365)")
    ap.add_argument("--support", default=SUPPORT_STANDARD)
    ap.add_argument("--out", default="-", help="output file (default: stdout)")
    args = ap.parse_args()

    if not os.path.exists(PRIV_PATH):
        raise SystemExit(f"Vendor private key not found at {PRIV_PATH}. Run tools/vendor_keygen.py first.")
    with open(PRIV_PATH) as fh:
        priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(fh.read().strip()))

    today = dt.date.today()
    payload = {
        "v": 1,
        "serial": secrets.token_hex(6).upper(),
        "licensee": args.licensee,
        "host_id": args.host,
        "tier": args.tier,
        "max_mbps": TIERS[args.tier],
        "dpi": bool(args.dpi),
        "support": args.support,
        "model": f"VectraOne-Flow VF-{args.tier}",
        "issued": today.isoformat(),
        "expires": (today + dt.timedelta(days=args.days)).isoformat(),
    }
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    sig = priv.sign(payload_bytes)
    license_str = f"{_b64url(payload_bytes)}.{_b64url(sig)}"

    if args.out == "-":
        print(license_str)
    else:
        with open(args.out, "w") as fh:
            fh.write(license_str + "\n")
        print(f"Issued {args.tier} license for '{args.licensee}' "
              f"(DPI={'yes' if args.dpi else 'no'}, host={args.host}, "
              f"expires {payload['expires']}, serial {payload['serial']}) -> {args.out}")


if __name__ == "__main__":
    main()
