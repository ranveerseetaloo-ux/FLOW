"""
Tests for the control-plane -> data-plane bridge (pipe_builder).

Uses SimpleNamespace stubs so it runs without a database or FastAPI — proving
the compile path the /api/policies/compile endpoint relies on.
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data-plane")))
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from shaper.models import Direction, PipeType  # noqa: E402
from app.core.pipe_builder import build_interface_plan, compile_interface  # noqa: E402


def _pipe(**kw):
    base = dict(id=1, name="p", ptype=PipeType.DEDICATED, download_mbps=100, upload_mbps=100,
                contention_ratio=1, priority=3, match_label=None, fwmark=None, windows_json=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _assign(pipe_id, cidr, dl=0, ul=0, label=""):
    return SimpleNamespace(pipe_id=pipe_id, cidr=cidr, download_mbps=dl, upload_mbps=ul,
                           label=label, ref=label or cidr)


def test_builder_groups_subscribers_by_pipe():
    pipes = [_pipe(id=1, name="DIA", ptype=PipeType.DEDICATED, download_mbps=200, upload_mbps=200)]
    assigns = [_assign(1, "203.0.113.50/32", label="acme")]
    plan = build_interface_plan(interface="eth0", direction=Direction.DOWNLOAD,
                                total_mbps=1000, pipes=pipes, assignments=assigns)
    assert len(plan.pipes) == 1
    assert plan.pipes[0].subscribers[0].cidr == "203.0.113.50/32"


def test_assignment_override_beats_pipe_default():
    pipes = [_pipe(id=2, name="res", ptype=PipeType.CONTENDED, contention_ratio=4,
                   download_mbps=100, upload_mbps=20)]
    # override this subscriber to 500 down
    assigns = [_assign(2, "203.0.113.1/32", dl=500, ul=50, label="vip")]
    plan = build_interface_plan(interface="eth0", direction=Direction.DOWNLOAD,
                                total_mbps=1000, pipes=pipes, assignments=assigns)
    assert plan.pipes[0].subscribers[0].download_mbps == 500


def test_full_compile_path_produces_tc():
    pipes = [
        _pipe(id=1, name="DIA", ptype=PipeType.DEDICATED, download_mbps=200, upload_mbps=200),
        _pipe(id=2, name="res", ptype=PipeType.CONTENDED, contention_ratio=4,
              download_mbps=100, upload_mbps=20),
        _pipe(id=3, name="bt", ptype=PipeType.APPLICATION, download_mbps=50,
              match_label="bittorrent", fwmark=0x10),
    ]
    assigns = [_assign(1, "203.0.113.50/32", label="acme")] + \
              [_assign(2, f"203.0.113.{i}/32", label=f"home{i}") for i in range(1, 5)]
    prog = compile_interface(interface="eth0", direction=Direction.DOWNLOAD,
                             total_mbps=1000, pipes=pipes, assignments=assigns)
    s = prog.script()
    assert "htb default fff" in s
    assert "match ip dst 203.0.113.50/32" in s
    assert "handle 16 fw" in s
    # dedicated 200 + contended provisioned 100 = 300 committed, under 1000 -> no warning
    assert not prog.warnings
