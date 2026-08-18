#!/usr/bin/env python3
"""
Zero-dependency end-to-end demo of the PipeCore data plane.

Defines a realistic small-ISP mix of pipes, compiles them to tc/CAKE commands,
prints the script, and dry-run "applies" it. Runs with nothing but the stdlib.

    python3 data-plane/demo/compile_demo.py
"""
import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from shaper.models import (
    Direction, InterfacePlan, Pipe, PipeType, Subscriber, TimeWindow,
)
from shaper.tc_compiler import compile_plan
from shaper.applier import Applier


def build_demo() -> InterfacePlan:
    homes = [Subscriber(f"home{i}", f"203.0.113.{i}/32", 100, 20) for i in range(1, 5)]
    return InterfacePlan(
        interface="eth0", direction=Direction.DOWNLOAD, total_mbps=1000,
        pipes=[
            Pipe(1, "DIA-AcmeBank", PipeType.DEDICATED, 200, 200, priority=1,
                 subscribers=[Subscriber("acme", "203.0.113.50/32", 200, 200)]),
            Pipe(2, "Residential-1to4", PipeType.CONTENDED, contention_ratio=4,
                 subscribers=homes, priority=3),
            Pipe(3, "Throttle-BitTorrent", PipeType.APPLICATION, download_mbps=50,
                 match_label="bittorrent", fwmark=0x10, priority=5),
            Pipe(4, "NightBoost", PipeType.TIME_BASED, priority=3,
                 subscribers=[Subscriber("nb", "203.0.113.80/32", 0, 0)],
                 windows=[
                     TimeWindow("peak", [0,1,2,3,4,5,6], "18:00", "23:00", 50, 25),
                     TimeWindow("offpeak", [0,1,2,3,4,5,6], "23:00", "18:00", 200, 100),
                 ]),
        ],
    )


def main() -> None:
    plan = build_demo()
    prog = compile_plan(plan)

    print("=" * 70)
    print(f" Compiled shaping for {plan.interface} ({plan.direction.value}), "
          f"link {plan.total_mbps:.0f} Mbps")
    print("=" * 70)
    print(prog.script())
    print()
    print("Class map (pipe -> HTB classid, guaranteed/ceil Mbps):")
    for cp in prog.class_map:
        print(f"  pipe {cp.pipe_id:>2}  {cp.classid:<8}  "
              f"rate={cp.rate_mbps:g}  ceil={cp.ceil_mbps:g}")
    if prog.warnings:
        print("\nWARNINGS:")
        for w in prog.warnings:
            print("  ! " + w)

    print("\nDry-run apply:")
    res = Applier(dry_run=True).apply(prog)
    print(f"  {len(res.ran)} commands would run, errors={len(res.errors)}, "
          f"dry_run={res.dry_run}")


if __name__ == "__main__":
    main()
