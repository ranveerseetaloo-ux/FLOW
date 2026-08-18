# PipeCore roadmap

Mirrors the feasibility & build plan. This scaffold delivers the **Phase 1 core**
and the interfaces for later phases.

| Phase | Goal | State in this repo |
|-------|------|--------------------|
| **0 — PoC** | Inline bridge on a VM shapes + classifies live traffic | `netns_demo.sh` proves shaping; LibreQoS+nDPI attach is the field step |
| **1 — Pipe model & policy engine** | Configurable packages → tc | **Delivered**: model, compiler, control-plane API, dashboard |
| **2 — DPI-driven shaping** | Protocol/application shaping via nDPI | Interface + stub + fwmark seam ready; native binding pending |
| **3 — Reporting product** | NetXplorer-class dashboards + exports | Schema, API, UI, CSV export delivered; live ingest + PDF/XLSX pending |
| **4 — Hardening / HA / appliance** | Production-safe VM appliance | Dry-run safety + compose delivered; bypass/HA/OVA pending |

## Immediate next steps

1. Stand up LibreQoS + nDPI inline on a lab VM (Phase 0); feed it `tc_compiler` output.
2. Replace `StubClassifier` with the native `NDPIClassifier` binding.
3. Wire the eBPF flow map (`data-plane/ebpf/`) for line-rate fwmark shaping.
4. Point the flow exporter at live ClickHouse; enable PDF/XLSX report rendering.
5. Add hardware fail-to-wire bypass + active/standby HA; package as OVA/qcow2.
