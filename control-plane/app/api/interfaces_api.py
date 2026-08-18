"""
Network interface configuration API.

Reads the node's real NICs and lets an operator assign roles (bridge LAN /
bridge WAN / management / spare), addressing (static or DHCP), a gateway, and a
port speed (1G/10G/25G/40G/100G). The desired config is persisted as JSON and
compiled into the exact `ip` / `ethtool` / bridge commands that realise it.

Applying to the live kernel is gated (dry-run by default) because changing the
management interface can cut you off — the appliance build wires the real apply
with a safe rollback timer.
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .auth import require

router = APIRouter(prefix="/interfaces", tags=["interfaces"])

_CFG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "interfaces.json"
)
PORT_SPEEDS = ["1G", "10G", "25G", "40G", "100G"]
ROLES = ["management", "bridge-lan", "bridge-wan", "spare", "cluster", "mirror"]


class IfConfig(BaseModel):
    name: str
    role: str = "spare"
    dhcp4: bool = False
    addresses: list[str] = []       # ["192.168.0.161/24", ...]
    speed: Optional[str] = None     # one of PORT_SPEEDS
    comment: str = ""


class InterfacesApply(BaseModel):
    interfaces: list[IfConfig]
    gateway4: str = ""
    gateway6: str = ""
    bridge_name: str = "br0"
    apply: bool = False             # if false: return the commands without running


def _sh(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001
        return ""


def _detected() -> list[dict]:
    """Live view of the node's interfaces from the kernel."""
    out = []
    net_dir = "/sys/class/net"
    if not os.path.isdir(net_dir):
        return out
    # addresses via `ip -j addr` (JSON) when available
    addr_by_if: dict[str, list[str]] = {}
    try:
        data = json.loads(_sh(["ip", "-j", "addr", "show"]) or "[]")
        for e in data:
            addr_by_if[e.get("ifname", "")] = [
                f"{a['local']}/{a['prefixlen']}" for a in e.get("addr_info", [])
                if a.get("family") in ("inet", "inet6")
            ]
    except Exception:  # noqa: BLE001
        pass
    for name in sorted(os.listdir(net_dir)):
        if name == "lo":
            continue
        def rd(p, d=""):
            try:
                return open(os.path.join(net_dir, name, p)).read().strip()
            except OSError:
                return d
        speed_mbps = rd("speed")
        out.append({
            "name": name,
            "mac": rd("address"),
            "state": rd("operstate", "unknown"),
            "speed_mbps": int(speed_mbps) if speed_mbps.lstrip("-").isdigit() else None,
            "addresses": addr_by_if.get(name, []),
            "is_bridge": os.path.isdir(os.path.join(net_dir, name, "bridge")),
        })
    return out


def _load_cfg() -> dict:
    if os.path.exists(_CFG_PATH):
        with open(_CFG_PATH) as fh:
            return json.load(fh)
    return {}


def _compile(cfg: InterfacesApply) -> list[str]:
    """Turn desired interface config into concrete ip/ethtool/bridge commands."""
    cmds: list[str] = []
    speed_map = {"1G": 1000, "10G": 10000, "25G": 25000, "40G": 40000, "100G": 100000}
    bridge_members = [i for i in cfg.interfaces if i.role in ("bridge-lan", "bridge-wan")]
    if bridge_members:
        cmds.append(f"ip link add name {cfg.bridge_name} type bridge")
        cmds.append(f"ip link set {cfg.bridge_name} up")
    for i in cfg.interfaces:
        if i.speed in speed_map:
            # fixed speed, autoneg off (typical for fibre/DAC on carrier links)
            cmds.append(f"ethtool -s {i.name} speed {speed_map[i.speed]} autoneg off")
        cmds.append(f"ip addr flush dev {i.name}")
        if i.role in ("bridge-lan", "bridge-wan"):
            cmds.append(f"ip link set {i.name} master {cfg.bridge_name}")
            cmds.append(f"ip link set {i.name} up")
        else:
            if i.dhcp4:
                cmds.append(f"# {i.name}: DHCPv4 (dhclient {i.name})")
            for a in i.addresses:
                if a.strip():
                    cmds.append(f"ip addr add {a.strip()} dev {i.name}")
            cmds.append(f"ip link set {i.name} up")
    if cfg.gateway4:
        cmds.append(f"ip route replace default via {cfg.gateway4}")
    if cfg.gateway6:
        cmds.append(f"ip -6 route replace default via {cfg.gateway6}")
    return cmds


@router.get("")
def list_interfaces():
    return {
        "detected": _detected(),
        "config": _load_cfg(),
        "port_speeds": PORT_SPEEDS,
        "roles": ROLES,
    }


@router.post("/apply")
def apply_interfaces(cfg: InterfacesApply, _=Depends(require("admin"))):
    cmds = _compile(cfg)
    with open(_CFG_PATH, "w") as fh:
        json.dump(cfg.model_dump(), fh, indent=2)
    applied = False
    # real apply is intentionally not performed here (see module docstring).
    return {"saved": True, "applied": applied, "commands": cmds}
