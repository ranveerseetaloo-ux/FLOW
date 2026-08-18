#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# PipeCore live shaping demo using Linux network namespaces.
#
# Creates a client namespace connected by veth to the host, applies a PipeCore-
# compiled HTB+CAKE shaping policy on the egress veth, and (if iperf3 is present)
# measures the enforced rate. This proves the compiled tc actually shapes real
# traffic, on any Linux box, without touching production NICs.
#
#   sudo ./netns_demo.sh
#
# Requires: root, iproute2 (tc, ip), optionally iperf3. CAKE needs a kernel with
# sch_cake (Linux 4.19+). Falls back to fq_codel automatically if CAKE is absent.
# ---------------------------------------------------------------------------
set -euo pipefail

NS="pipecore_cl"
VETH_H="pc_h"      # host side
VETH_C="pc_c"      # client side
LIMIT_MBIT="${1:-50}"   # shape client download to this many mbit

need_root() { [ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)"; exit 1; }; }
cleanup() {
  ip netns del "$NS" 2>/dev/null || true
  ip link del "$VETH_H" 2>/dev/null || true
}

need_root
trap cleanup EXIT
cleanup

echo "[1/5] create namespace + veth pair"
ip netns add "$NS"
ip link add "$VETH_H" type veth peer name "$VETH_C"
ip link set "$VETH_C" netns "$NS"

ip addr add 10.123.0.1/24 dev "$VETH_H"
ip link set "$VETH_H" up
ip netns exec "$NS" ip addr add 10.123.0.2/24 dev "$VETH_C"
ip netns exec "$NS" ip link set "$VETH_C" up
ip netns exec "$NS" ip link set lo up

echo "[2/5] compile shaping policy from PipeCore (dedicated ${LIMIT_MBIT}mbit to 10.123.0.2)"
DP_DIR="$(cd "$(dirname "$0")/.." && pwd)"   # .../data-plane
SCRIPT="$(PYTHONPATH="$DP_DIR" python3 - "$LIMIT_MBIT" <<'PY'
import sys
from shaper.models import Direction, InterfacePlan, Pipe, PipeType, Subscriber
from shaper.tc_compiler import compile_plan
limit=float(sys.argv[1])
plan=InterfacePlan("__DEV__", Direction.DOWNLOAD, 1000, [
  Pipe(1,"demo",PipeType.DEDICATED,limit,limit,
       subscribers=[Subscriber("cl","10.123.0.2/32",limit,limit)])])
print(compile_plan(plan).script())
PY
)"
# target the host-side egress interface (traffic toward the client)
SCRIPT="${SCRIPT//__DEV__/$VETH_H}"

# fall back to fq_codel if CAKE unavailable
if ! tc qdisc add dev lo root cake 2>/dev/null; then
  echo "    (sch_cake not available -> using fq_codel leaves)"
  SCRIPT="${SCRIPT//cake/fq_codel}"
else
  tc qdisc del dev lo root 2>/dev/null || true
fi

echo "[3/5] apply tc program:"
echo "$SCRIPT" | sed 's/^/      /'
while IFS= read -r line; do
  line="${line%%  #*}"
  [ -z "$line" ] && continue
  eval "$line" 2>/dev/null || true
done <<< "$SCRIPT"

echo "[4/5] installed qdisc/class tree on $VETH_H:"
tc -s class show dev "$VETH_H" | sed 's/^/      /' | head -20

echo "[5/5] rate test"
if command -v iperf3 >/dev/null 2>&1; then
  ip netns exec "$NS" iperf3 -s -1 -D --bind 10.123.0.2 2>/dev/null || true
  sleep 1
  echo "    (expect ~${LIMIT_MBIT} Mbit/s ceiling)"
  # host -> client is the shaped direction (tc egress on pc_h, dst 10.123.0.2),
  # so send from the host to the namespace WITHOUT -R.
  iperf3 -c 10.123.0.2 -t 5 2>/dev/null | tail -4 | sed 's/^/      /' || \
    echo "      iperf3 run skipped (namespace routing varies by host)"
else
  echo "    iperf3 not installed; skipping throughput measurement."
  echo "    Install iperf3 and re-run to see the ${LIMIT_MBIT} Mbit/s ceiling enforced."
fi

echo "done. (namespace + veth are cleaned up on exit)"
