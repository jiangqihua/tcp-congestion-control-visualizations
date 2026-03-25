# TCP Congestion Control Visualisations

Python simulations that plot **congestion window (cwnd) over time** for six
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
| `highspeed/` | `tcp_highspeed.py` | Loss-based (state-dependent AIMD) | RFC 3649 |
| `bbr/` | `tcp_bbr.py` | Model-based (bandwidth + RTT) | Google 2016 |

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

### TCP HighSpeed (HSTCP, RFC 3649)
Designed for high-bandwidth, high-RTT paths where Reno's fixed +1 MSS/RTT
growth is far too slow. HSTCP uses **cwnd-dependent AIMD parameters**:

```
cwnd ≤ LOW_WINDOW  :  a(w) = 1,   keep(w) = 50%   ← identical to Reno
cwnd ≥ HIGH_WINDOW :  a(w) = 12,  keep(w) = 85%   ← 12× faster growth, only 15% cut
```

Parameters are log-interpolated between the two extremes.

- **Additive increase**: `cwnd += a(w)` per RTT — up to 12 MSS/RTT at high windows.
- **Fast Retransmit**: `ssthresh = cwnd × keep(w)` — much softer than Reno's 50% halving.
- **RTO**: `ssthresh = cwnd/2`, `cwnd = 1` — same hard reset as Reno.

The plot overlays a TCP Reno reference line (same loss events) so the
throughput advantage of HSTCP is directly visible. The `a(w)` value in effect
is annotated along the HSTCP cwnd line.

## Comparison at a glance

### TCP BBR (Google 2016)
A **model-based** algorithm that estimates two network properties and sets
cwnd directly from them — without reacting to loss at all.

```
BtlBW   = windowed max of delivery rate   (bottleneck bandwidth)
RTprop  = windowed min of RTT             (propagation delay)
cwnd   ≈ BtlBW × RTprop                  (= BDP, just fills the pipe)
```

BBR cycles through four states:

| State | Behaviour |
|---|---|
| **Startup** | Double pacing rate each RTT until BtlBW plateaus (3 rounds) |
| **Drain** | Drain queue built in Startup; pacing_gain = 1/2 |
| **ProbeBW** | Steady state — 8-RTT gain cycle `[1.25, 0.75, 1.0×6]` probes BW |
| **ProbeRTT** | Every ~24 RTTs, cwnd → 4 MSS for 2 RTTs to measure clean RTprop |

The plot overlays the **BDP estimate** (orange dashed) to show BBR learning
the network, and annotates the `×1.25` / `×0.75` pacing gain at probe rounds.
There is no sawtooth — cwnd hugs the BDP with ±25 % oscillation.

## Comparison at a glance

| Property | Reno | New Reno | Vegas | CUBIC | HSTCP | BBR |
|---|---|---|---|---|---|---|
| Growth | +1/RTT | +1/RTT | ±1 (diff) | Cubic | +a(w)/RTT | tracks BDP |
| Reacts to | Loss | Loss | RTT increase | Loss | Loss | **nothing** |
| Loss penalty | cwnd/2 | cwnd/2 | cwnd/2 | ×0.7 | ×(1−keep) | none |
| Sawtooth | Yes | Yes | No | Yes | Yes | No |
| High-BDP | Poor | Poor | Moderate | Excellent | Excellent | Excellent |

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
cd cubic      && python tcp_cubic.py
cd highspeed  && python tcp_highspeed.py
cd bbr        && python tcp_bbr.py
```

Each script prints a per-RTT table of `cwnd`, `ssthresh`, and phase, then
opens an interactive plot window and saves a PNG.

## Tuning

All key parameters are defined as module-level constants at the top of each
file — `INIT_CWND`, `INIT_SSTHRESH`, event RTTs, etc. — so they are easy to
adjust without reading the simulation logic.
