"""
PipeCore — tc / CAKE / HTB compiler.

Turns the abstract pipe model (models.py) into concrete Linux `tc` commands
that enforce the packages on a real interface. This is the heart of the data
plane: HTB provides the hierarchical rate/ceil (guarantee + borrowing) and a
CAKE leaf qdisc on every class kills bufferbloat and keeps latency low.

Class-id scheme (HTB minor numbers, hex-friendly decimals):
    1:            root qdisc
    1:1           root class = full link capacity
    1:1x          one class per pipe (x = 0,1,2,... allocated in order)
    1:1x0y        contended-pipe child, one per subscriber

Matching:
    * Subscriber pipes (dedicated / contended) match on IP with a u32 filter.
    * Protocol / application pipes match on the fwmark set upstream by the DPI
      classifier (nDPI -> eBPF/iptables), using an `fw` filter.

The compiler is pure: it returns command strings and never touches the system.
`applier.py` is responsible for actually running them (or dry-running).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import Direction, InterfacePlan, Pipe, PipeType, Subscriber


class CompileError(ValueError):
    """Raised when a plan is internally inconsistent (bad ratio, oversell, ...)."""


ALLOWED_RATIOS = (1, 2, 4, 8, 10, 20)


def _rate(mbps: float) -> str:
    """Render a Mbit/s value for tc. Sub-1 Mbit falls back to kbit precision."""
    if mbps <= 0:
        raise CompileError(f"rate must be > 0, got {mbps}")
    if mbps < 1:
        return f"{int(round(mbps * 1000))}kbit"
    # tc accepts fractional mbit but keep it clean
    if abs(mbps - round(mbps)) < 1e-9:
        return f"{int(round(mbps))}mbit"
    return f"{mbps:.3f}mbit"


def _dir_rate(pipe: Pipe, direction: Direction) -> float:
    return pipe.download_mbps if direction == Direction.DOWNLOAD else pipe.upload_mbps


def _sub_rate(sub: Subscriber, direction: Direction) -> float:
    return sub.download_mbps if direction == Direction.DOWNLOAD else sub.upload_mbps


@dataclass
class CompiledPipe:
    pipe_id: int
    classid: str
    rate_mbps: float
    ceil_mbps: float


@dataclass
class TcProgram:
    """Result of compiling one InterfacePlan."""
    interface: str
    direction: Direction
    commands: list[str] = field(default_factory=list)
    class_map: list[CompiledPipe] = field(default_factory=list)
    # human-readable warnings (e.g. oversubscription beyond link capacity)
    warnings: list[str] = field(default_factory=list)

    def script(self) -> str:
        return "\n".join(self.commands)


class TcCompiler:
    def __init__(self, plan: InterfacePlan, *, cake_leaf: bool = True):
        self.plan = plan
        self.cake_leaf = cake_leaf
        self.dev = plan.interface
        self._minor = 0  # counter for pipe class minor ids

    # ---- public -----------------------------------------------------------
    def compile(self) -> TcProgram:
        p = self.plan
        prog = TcProgram(interface=self.dev, direction=p.direction)

        # default class = last one (1:1fff) catches unclassified -> best effort
        prog.commands.append(f"tc qdisc del dev {self.dev} root  # (ignored if absent)")
        prog.commands.append(
            f"tc qdisc add dev {self.dev} root handle 1: htb default fff"
        )
        prog.commands.append(
            f"tc class add dev {self.dev} parent 1: classid 1:1 "
            f"htb rate {_rate(p.total_mbps)} ceil {_rate(p.total_mbps)}"
        )

        committed = 0.0
        for pipe in p.pipes:
            committed += self._emit_pipe(pipe, prog)

        # default best-effort class for traffic matching no pipe
        prog.commands.append(
            f"tc class add dev {self.dev} parent 1:1 classid 1:fff "
            f"htb rate {_rate(max(p.total_mbps * 0.01, 1))} ceil {_rate(p.total_mbps)} prio 7"
        )
        prog.commands.append(self._leaf(0xFFF))

        if committed > p.total_mbps + 1e-6:
            prog.warnings.append(
                f"Committed guaranteed rate {committed:.1f} Mbps exceeds link "
                f"capacity {p.total_mbps:.1f} Mbps on {self.dev}. HTB guarantees "
                f"cannot all be honoured under saturation."
            )
        return prog

    # ---- per-pipe emitters ------------------------------------------------
    def _emit_pipe(self, pipe: Pipe, prog: TcProgram) -> float:
        """Return the guaranteed (committed) rate this pipe reserves."""
        if pipe.ptype == PipeType.DEDICATED:
            return self._emit_dedicated(pipe, prog)
        if pipe.ptype == PipeType.CONTENDED:
            return self._emit_contended(pipe, prog)
        if pipe.ptype == PipeType.PROTOCOL or pipe.ptype == PipeType.APPLICATION:
            return self._emit_marked(pipe, prog)
        if pipe.ptype == PipeType.TIME_BASED:
            return self._emit_time_based(pipe, prog)
        raise CompileError(f"unknown pipe type {pipe.ptype}")

    def _next_classid(self) -> tuple[str, int]:
        self._minor += 1
        minor = 0x100 + self._minor  # 0x101, 0x102, ...
        return f"1:{minor:x}", minor

    def _leaf(self, parent_minor: int) -> str:
        """CAKE (preferred) or fq_codel leaf qdisc on a class."""
        handle = f"{parent_minor:x}0"
        if self.cake_leaf:
            return (
                f"tc qdisc add dev {self.dev} parent 1:{parent_minor:x} "
                f"handle {handle}: cake"
            )
        return (
            f"tc qdisc add dev {self.dev} parent 1:{parent_minor:x} "
            f"handle {handle}: fq_codel"
        )

    def _ip_filter(self, sub: Subscriber, classid: str) -> str:
        # download shapes toward subscriber => match dst ip; upload => src ip
        field = "dst" if self.plan.direction == Direction.DOWNLOAD else "src"
        return (
            f"tc filter add dev {self.dev} protocol ip parent 1: prio 1 u32 "
            f"match ip {field} {sub.cidr} flowid {classid}"
        )

    def _fw_filter(self, fwmark: int, classid: str, prio: int = 2) -> str:
        return (
            f"tc filter add dev {self.dev} protocol ip parent 1: prio {prio} "
            f"handle {fwmark} fw flowid {classid}"
        )

    def _emit_dedicated(self, pipe: Pipe, prog: TcProgram) -> float:
        rate = _dir_rate(pipe, self.plan.direction)
        if rate <= 0:
            raise CompileError(f"dedicated pipe '{pipe.name}' needs a rate")
        classid, minor = self._next_classid()
        # 100% guarantee: rate == ceil (no borrowing above, guaranteed below)
        prog.commands.append(
            f"tc class add dev {self.dev} parent 1:1 classid {classid} "
            f"htb rate {_rate(rate)} ceil {_rate(rate)} prio {pipe.priority}"
        )
        prog.commands.append(self._leaf(minor))
        for sub in pipe.subscribers:
            prog.commands.append(self._ip_filter(sub, classid))
        prog.class_map.append(CompiledPipe(pipe.id, classid, rate, rate))
        return rate

    def _emit_contended(self, pipe: Pipe, prog: TcProgram) -> float:
        ratio = pipe.contention_ratio
        if ratio not in ALLOWED_RATIOS:
            raise CompileError(
                f"contention ratio 1:{ratio} not allowed; use one of "
                f"{', '.join('1:%d' % r for r in ALLOWED_RATIOS)}"
            )
        if not pipe.subscribers:
            raise CompileError(f"contended pipe '{pipe.name}' has no subscribers")

        # Aggregate of sold plan rates, then divide by the contention ratio to
        # get the guaranteed aggregate we actually provision.
        sold = sum(_sub_rate(s, self.plan.direction) for s in pipe.subscribers)
        provisioned = sold / ratio

        parent_id, parent_minor = self._next_classid()
        # parent guarantees `provisioned`, may burst to the full sold aggregate
        prog.commands.append(
            f"tc class add dev {self.dev} parent 1:1 classid {parent_id} "
            f"htb rate {_rate(provisioned)} ceil {_rate(sold)} prio {pipe.priority}"
        )
        prog.class_map.append(CompiledPipe(pipe.id, parent_id, provisioned, sold))

        # one child per subscriber: small guarantee, ceil = their plan rate,
        # borrowing from the shared parent up to the plan.
        for idx, sub in enumerate(pipe.subscribers, start=1):
            plan_rate = _sub_rate(sub, self.plan.direction)
            child_minor = parent_minor * 0x10 + idx  # nested, unique
            child_id = f"1:{child_minor:x}"
            guaranteed = max(plan_rate / ratio, 0.05)
            prog.commands.append(
                f"tc class add dev {self.dev} parent {parent_id} classid {child_id} "
                f"htb rate {_rate(guaranteed)} ceil {_rate(plan_rate)} prio {pipe.priority}"
            )
            prog.commands.append(self._leaf(child_minor))
            prog.commands.append(self._ip_filter(sub, child_id))
        return provisioned

    def _emit_marked(self, pipe: Pipe, prog: TcProgram) -> float:
        """Protocol- or application-based shaping via DPI fwmark."""
        if pipe.fwmark is None:
            raise CompileError(
                f"{pipe.ptype.value} pipe '{pipe.name}' needs an fwmark "
                f"(assigned by the DPI classifier)"
            )
        ceil = _dir_rate(pipe, self.plan.direction)
        if ceil <= 0:
            raise CompileError(f"pipe '{pipe.name}' needs a rate limit")
        classid, minor = self._next_classid()
        guaranteed = max(ceil * 0.05, 0.05)  # low floor; this is a limiter
        prog.commands.append(
            f"tc class add dev {self.dev} parent 1:1 classid {classid} "
            f"htb rate {_rate(guaranteed)} ceil {_rate(ceil)} prio {pipe.priority}  "
            f"# match={pipe.match_label}"
        )
        prog.commands.append(self._leaf(minor))
        prog.commands.append(self._fw_filter(pipe.fwmark, classid))
        prog.class_map.append(CompiledPipe(pipe.id, classid, guaranteed, ceil))
        return guaranteed

    def _emit_time_based(self, pipe: Pipe, prog: TcProgram) -> float:
        """
        Time-based pipes are compiled per active window by the scheduler.
        At compile time we emit the CURRENT effective rate as a dedicated-style
        class; `scheduler.py` recompiles and re-applies at each window boundary.
        The default (window-less) rate is used here.
        """
        rate = _dir_rate(pipe, self.plan.direction)
        if rate <= 0 and pipe.windows:
            rate = max(w.download_mbps if self.plan.direction == Direction.DOWNLOAD
                       else w.upload_mbps for w in pipe.windows)
        classid, minor = self._next_classid()
        prog.commands.append(
            f"tc class add dev {self.dev} parent 1:1 classid {classid} "
            f"htb rate {_rate(max(rate*0.5, 0.05))} ceil {_rate(rate)} "
            f"prio {pipe.priority}  # time-based; scheduler swaps windows"
        )
        prog.commands.append(self._leaf(minor))
        for sub in pipe.subscribers:
            prog.commands.append(self._ip_filter(sub, classid))
        prog.class_map.append(CompiledPipe(pipe.id, classid, max(rate*0.5, 0.05), rate))
        return max(rate * 0.5, 0.05)


def compile_plan(plan: InterfacePlan, *, cake_leaf: bool = True) -> TcProgram:
    """Convenience wrapper."""
    return TcCompiler(plan, cake_leaf=cake_leaf).compile()
