# PipeCore — Phase 2 Plan: Real DPI & Traffic Shaping

**Where you are now:** the control plane, pipe model, and tc/CAKE *compiler* all
work — but they generate shaping commands that aren't yet applied to live
traffic, and classification uses a simple port-based **stub** instead of real
deep packet inspection. Reports show sample data.

**Goal of Phase 2:** move from "generates correct commands" to "actually
inspects and shapes real traffic," with real usage data in the dashboard.

This is the hardest part of the project and it touches the Linux kernel and live
networking. So we do it in an order that is **safe, cheap, and confidence-
building first**, leaving the risky inline-bridge deployment for last. Read the
whole thing once, then start at Milestone 1.

---

## The mental model: three things must become "real"

| Piece | Now (demo) | Phase 2 (real) |
|-------|-----------|----------------|
| **Shaping** | tc commands printed to screen | tc commands *applied* to a live interface, actually limiting bandwidth |
| **Classification (DPI)** | port-based guess (`StubClassifier`) | nDPI inspects packets, identifies real apps, sets an "fwmark" |
| **Reporting** | built-in sample numbers | real per-flow counters shipped to ClickHouse |

And one deployment change ties them together: the box has to sit **inline** (in
the traffic path) as a transparent bridge, instead of off to the side.

We'll make each piece real one at a time.

---

## Milestone 1 — See real shaping work (½ day, no new hardware)

**Why first:** it proves the compiler's output genuinely limits bandwidth, using
a safe simulation on a single machine. Biggest confidence boost for least effort.

**What you do:** run the network-namespace demo that ships with PipeCore. It
creates a fake "client" connected by a virtual cable, applies a PipeCore-
compiled shaping policy, and measures the enforced speed.

On your server:
```bash
apt install -y iproute2 iperf3        # tc, ip, and a speed-test tool
cd ~/pipecore
bash data-plane/demo/netns_demo.sh 30 # shape the fake client to 30 Mbit
```

**You'll know it works when:** the `iperf3` result at the end reads roughly
**30 Mbit/s**, not your full link speed. You just watched PipeCore throttle real
packets. Try `50`, `100` — the ceiling moves with it.

**Concept you're learning:** `tc` (traffic control) + `CAKE`/`HTB` are the Linux
kernel features doing the actual limiting. PipeCore just writes their config.

---

## Milestone 2 — Real usage data in the dashboard (½–1 day)

**Why now:** it's self-contained (no inline networking) and makes the reporting
side real, so the dashboard stops showing sample numbers.

**What you do:**
1. Stand up ClickHouse (the reporting database) with Docker:
   ```bash
   curl -fsSL https://get.docker.com | sudo sh      # one-time Docker install
   cd ~/pipecore
   docker compose up -d clickhouse                  # loads reporting/clickhouse/schema.sql
   ```
2. Point the backend at it by setting `PIPECORE_CLICKHOUSE` (already in the
   compose defaults; when you move to the systemd service, add the env line from
   the setup guide).
3. Feed it flow records. At first you can insert **synthetic** flows with a small
   script (I can generate one) to see the charts light up with "live" data; later
   these come from the real data-plane counters (Milestone 4).

**You'll know it works when:** the Traffic Report's "source" label changes from
`sample` to real ClickHouse rows, and the numbers move as you insert data.

**Concept:** the data-plane counts traffic → exports `FlowRecord`s
(`data-plane/shaper/flow_exporter.py`) → ClickHouse stores them → the dashboard
queries them.

---

## Milestone 3 — Real classification with nDPI (2–5 days)

**Why now:** this is the "deep packet inspection" heart. It replaces the
port-guessing stub with a real engine that recognises 450+ applications.

**What you do (staged):**
1. **Get nDPI and just look at what it sees.** Install it and run its bundled
   reader against live traffic to watch it classify flows — no coding yet:
   ```bash
   apt install -y build-essential git autoconf automake libtool pkg-config libpcap-dev
   git clone https://github.com/ntop/nDPI.git
   cd nDPI && ./autogen.sh && make
   sudo ./example/ndpiReader -i eth0        # watch it label real flows
   ```
   Seeing nDPI print "Netflix / YouTube / QUIC / BitTorrent" on your own traffic
   is the moment DPI becomes real to you.
