"""
PipeCore — DPI classifier interface (nDPI integration point).

This is the seam where nDPI plugs in. The production implementation inspects
the first N packets of each flow with nDPI, resolves an application/protocol
label, and installs an fwmark in an eBPF flow map (or via nftables) so the
kernel fast-path can shape every subsequent packet of that flow at line rate
without re-inspection.

Here we define the stable interface plus a rule-based stub so the rest of the
platform (policy compiler, tests, demo) is fully runnable before the native
nDPI binding is wired in. Swap `StubClassifier` for `NDPIClassifier` in Phase 2.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class FlowKey:
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    proto: str          # "tcp" | "udp"


@dataclass
class Verdict:
    application: str     # e.g. "netflix", "youtube", "bittorrent", "quic", "unknown"
    protocol: str        # e.g. "tls", "quic", "http", "bittorrent"
    fwmark: int          # mark to program into the fast path
    confidence: float    # 0..1


class Classifier(ABC):
    @abstractmethod
    def classify(self, flow: FlowKey, first_packets: bytes = b"") -> Verdict: ...


# --- fwmark registry: label -> mark. Kept in sync with pipe.fwmark values. ---
FWMARK_REGISTRY: dict[str, int] = {
    "bittorrent": 0x10,
    "netflix": 0x11,
    "youtube": 0x12,
    "quic": 0x13,
    "tls": 0x14,
    "voip": 0x15,
    "unknown": 0x00,
}


class StubClassifier(Classifier):
    """Port/heuristic-based stand-in for nDPI. Deterministic, no deps."""

    def classify(self, flow: FlowKey, first_packets: bytes = b"") -> Verdict:
        dp = flow.dst_port
        if flow.proto == "udp" and dp == 443:
            return Verdict("quic", "quic", FWMARK_REGISTRY["quic"], 0.6)
        if dp == 443:
            return Verdict("tls", "tls", FWMARK_REGISTRY["tls"], 0.5)
        if dp in (6881, 6882, 6883, 51413):
            return Verdict("bittorrent", "bittorrent", FWMARK_REGISTRY["bittorrent"], 0.8)
        if flow.proto == "udp" and 16384 <= dp <= 32767:
            return Verdict("voip", "rtp", FWMARK_REGISTRY["voip"], 0.4)
        return Verdict("unknown", flow.proto, FWMARK_REGISTRY["unknown"], 0.1)


class NDPIClassifier(Classifier):
    """
    Production classifier backed by nDPI (LGPLv3).

    Phase-2 implementation notes:
      * bind libndpi via cffi / a small C shim, or run ntopng's nDPI in-line;
      * inspect up to ~10 packets per flow, then cache the verdict;
      * program the fwmark into the eBPF flow map keyed by the 5-tuple so the
        XDP fast path marks the rest of the flow without userspace involvement.
    """

    def __init__(self) -> None:
        raise NotImplementedError(
            "NDPIClassifier is the Phase-2 integration point; use StubClassifier "
            "until the native nDPI binding is wired in."
        )

    def classify(self, flow: FlowKey, first_packets: bytes = b"") -> Verdict:  # pragma: no cover
        raise NotImplementedError
