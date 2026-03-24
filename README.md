# TCP Congestion Control Visualisations

Python simulations that plot **congestion window (cwnd) over time** for four
TCP congestion control algorithms. Each script is self-contained and produces
a labelled matplotlib figure saved as a PNG alongside a per-RTT summary table
printed to stdout.

## Algorithms

| Directory | Script | Algorithm class | Key reference |
|-----------|--------|-----------------|---------------|
| `reno/` | `tcp_reno.py` | Loss-based | RFC 5681 |
| `newreno/` | `tcp_newreno.py` | Loss-based | RFC 6582 |
| `vegas/` | `tcp_vegas.py` | Delay-based | Brakmo & Peterson 1994 |
| `cubic/` | `tcp_cubic.py` | Loss-based (cubic) | RFC 9438 |

## Algorithm summaries

### TCP Reno
The classic baseline. cwnd grows exponentially during **Slow Start** and
linearly (+1 MSS/RTT) during **Congestion Avoidance**.

- **Fast Retransmit** (3 dup-ACKs): `ssthresh = cwnd/2`, `cwnd = ssthresh` → back to Congestion Avoidance.
- **RTO** (timeout): `ssthresh = cwnd/2`, `cwnd = 1` → restart Slow Start.

The characteristic sawtooth pattern results from cwnd being halved on every
loss event.

### TCP New Reno (RFC 6582)
Fixes Reno's behaviour when **multiple packets are lost in one window**.

- On 3 dup-ACKs, enters **Fast Recovery** with window inflation (`cwnd = ssthresh + 3`).
- **Partial ACK** (not all losses recovered): stays in Fast Recovery, retransmits next missing segment, deflates cwnd — does _not_ exit recovery prematurely like Reno does.
- **Full ACK** (all losses recovered): `cwnd = ssthresh`, exit to Congestion Avoidance.

### TCP Vegas
A **delay-based** algorithm that detects congestion from RTT growth before
packets are dropped, resulting in a smooth cwnd curve rather than a sawtooth.

```
diff = cwnd × (1/BaseRTT − 1/ActualRTT)

diff < α  →  cwnd += 1   (underutilised)
diff > β  →  cwnd -= 1   (queue building)
α ≤ diff ≤ β  →  no change
```

Vegas exits Slow Start as soon as `ActualRTT > BaseRTT` (queue detected).
The stable operating point is `CAPACITY + α ≤ cwnd ≤ CAPACITY + β`.

Because cwnd is held near the bandwidth-delay product, packet loss is rare;
fast retransmit and RTO are included in the simulation for completeness.

### TCP CUBIC (RFC 9438)
The default algorithm in Linux since kernel 2.6.19. Replaces the linear
Congestion Avoidance ramp with a **cubic function** of time since the last
loss event:

```
W_cubic(t) = C × (t − K)³ + W_max
K = ∛(W_max × β / C)
```

- Left of inflection point K: concave-down (probing back toward W_max quickly).
- Right of K: concave-up (aggressive exploration beyond W_max).
- On loss: `W_max = cwnd`, `cwnd = cwnd × (1 − β)` (β = 0.7, so 30% reduction vs Reno's 50%).

CUBIC is more aggressive than Reno on high-bandwidth, high-RTT paths (large
BDP) because the cubic curve recovers lost throughput much faster.

## Comparison at a glance

| Property | Reno | New Reno | Vegas | CUBIC |
|---|---|---|---|---|
| Growth (cong. avoid.) | Linear +1/RTT | Linear +1/RTT | ±1 based on diff | Cubic in time |
| Reacts to | Packet loss | Packet loss | RTT increase | Packet loss |
| Loss penalty | cwnd/2 | cwnd/2 | cwnd/2 | cwnd × 0.7 |
| Multi-loss recovery | Poor | Good | N/A (rare loss) | Good |
| High-BDP performance | Poor | Poor | Moderate | Excellent |

## Requirements

```
pip install matplotlib numpy
```

## Usage

Run any script from its own directory (the PNG is saved there):

```bash
cd reno   && python tcp_reno.py
cd newreno && python tcp_newreno.py
cd vegas   && python tcp_vegas.py
cd cubic   && python tcp_cubic.py
```

Each script prints a per-RTT table of `cwnd`, `ssthresh`, and phase, then
opens an interactive plot window and saves a PNG.

## Tuning

All key parameters are defined as module-level constants at the top of each
file — `INIT_CWND`, `INIT_SSTHRESH`, event RTTs, etc. — so they are easy to
adjust without reading the simulation logic.