2. **Wire it into PipeCore.** Replace `StubClassifier` with a real
   `NDPIClassifier` in `data-plane/shaper/dpi/classifier.py`. The clean approach:
   a small helper that inspects the first ~10 packets of each new flow, gets the
   nDPI verdict, and writes the matching **fwmark** so the kernel can shape the
   rest of the flow cheaply.
3. **Connect verdicts to shaping.** The compiler already emits
   `tc filter ... handle <fwmark> fw` rules for protocol/application pipes — so
   once nDPI sets the fwmark, those pipes start actually catching the right
   traffic.

**You'll know it works when:** you create an "application" pipe (e.g. throttle
BitTorrent to 50 Mbit) and BitTorrent traffic is actually held at 50, while other
apps are untouched.

**Honest note:** the Python↔nDPI binding is the most "developer-ish" task in the
whole project. This is a good point to pair with a developer, or I can write the
binding and the fast-path glue with you.

---

## Milestone 4 — Real flow accounting from the data plane (2–3 days)

**Why now:** connects Milestones 2 and 3 — the live per-flow byte/packet counters
(and the nDPI app label) become the real feed into ClickHouse, so reports reflect
actual subscriber usage instead of synthetic inserts.

**What you do:** count bytes/packets per flow in the fast path (an eBPF map, or
initially from nDPI's own accounting), attach the subscriber + app + pipe, and
drain them through `flow_exporter.py` into ClickHouse on a timer.

**You'll know it works when:** the dashboard's per-application, per-pipe,
per-customer reports match what you actually generate on the test client.

---

## Milestone 5 — Go inline for real: the transparent bridge (the hard one)

**Why last:** this is the only step that can take a network **down** if done
wrong, so we do it only after everything above is proven in a lab.

**What you do:**
1. **Get a two-interface box** (physical server or a VM with two NICs): one side
   faces the upstream/internet, the other faces the client/router. Traffic passes
   *through* it.
2. **Bridge the two interfaces** (Layer-2, transparent — no IP change on the
   traffic) and apply PipeCore's shaping on the bridge.
3. **Adopt LibreQoS** for the production fast path. LibreQoS (GPLv2) is the proven
   XDP + CAKE engine that shapes tens of Gbps per subscriber. You feed it the same
   pipe plan PipeCore compiles; it handles the line-rate bridging. This is the
   "don't rebuild the dangerous part" strategy from the feasibility plan.
4. **Add fail-safety:** a hardware **fail-to-wire** bypass NIC so that if the box
   loses power or crashes, the two ports short together and traffic keeps flowing.
   Keep `PIPECORE_DRY_RUN=true` until this is in place and tested.
5. **Test failover hard** before any real subscribers are behind it.

**You'll know it works when:** real client traffic flows through the bridge,
gets classified and shaped per its pipe, and pulling the box's power does **not**
drop the link.

**Honest note:** Milestone 5 is where you'll want a network engineer and real
lab time. It's proven technology (LibreQoS runs in production at many ISPs), but
inline core deployment is not a beginner solo task — plan for help here.

---

## Recommended order & realistic effort

```
Milestone 1  See shaping work (netns)          ~½ day   ← start here, today
Milestone 2  Real reporting data (ClickHouse)  ~1 day
Milestone 3  nDPI classification               ~2–5 days (developer help useful)
Milestone 4  Real flow accounting              ~2–3 days
Milestone 5  Inline bridge + LibreQoS + HA     lab + network engineer
```

Milestones 1–2 you can do yourself this week with my guidance. 3–4 are real
development — doable with help. 5 is a deployment project with hardware.

## The one thing to do next

**Milestone 1.** Install `iproute2` + `iperf3` and run the netns demo — watch
PipeCore throttle real packets to the exact rate you ask for. It's safe, needs no
new hardware, and turns "it compiles commands" into "it actually shapes traffic"
in about ten minutes. Say the word and I'll walk you through reading the result.
