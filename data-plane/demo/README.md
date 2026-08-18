# Data-plane demos

**`compile_demo.py`** — zero dependencies. Defines a realistic small-ISP pipe mix,
compiles it to tc/CAKE, prints the script + class map, and dry-run applies it.

```bash
python3 data-plane/demo/compile_demo.py
```

**`netns_demo.sh`** — proves the compiled tc actually shapes real traffic. Creates
a veth-connected network namespace, applies a PipeCore-compiled policy on the host
egress veth, and (with `iperf3`) measures the enforced ceiling. Needs Linux + root
+ iproute2; CAKE falls back to fq_codel if `sch_cake` is absent.

```bash
sudo data-plane/demo/netns_demo.sh 30    # shape to 30 Mbit
```
