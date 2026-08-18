# Data-plane fast path (XDP / eBPF / LibreQoS)

This directory is the **Phase-2 integration point** for the line-rate fast path.
The `tc_compiler` already produces the HTB/CAKE hierarchy; what plugs in here is
the high-performance bridge and the DPI flow-map that make classification cheap
at 10 Gbps.

## Strategy: leverage LibreQoS, don't rebuild

Per the feasibility plan, the inline bridge + per-subscriber shaping is provided
by **LibreQoS** (GPLv2, XDP + CAKE, proven >10 Gbps on commodity hardware). We do
not re-implement it. The integration work is:

1. **Bridge / attach** — run PipeCore's node agent alongside LibreQoS; feed it the
   compiled shaping plan (`tc_compiler` output maps directly onto the
   HTB+CAKE model LibreQoS manages).
2. **DPI flow map** — an eBPF map keyed by the 5-tuple stores the fwmark that the
   nDPI classifier resolves for each flow. The XDP program marks packets so the
   `fw` filters emitted by `tc_compiler` steer them into the right class without
   per-packet userspace inspection.
3. **Flow accounting** — per-flow byte/packet/RTT counters in an eBPF map, drained
   by `flow_exporter.py` into ClickHouse.

## Why the fwmark seam matters

`tc_compiler` emits, for every protocol/application pipe:

```
tc filter ... handle <fwmark> fw flowid <classid>
```

So the *only* thing the fast path must do for L7 shaping is: inspect the first
~10 packets of a flow with nDPI, decide the label, and write the corresponding
fwmark into the flow map. Every subsequent packet is shaped in-kernel at line
rate. This keeps DPI cost proportional to *new flows*, not *packets* — the key
to holding throughput with classification enabled.

## Files to add in Phase 2

- `xdp_bridge.c` / loader — or the LibreQoS attach shim
- `flow_map.c` — 5-tuple → {fwmark, counters} BPF map
- `ndpi_marker.py` — userspace: pull new flows, run `NDPIClassifier`, set fwmark

None of these are required for the control plane, the policy compiler, or the
reporting layer to function — they are the throughput upgrade, added once Phase 0
proves the model on real traffic.
