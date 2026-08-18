# Vendor keys & license issuing

This folder holds the **vendor signing key** used to mint customer licenses.
Treat the private key like a master password.

## Files

- `DEMO_vendor_private.key` — a throwaway key that matches the DEMO public key
  currently embedded in `control-plane/app/core/licensing.py`. It exists so the
  system runs out of the box. **Do not use it in production** — anyone with this
  repo could forge licenses.
- `vendor_private.key` — your real key, created by `tools/vendor_keygen.py`.
  Git-ignored on purpose. Keep it offline / in a password manager.

## Go-to-production steps

1. Generate your real keypair:
   ```
   python3 tools/vendor_keygen.py
   ```
2. Paste the printed public key into `VENDOR_PUBLIC_KEY_HEX` in
   `control-plane/app/core/licensing.py` (or set the `PIPECORE_VENDOR_PUBKEY`
   env var). This makes the product trust only your key.
3. Re-issue any real licenses with your key:
   ```
   python3 tools/issue_license.py --licensee "Customer" --tier 10G --dpi \
       --host <customer-host-id> --out customer.key
   ```
4. The customer uploads `customer.key` on the Licensing page.

## How a sale works

1. Customer installs VectraOne-Flow and reads their **Host ID** from the
   Licensing page (or the console).
2. They send you the Host ID + the tier they bought (and whether DPI is
   included).
3. You run `issue_license.py` and send back the `.key` file.
4. They upload it. It expires in a year; renewal = issue a new key.
