"""
System & diagnostics endpoints — power the System, Diagnostics and Tools pages.

Read-only system info plus a small, safe command runner for network tools
(ping / traceroute / DNS lookup / iperf). All commands are whitelisted, take a
validated target, and run with a timeout and no shell — so there is no command
injection surface. These require a logged-in operator but not a license, so the
box can always be diagnosed and recovered.
"""
from __future__ import annotations

import platform
import re
import shutil
import socket
import subprocess
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .auth import current_user

router = APIRouter(tags=["system"])

_TARGET_RE = re.compile(r"^[A-Za-z0-9._:-]{1,253}$")   # hostname or IP, no shell metachars


def _run(cmd: list[str], timeout: int = 20) -> str:
    if not shutil.which(cmd[0]):
        return f"[{cmd[0]} not installed on this node]"
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (p.stdout + p.stderr).strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"[timed out after {timeout}s]"
    except Exception as e:  # noqa: BLE001
        return f"[error: {e}]"


# ---------------- System info ----------------
@router.get("/system/info")
def system_info(_=Depends(current_user)):
    def rd(path):
        try:
            return open(path).read().strip()
        except OSError:
            return ""
    load = ""
    try:
        load = " ".join(f"{x:.2f}" for x in __import__("os").getloadavg())
    except Exception:  # noqa: BLE001
        pass
    mem = {}
    for line in rd("/proc/meminfo").splitlines()[:3]:
        k, _, v = line.partition(":")
        mem[k.strip()] = v.strip()
    from ..core.licensing import get_host_id
    return {
        "hostname": socket.gethostname(),
        "host_id": get_host_id(),
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "uptime": _run(["uptime", "-p"]),
        "loadavg": load,
        "memory": mem,
        "disk": _run(["df", "-h", "/"]),
        "now": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
    }


@router.get("/system/routes")
def routes(_=Depends(current_user)):
    return {"routes": _run(["ip", "route", "show"])}


@router.get("/system/dns")
def dns(_=Depends(current_user)):
    try:
        resolv = open("/etc/resolv.conf").read()
    except OSError:
        resolv = "(unavailable)"
    return {"resolv_conf": resolv, "hostname": socket.gethostname()}


@router.get("/system/datetime")
def datetime_info(_=Depends(current_user)):
    return {
        "now": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "timezone": time.strftime("%Z"),
        "timesync": _run(["timedatectl", "status"]),
    }


@router.get("/system/logs")
def logs(lines: int = 200, _=Depends(current_user)):
    lines = max(10, min(lines, 2000))
    out = _run(["journalctl", "-n", str(lines), "--no-pager"], timeout=15)
    if out.startswith("[journalctl not installed"):
        out = _run(["tail", "-n", str(lines), "/var/log/syslog"], timeout=10)
    return {"lines": lines, "log": out}


# ---------------- Network tools ----------------
class ToolReq(BaseModel):
    tool: str
    target: str = ""


@router.post("/tools/run")
def tools_run(body: ToolReq, _=Depends(current_user)):
    tool = body.tool.lower().strip()
    target = body.target.strip()
    needs_target = tool in ("ping", "traceroute", "dnslookup", "iperf")
    if needs_target and not _TARGET_RE.match(target):
        raise HTTPException(400, "invalid target (hostname or IP only)")
    cmds = {
        "ping": ["ping", "-c", "4", "-w", "8", target],
        "traceroute": ["traceroute", "-m", "15", "-w", "2", target],
        "dnslookup": ["getent", "hosts", target],
        "iperf": ["iperf3", "-c", target, "-t", "5"],
        "iperf_server": ["iperf3", "-s", "-1", "-D"],
    }
    if tool not in cmds:
        raise HTTPException(400, f"unknown tool '{tool}'")
    return {"tool": tool, "target": target, "output": _run(cmds[tool], timeout=25)}
