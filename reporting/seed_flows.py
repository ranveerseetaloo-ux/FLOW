#!/usr/bin/env python3
"""
Generate synthetic flow records into ClickHouse so the dashboard shows "live"
traffic data during development (Milestone 2), before the real data-plane
counters exist (Milestone 4).

Usage (from the repo root, with the control-plane venv active):
    python3 reporting/seed_flows.py            # inserts ~2000 flows over last 24h
    python3 reporting/seed_flows.py 5000       # custom count

Reads the ClickHouse DSN from PIPECORE_CLICKHOUSE, defaulting to the local
docker-compose ClickHouse.
"""
import os
import random
import sys
import time

from clickhouse_driver import Client

DSN = os.getenv("PIPECORE_CLICKHOUSE", "clickhouse://localhost:9000/pipecore")

# (application, protocol) pairs weighted to look like a real access network
APPS = [
    ("YouTube", "quic", 30), ("Netflix", "tls", 18), ("QUIC/Google", "quic", 15),
    ("Facebook", "tls", 10), ("TikTok", "tls", 8), ("Zoom", "udp", 5),
    ("BitTorrent", "bittorrent", 4), ("WhatsApp", "tls", 6), ("Windows Update", "http", 2),
    ("Other", "tls", 12),
]
CUSTOMERS = [("acme", 1, "203.0.113.50")] + [
    (f"home{i}", 2, f"203.0.113.{i}") for i in range(1, 5)
]


def weighted_app():
    total = sum(w for *_, w in APPS)
    r = random.uniform(0, total)
    upto = 0
    for app, proto, w in APPS:
        upto += w
        if r <= upto:
            return app, proto
    return APPS[-1][0], APPS[-1][1]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    client = Client.from_url(DSN)
    now = int(time.time())
    rows = []
    for _ in range(n):
        app, proto = weighted_app()
        ref, pipe_id, ip = random.choice(CUSTOMERS)
        down = random.randint(200_000, 400_000_000)
        up = int(down * random.uniform(0.02, 0.2))
        rows.append((
            now - random.randint(0, 24 * 3600),   # ts within last 24h
            ref, ip, "142.250.0.1", app, proto, pipe_id,
            down, up, random.randint(5, 5000), round(random.uniform(2, 90), 1),
        ))
    client.execute(
        "INSERT INTO pipecore.flows (ts, subscriber_ref, src_ip, dst_ip, application, "
        "protocol, pipe_id, bytes_down, bytes_up, packets, rtt_ms) VALUES",
        rows,
    )
    total = client.execute("SELECT count() FROM pipecore.flows")[0][0]
    print(f"Inserted {n} synthetic flows. Table now holds {total} rows.")


if __name__ == "__main__":
    main()
