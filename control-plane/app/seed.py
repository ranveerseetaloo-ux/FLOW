"""Seed demo data: an admin user plus a realistic small-ISP configuration."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from shaper.models import PipeType  # type: ignore

from .api.auth import hash_password
from .models import Customer, IPGroup, Pipe, User


def seed(db: Session) -> None:
    if db.scalar(select(User).limit(1)):
        return  # already seeded

    db.add(User(username="admin", password_hash=hash_password("admin"), role="admin"))

    # --- pipes (bandwidth packages) ---
    dia = Pipe(name="DIA-AcmeBank", ptype=PipeType.DEDICATED, download_mbps=200, upload_mbps=200, priority=1)
    res = Pipe(name="Residential-1to4", ptype=PipeType.CONTENDED, contention_ratio=4,
               download_mbps=100, upload_mbps=20, priority=3)
    biz = Pipe(name="Business-1to8", ptype=PipeType.CONTENDED, contention_ratio=8,
               download_mbps=50, upload_mbps=25, priority=2)
    bt = Pipe(name="Throttle-BitTorrent", ptype=PipeType.APPLICATION, download_mbps=50,
              match_label="bittorrent", fwmark=0x10, priority=5)
    tod = Pipe(name="NightBoost", ptype=PipeType.TIME_BASED, download_mbps=100, upload_mbps=50,
               windows_json=json.dumps([
                   {"name": "peak", "days": [0, 1, 2, 3, 4, 5, 6], "start": "18:00", "end": "23:00",
                    "download_mbps": 50, "upload_mbps": 25},
                   {"name": "offpeak", "days": [0, 1, 2, 3, 4, 5, 6], "start": "23:00", "end": "18:00",
                    "download_mbps": 200, "upload_mbps": 100},
               ]))
    db.add_all([dia, res, biz, bt, tod])
    db.flush()

    # --- customers + IP groups assigned to pipes ---
    acme = Customer(ref="acme", name="Acme Bank Ltd", contact_email="noc@acme.example")
    homes = Customer(ref="res-pool", name="Residential Pool")
    db.add_all([acme, homes])
    db.flush()

    db.add(IPGroup(customer_id=acme.id, cidr="203.0.113.50/32", label="acme-hq", pipe_id=dia.id))
    for i in range(1, 5):
        db.add(IPGroup(customer_id=homes.id, cidr=f"203.0.113.{i}/32",
                       label=f"home{i}", pipe_id=res.id))
    db.commit()
