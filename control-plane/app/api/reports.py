"""
Reporting endpoints (NetXplorer-equivalent analytics).

Queries the ClickHouse flow store for usage by protocol, application, pipe, IP
and customer. Falls back to a synthetic sample when ClickHouse is unreachable so
the dashboard and downloadable-report features are demonstrable end-to-end.
Downloadable reports are rendered server-side (CSV here; PDF/XLSX in Phase 3).
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from ..config import get_settings
from .auth import current_user

router = APIRouter(prefix="/reports", tags=["reports"])
settings = get_settings()

_DIMENSIONS = {"application", "protocol", "pipe", "ip", "customer"}


def _query_clickhouse(dimension: str, hours: int) -> list[dict]:  # pragma: no cover
    from clickhouse_driver import Client  # lazy
    client = Client.from_url(settings.clickhouse_dsn)
    col = {"application": "application", "protocol": "protocol", "pipe": "pipe_id",
           "ip": "src_ip", "customer": "subscriber_ref"}[dimension]
    rows = client.execute(
        f"SELECT {col} AS k, sum(bytes_down+bytes_up) AS bytes, count() AS flows "
        f"FROM flows WHERE ts > now() - INTERVAL %(h)s HOUR GROUP BY k ORDER BY bytes DESC LIMIT 50",
        {"h": hours},
    )
    return [{"key": str(k), "bytes": int(b), "flows": int(f)} for k, b, f in rows]


def _sample(dimension: str) -> list[dict]:
    samples = {
        "application": [("YouTube", 4_200_000_000, 1820), ("Netflix", 3_600_000_000, 640),
                        ("QUIC/Google", 2_100_000_000, 5400), ("BitTorrent", 900_000_000, 210),
                        ("Zoom", 620_000_000, 95), ("Other", 1_500_000_000, 12000)],
        "protocol": [("tls", 8_800_000_000, 19000), ("quic", 2_300_000_000, 6100),
                     ("http", 700_000_000, 3200), ("bittorrent", 900_000_000, 210)],
        "pipe": [("Residential-1to4", 7_100_000_000, 15400), ("DIA-AcmeBank", 2_800_000_000, 900),
                 ("Throttle-BitTorrent", 900_000_000, 210)],
        "ip": [("203.0.113.1", 1_400_000_000, 2100), ("203.0.113.2", 1_200_000_000, 1800),
               ("203.0.113.50", 2_800_000_000, 900)],
        "customer": [("AcmeBank", 2_800_000_000, 900), ("home1", 1_400_000_000, 2100),
                     ("home2", 1_200_000_000, 1800)],
    }
    return [{"key": k, "bytes": b, "flows": f} for k, b, f in samples.get(dimension, [])]


def _rows(dimension: str, hours: int) -> tuple[list[dict], str]:
    """Return (rows, source) where source is 'clickhouse' or 'sample'."""
    try:
        rows = _query_clickhouse(dimension, hours)
        if rows:                      # real data present
            return rows, "clickhouse"
        return _sample(dimension), "sample (clickhouse empty)"
    except Exception:  # noqa: BLE001 - demo fallback when CH is unreachable
        return _sample(dimension), "sample (clickhouse unreachable)"


@router.get("/top")
def top(dimension: str = Query("application"), hours: int = 24, user=Depends(current_user)):
    dimension = dimension if dimension in _DIMENSIONS else "application"
    rows, source = _rows(dimension, hours)
    return {"dimension": dimension, "hours": hours, "source": source, "rows": rows}


@router.get("/download")
def download(dimension: str = Query("application"), hours: int = 24, user=Depends(current_user)):
    """Downloadable CSV report."""
    dimension = dimension if dimension in _DIMENSIONS else "application"
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([dimension, "bytes", "flows", "GB"])
    rows, _source = _rows(dimension, hours)
    for r in rows:
        w.writerow([r["key"], r["bytes"], r["flows"], round(r["bytes"] / 1e9, 3)])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=report_{dimension}_{hours}h.csv"},
    )
