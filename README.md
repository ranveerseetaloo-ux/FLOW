# PipeCore

**Open-source, Allot NetXplorer–class bandwidth management for ISPs.**

PipeCore is a bandwidth-management platform that sits inline in an ISP core (a
transparent L2 bridge between the international transport layer and the
provider-edge router), classifies traffic with DPI, and enforces bandwidth
**pipes** — dedicated, contended, time-based, protocol- and application-based —
per public IP or network group, with a reporting dashboard and downloadable
reports. It runs on commodity Linux and deploys on a VM.

This repository is the **MVP scaffold**: the differentiating control plane and
the data-plane policy compiler are real and tested; the heavy line-rate engines
(XDP/LibreQoS, nDPI) plug in behind clean interfaces per the phased plan.

---

## Architecture at a glance

```
        International transport / upstream
                     │
        ┌────────────┴─────────────┐
        │   PipeCore data-plane     │   transparent L2 bridge
        │  ┌──────────────────────┐ │
        │  │ XDP fast path (bridge)│ │  ← LibreQoS / eBPF  (Phase 0/2)
        │  │ tc + CAKE/HTB shaping │ │  ← tc_compiler      (DONE, tested)
        │  │ nDPI classifier       │ │  ← dpi/classifier   (interface + stub)
        │  │ flow exporter         │ │  → ClickHouse
        │  │ HW fail-to-wire bypass│ │
        │  └──────────────────────┘ │
        └────────────┬─────────────┘
                     │
              Provider-edge router → subscribers

        ┌───────────────────────────────────────────┐
        │   PipeCore control plane (FastAPI)          │
        │   customers · IP groups · pipes · policies  │
        │   policy compiler → pushes tc to nodes      │
        │   reporting API + downloadable reports      │
        │   dashboard UI  ·  RBAC / JWT               │
        └───────────────────────────────────────────┘
```

See `docs/architecture.md` for detail and `docs/roadmap.md` for the phase plan.

## Repository layout

| Path | What it is | Status |
|------|------------|--------|
| `data-plane/shaper/tc_compiler.py` | Pipe model → Linux `tc`/CAKE/HTB commands | **Real + 10 unit tests** |
| `data-plane/shaper/models.py` | Canonical pipe/subscriber domain model | Real |
| `data-plane/shaper/applier.py` | Apply/dry-run tc to the kernel (safe) | Real |
| `data-plane/shaper/dpi/classifier.py` | nDPI integration seam + working stub | Interface + stub |
| `data-plane/shaper/flow_exporter.py` | Flow accounting → ClickHouse | Real (pluggable sink) |
| `data-plane/demo/compile_demo.py` | Zero-dep end-to-end demo | **Runnable now** |
| `data-plane/demo/netns_demo.sh` | Live shaping proof in network namespaces | Runnable on Linux+root |
| `data-plane/ebpf/` | XDP / LibreQoS integration notes | Phase-2 stub |
| `control-plane/app/` | FastAPI service: models, API, policy compiler | **Real + 3 unit tests** |
| `control-plane/app/core/pipe_builder.py` | DB pipes → data-plane plan → compile | Real, tested |
| `reporting/clickhouse/schema.sql` | Flow store schema + rollups | Real |
| `reporting/grafana/dashboard.json` | Grafana dashboard (alt to built-in UI) | Real |
| `ui/index.html` | Single-file dashboard (pipes, compile, reports) | Real |

## Quickstart

### 1. Try the data plane right now (no dependencies)

```bash
python3 data-plane/demo/compile_demo.py
```

Prints the tc/CAKE commands PipeCore generates for a realistic small-ISP mix
(a dedicated 200 Mbps pipe, a 1:4 contended residential pool, a BitTorrent
throttle, and a time-of-day pipe) and dry-run applies them.

### 2. Run the unit tests

```bash
pip install pytest
pytest data-plane/tests control-plane/tests -q     # 13 tests
```

### 3. Prove real shaping on any Linux box (root)

```bash
sudo data-plane/demo/netns_demo.sh 30    # shape a namespaced client to 30 Mbit
```

Creates a veth-connected namespace, applies a PipeCore-compiled policy, and (if
`iperf3` is installed) measures the enforced ceiling.

### 4. Run the control plane + dashboard

```bash
cd control-plane
pip install -r requirements.txt
uvicorn app.main:app --reload
# open http://localhost:8000/      (dashboard, demo login admin/admin)
# API docs at http://localhost:8000/docs
```

The API seeds a demo ISP config on first start (SQLite by default). Point
`PIPECORE_DB` at PostgreSQL for production.

### 5. Full stack with Docker

```bash
cp .env.example .env
docker compose up      # postgres + clickhouse + control-plane + ui
```

## What's real vs. what plugs in next

**Real and tested now:** the pipe/package model; the tc/CAKE/HTB compiler for all
five pipe types incl. 1:N contention math and oversubscription warnings; the
control-plane API (customers, IP groups, pipes, policy compile/apply, reporting,
JWT RBAC, audit); the reporting schema and dashboard.

**Plugs in per the roadmap:** native nDPI binding (replace `StubClassifier` with
`NDPIClassifier`); XDP/LibreQoS fast-path bridge and eBPF flow map; hardware
fail-to-wire bypass + HA; live ClickHouse ingest; PDF/XLSX report rendering.

## License

Intended to orchestrate GPL/LGPL engines (LibreQoS GPLv2, nDPI LGPLv3) as
separate programs over defined interfaces — keep the proprietary/open boundary
per the feasibility plan (Section 9) and confirm with counsel before distribution.
