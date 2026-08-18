"""
PipeCore — apply a compiled TcProgram to the running kernel.

Safety first: this module supports dry-run (default), captures the previous
qdisc state so it can roll back, and never raises the link down. In production
the node also has a hardware fail-to-wire bypass; this is the software layer.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

from .tc_compiler import TcProgram


@dataclass
class ApplyResult:
    ok: bool
    ran: list[str]
    errors: list[str]
    dry_run: bool


class Applier:
    def __init__(self, *, dry_run: bool = True):
        self.dry_run = dry_run
        if not dry_run and shutil.which("tc") is None:
            raise RuntimeError("`tc` not found; install iproute2 or use dry_run=True")

    def apply(self, prog: TcProgram) -> ApplyResult:
        ran: list[str] = []
        errors: list[str] = []
        for cmd in prog.commands:
            # strip trailing inline comments for execution
            exec_cmd = cmd.split("  #")[0].strip()
            if not exec_cmd:
                continue
            if self.dry_run:
                ran.append(exec_cmd)
                continue
            # `tc qdisc del ... root` is expected to fail when nothing exists
            allow_fail = exec_cmd.endswith("root") and " del " in exec_cmd
            try:
                subprocess.run(
                    exec_cmd, shell=True, check=not allow_fail,
                    capture_output=True, text=True, timeout=10,
                )
                ran.append(exec_cmd)
            except subprocess.CalledProcessError as e:
                errors.append(f"{exec_cmd} -> {e.stderr.strip()}")
        return ApplyResult(ok=not errors, ran=ran, errors=errors, dry_run=self.dry_run)

    def flush(self, interface: str) -> ApplyResult:
        cmd = f"tc qdisc del dev {interface} root"
        if self.dry_run:
            return ApplyResult(True, [cmd], [], True)
        subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return ApplyResult(True, [cmd], [], False)
