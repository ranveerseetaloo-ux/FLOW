"""
PipeCore — flow accounting / exporter.

The data-plane node counts per-flow bytes/packets/latency (eBPF map in
production) and ships records to the reporting store (ClickHouse). This module
defines the record schema and a batching exporter with a pluggable sink so the
pipeline is testable without a live ClickHouse.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Callable, Optional


@dataclass
class FlowRecord:
    ts: float               # unix seconds (window end)
    subscriber_ref: str     # customer / account
    src_ip: str
    dst_ip: str
    application: str        # from DPI
    protocol: str
    pipe_id: int
    bytes_down: int
    bytes_up: int
    packets: int
    rtt_ms: float           # ePPing-style latency sample (0 if unknown)


Sink = Callable[[list[FlowRecord]], None]


def clickhouse_sink(dsn: str) -> Sink:  # pragma: no cover - needs a server
    """Return a sink that inserts records into ClickHouse. Lazy-imports driver."""
    def _sink(records: list[FlowRecord]) -> None:
        from clickhouse_driver import Client  # type: ignore
        client = Client.from_url(dsn)
        client.execute(
            "INSERT INTO flows (ts, subscriber_ref, src_ip, dst_ip, application, "
            "protocol, pipe_id, bytes_down, bytes_up, packets, rtt_ms) VALUES",
            [tuple(asdict(r).values()) for r in records],
        )
    return _sink


class FlowExporter:
    def __init__(self, sink: Optional[Sink] = None, *, batch_size: int = 500):
        self.sink = sink or (lambda recs: None)
        self.batch_size = batch_size
        self._buf: list[FlowRecord] = []

    def add(self, rec: FlowRecord) -> None:
        self._buf.append(rec)
        if len(self._buf) >= self.batch_size:
            self.flush()

    def flush(self) -> int:
        if not self._buf:
            return 0
        n = len(self._buf)
        self.sink(self._buf)
        self._buf = []
        return n

    def now(self) -> float:
        return time.time()
