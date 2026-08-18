# VectraOne-Flow — Bare-Metal Appliance Plan

**Goal:** ship VectraOne-Flow the way OPNsense ships — a single installer image
that lays the whole system (OS + application) onto a bare server with no
pre-installed operating system, boots to a console menu, and exposes the web GUI
for setup. The customer just writes the image to a USB stick, boots the server,
and installs.

This is a real infrastructure project (OPNsense is an entire FreeBSD-based
distribution). Below is the pragmatic path for a small team, deliberately built
on Debian so it reuses everything you already have.

## Why Debian-based (not FreeBSD like OPNsense)

OPNsense uses FreeBSD; pfSense too. But your data plane (XDP/eBPF, tc/CAKE,
LibreQoS, nDPI) is Linux-native. Building the appliance on **Debian** means the
exact code running on your dev server runs on the appliance — no porting. You
get the "OPNsense experience" (self-installing image, console menu, web setup)
on a Linux base that fits your stack.

## Architecture of the image

```
  Installer ISO / USB image
        │  boots a live environment
        ▼
  Console installer  ──►  partitions disk, installs base Debian +
                          VectraOne-Flow packages, sets up services
        │
        ▼
  Installed appliance
    • minimal Debian (no desktop)
    • systemd services: control-plane API, data-plane node agent,
      PostgreSQL, ClickHouse
    • the 4-NIC model: mgmt + 2×bridge + spare
    • console menu on tty1 (set mgmt IP, show status, factory reset)
    • web GUI on the mgmt IP (dashboard, interfaces, license, docs)
    • license enforcement gates operation
```

## Build toolchain

Two well-trodden options to produce the self-installing image:

1. **`debian-installer` preseed** — a Debian netinst/DVD with a `preseed.cfg`
   that automates partitioning and, in `late_command`, installs your
   VectraOne-Flow `.deb` packages and enables the services. Simplest to start.
2. **`live-build` (Debian Live)** — build a live image that includes a
   `debian-installer` (calamares or d-i) plus your packages baked in. This is
   closest to the OPNsense "live image that can install itself" experience and
   is the recommended target.

Either way you first package the app:

- Build **`.deb` packages**: `vectraone-controlplane`, `vectraone-dataplane`,
  `vectraone-web`. Use `fpm` or `dpkg-deb`; declare dependencies (python3,
  postgresql, clickhouse, iproute2, ethtool, the LibreQoS/nDPI bits).
- Ship **systemd unit files** so services start on boot (you already have the
  control-plane unit in the setup guide; add units for the data-plane agent).

## The 4-interface model on the appliance

The Interfaces GUI (already built) maps directly to the hardware:

| Port | Default role | Purpose |
|------|--------------|---------|
| NIC 1 | `management` | web GUI + SSH, out-of-band |
| NIC 2 | `bridge-wan` | faces the upstream / internet |
| NIC 3 | `bridge-lan` | faces the edge router / subscribers |
| NIC 4 | `spare` | second bridge pair, mirror, or cluster |

The installer detects NICs, the console menu sets the management IP so you can
reach the GUI, and the Interfaces page does the rest (roles, addresses, speed
1G/10G/25G/40G/100G, gateway). `ethtool` fixes port speed; the two bridge NICs
are enslaved to `br0`.

## Console menu (tty1)

A small text menu on the physical console, like appliance firewalls have:

```
  VectraOne-Flow 0.1.0   Host ID: 3f9a1c22b7d0
  1) Set management interface / IP
  2) Show interface & bridge status
  3) Show license status
  4) Restart services
  5) Factory reset
  6) Shell
```

A short Python/dialog script wired to the same APIs.

## Licensing on the appliance

The licensing you already have carries straight over: the console and web both
show the **Host ID**; the customer sends it to you; you mint a license with
`tools/issue_license.py`; they upload it in the web GUI (or drop it via the
console). Expiry fails the node closed until renewed — exactly the subscription
model you want.

## Fail-safety (critical for inline)

Because the appliance sits inline, add before selling into production:

- **Hardware fail-to-wire bypass NIC** so power/software failure shorts the
  bridge pair and traffic keeps flowing.
- **Watchdog** that reverts to bypass if the data plane stops.
- **Config rollback timer** on interface changes (revert if the operator
  doesn't confirm within N seconds) so a bad mgmt-IP change can't strand the box.

## Phased delivery

| Step | Output | Effort |
|------|--------|--------|
| A | `.deb` packages + systemd units for the current app | 3–5 days |
| B | `preseed.cfg` netinst that auto-installs the packages | 3–5 days |
| C | Console setup menu (mgmt IP, status, reset) | 3–5 days |
| D | `live-build` self-installing ISO (the OPNsense-style image) | 1–2 weeks |
| E | Fail-to-wire bypass + watchdog + rollback timer | lab + hardware |

Steps A–C give you an installable appliance a technician can stand up. D makes
it a polished single-image install. E makes it safe for a live ISP core.

## Not in scope of the OS image

The heavy data-plane realism (nDPI native binding, LibreQoS inline bridge) is
tracked in `PHASE2_PLAN.md`; the appliance is the *delivery vehicle* for it, not
a substitute. Build the appliance packaging in parallel with Phase 2.
