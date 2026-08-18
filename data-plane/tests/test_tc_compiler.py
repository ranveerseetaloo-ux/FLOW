"""Unit tests for the tc/CAKE compiler — the core of the data plane."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shaper.models import (  # noqa: E402
    Direction, InterfacePlan, Pipe, PipeType, Subscriber, TimeWindow,
)
from shaper.tc_compiler import compile_plan, CompileError  # noqa: E402


def _plan(pipes, total=1000, direction=Direction.DOWNLOAD):
    return InterfacePlan(interface="eth0", direction=direction,
                         total_mbps=total, pipes=pipes)


def test_root_qdisc_and_class():
    prog = compile_plan(_plan([]))
    s = prog.script()
    assert "tc qdisc add dev eth0 root handle 1: htb default fff" in s
    assert "classid 1:1 htb rate 1000mbit ceil 1000mbit" in s
    # default best-effort class always present
    assert "classid 1:fff" in s


def test_dedicated_rate_equals_ceil():
    pipe = Pipe(id=1, name="DIA-AcmeCorp", ptype=PipeType.DEDICATED,
                download_mbps=200, upload_mbps=200,
                subscribers=[Subscriber("acme", "203.0.113.10/32", 200, 200)])
    prog = compile_plan(_plan([pipe]))
    s = prog.script()
    # 100% guarantee -> rate == ceil
    assert "rate 200mbit ceil 200mbit" in s
    # matches the subscriber IP on dst (download direction)
    assert "match ip dst 203.0.113.10/32" in s
    # cake leaf present
    assert "cake" in s
    cp = prog.class_map[0]
    assert cp.rate_mbps == cp.ceil_mbps == 200


def test_contended_oversubscription_math():
    subs = [Subscriber(f"c{i}", f"203.0.113.{i}/32", 100, 100) for i in range(1, 5)]
    pipe = Pipe(id=2, name="Home-1to4", ptype=PipeType.CONTENDED,
                contention_ratio=4, subscribers=subs)
    prog = compile_plan(_plan([pipe]))
    parent = prog.class_map[0]
    # 4 subs x 100 Mbps sold, 1:4 => 100 Mbps provisioned, burst to 400
    assert parent.rate_mbps == pytest.approx(100)
    assert parent.ceil_mbps == pytest.approx(400)
    s = prog.script()
    # each subscriber can burst up to their full plan (ceil 100)
    assert s.count("ceil 100mbit") >= 4


def test_invalid_ratio_rejected():
    subs = [Subscriber("c1", "203.0.113.1/32", 100, 100)]
    pipe = Pipe(id=3, name="bad", ptype=PipeType.CONTENDED,
                contention_ratio=3, subscribers=subs)
    with pytest.raises(CompileError):
        compile_plan(_plan([pipe]))


def test_application_pipe_needs_fwmark():
    pipe = Pipe(id=4, name="throttle-bt", ptype=PipeType.APPLICATION,
                download_mbps=50, match_label="bittorrent")
    with pytest.raises(CompileError):
        compile_plan(_plan([pipe]))


def test_application_pipe_fw_filter():
    pipe = Pipe(id=5, name="throttle-bt", ptype=PipeType.APPLICATION,
                download_mbps=50, match_label="bittorrent", fwmark=0x10)
    prog = compile_plan(_plan([pipe]))
    s = prog.script()
    assert "handle 16 fw" in s          # 0x10 == 16
    assert "ceil 50mbit" in s
    assert "match=bittorrent" in s


def test_upload_direction_matches_src():
    pipe = Pipe(id=6, name="DIA", ptype=PipeType.DEDICATED,
                download_mbps=100, upload_mbps=100,
                subscribers=[Subscriber("a", "203.0.113.9/32", 100, 100)])
    prog = compile_plan(_plan([pipe], direction=Direction.UPLOAD))
    assert "match ip src 203.0.113.9/32" in prog.script()


def test_oversubscription_warning():
    # two dedicated pipes of 700 Mbps each on a 1000 Mbps link -> warning
    p1 = Pipe(id=1, name="a", ptype=PipeType.DEDICATED, download_mbps=700,
              subscribers=[Subscriber("a", "203.0.113.1/32", 700, 700)])
    p2 = Pipe(id=2, name="b", ptype=PipeType.DEDICATED, download_mbps=700,
              subscribers=[Subscriber("b", "203.0.113.2/32", 700, 700)])
    prog = compile_plan(_plan([p1, p2], total=1000))
    assert any("exceeds link capacity" in w for w in prog.warnings)


def test_time_based_uses_window_peak():
    win = [
        TimeWindow("peak", [0, 1, 2, 3, 4], "18:00", "23:00", 50, 20),
        TimeWindow("offpeak", [0, 1, 2, 3, 4], "23:00", "18:00", 200, 100),
    ]
    pipe = Pipe(id=7, name="TOD", ptype=PipeType.TIME_BASED, windows=win,
                subscribers=[Subscriber("a", "203.0.113.7/32", 0, 0)])
    prog = compile_plan(_plan([pipe]))
    # ceil should reflect the peak window rate (200)
    assert "ceil 200mbit" in prog.script()


def test_class_ids_unique():
    pipes = [
        Pipe(id=i, name=f"d{i}", ptype=PipeType.DEDICATED, download_mbps=10,
             subscribers=[Subscriber(f"s{i}", f"203.0.113.{i}/32", 10, 10)])
        for i in range(1, 6)
    ]
    prog = compile_plan(_plan(pipes))
    ids = [cp.classid for cp in prog.class_map]
    assert len(ids) == len(set(ids))
