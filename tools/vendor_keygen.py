#!/usr/bin/env python3
"""
VENDOR TOOL — generate your signing keypair. Run this ONCE.

    python3 tools/vendor_keygen.py

Outputs:
  vendor/vendor_private.key   <-- KEEP SECRET. Never ships in the product.
                                  Used by issue_license.py to mint licenses.
  Prints the PUBLIC key hex   <-- paste into VENDOR_PUBLIC_KEY_HEX in
                                  control-plane/app/core/licensing.py

Anyone with the private key can issue licenses, so guard it like a signing key
(offline machine, password manager, or an HSM for production).
"""
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vendor")
PRIV_PATH = os.path.join(OUT_DIR, "vendor_private.key")


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(PRIV_PATH):
        raise SystemExit(f"Refusing to overwrite existing key: {PRIV_PATH}")
    priv = Ed25519PrivateKey.generate()
    priv_raw = priv.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    pub_raw = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    with open(PRIV_PATH, "w") as fh:
        fh.write(priv_raw.hex())
    os.chmod(PRIV_PATH, 0o600)
    print(f"Private key written to {PRIV_PATH} (mode 600 — keep it secret).")
    print()
    print("Paste this into control-plane/app/core/licensing.py -> VENDOR_PUBLIC_KEY_HEX:")
    print(f'    "{pub_raw.hex()}"')


if __name__ == "__main__":
    main()
