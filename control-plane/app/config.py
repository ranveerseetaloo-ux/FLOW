"""Central configuration and path bootstrap for the control plane."""
from __future__ import annotations

import os
import sys
from functools import lru_cache

# --- make the shared data-plane package importable ------------------------
# The tc compiler / models live in ../../data-plane. The control plane reuses
# them so there is exactly one definition of a "pipe".
_HERE = os.path.dirname(os.path.abspath(__file__))
_DATAPLANE = os.path.normpath(os.path.join(_HERE, "..", "..", "data-plane"))
if _DATAPLANE not in sys.path:
    sys.path.insert(0, _DATAPLANE)


class Settings:
    """Environment-driven settings (kept dependency-light on purpose)."""

    def __init__(self) -> None:
        self.database_url: str = os.getenv(
            "PIPECORE_DB", "sqlite:///./pipecore.db"
        )
        self.clickhouse_dsn: str = os.getenv(
            "PIPECORE_CLICKHOUSE", "clickhouse://localhost:9000/pipecore"
        )
        self.jwt_secret: str = os.getenv("PIPECORE_JWT_SECRET", "dev-secret-change-me")
        self.jwt_ttl_min: int = int(os.getenv("PIPECORE_JWT_TTL_MIN", "480"))
        # data-plane node control endpoints, comma-separated host:port
        self.dataplane_nodes: list[str] = [
            n.strip() for n in os.getenv("PIPECORE_NODES", "127.0.0.1:9700").split(",")
            if n.strip()
        ]
        # apply shaping for real, or dry-run and just return the tc script
        self.dry_run: bool = os.getenv("PIPECORE_DRY_RUN", "true").lower() == "true"


@lru_cache
def get_settings() -> Settings:
    return Settings()
