#!/usr/bin/env python3
"""
TCP Vegas Congestion Window Simulation

Vegas is a delay-based algorithm: it detects congestion early by measuring the
gap between expected and actual throughput (caused by RTT inflation), and backs
off *before* packets are lost. As a result, the cwnd curve is smooth rather than
sawtooth-shaped.

Core idea
---------
  diff = cwnd × (1/BaseRTT  −  1/ActualRTT)

  diff < α  →  increase cwnd by 1  (underutilised, more headroom)
  diff > β  →  decrease cwnd by 1  (queue building, back off)
  α ≤ diff ≤ β  →  no change       (operating in the sweet spot)

Network model
-------------
A simple linear queueing model is used:
  ActualRTT(cwnd) = BaseRTT × (1 + max(0, cwnd − CAPACITY) / CAPACITY)
This gives  diff = max(0, cwnd − CAPACITY)  (when BaseRTT = 1),
so the stable operating point is  CAPACITY + α  ≤ cwnd ≤  CAPACITY + β.

Slow Start in Vegas
-------------------
Vegas exits slow start as soon as ActualRTT > BaseRTT (queue starts building),
or when cwnd reaches ssthresh — whichever comes first.

Events shown
------------
1. Slow Start → Vegas transition (RTT-triggered exit from exponential growth)
2. Vegas steady state (gentle oscillation around CAPACITY + α..β)
3. Fast Retransmit (3 dup-ACKs): rare in Vegas, but shown for completeness
4. RTO (Timeout): resets cwnd = 1, triggers slow start

Parameters
----------
BASE_RTT    : minimum RTT, i.e. RTT with an empty queue (normalised to 1)
CAPACITY    : bottleneck bandwidth × BaseRTT  (MSS)  — BDP of the path
ALPHA, BETA : Vegas lower / upper diff thresholds (MSS)
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ─── Simulation parameters ────────────────────────────────────────────────────
INIT_CWND     = 1
INIT_SSTHRESH = 64   # high enough so Vegas RTT-exit fires before ssthresh
BASE_RTT      = 1.0  # normalised
CAPACITY      = 20   # MSS  (BDP of the bottleneck)
ALPHA         = 2.0  # Vegas lower threshold
BETA          = 4.0  # Vegas upper threshold

FAST_RX_RTT   = 28   # RTT where 3 dup-ACKs arrive (forced for demonstration)
RTO_RTT       = 50   # RTT where RTO fires
TOTAL_RTTS    = 70
# ─────────────────────────────────────────────────────────────────────────────

SLOW_START    = "Slow Start"
VEGAS         = "Vegas (Cong. Avoidance)"


def actual_rtt(cwnd):
    """Linear queueing delay model."""
    if cwnd <= CAPACITY:
        return BASE_RTT
    return BASE_RTT * (1.0 + (cwnd - CAPACITY) / CAPACITY)


def vegas_diff(cwnd):
    """Expected throughput − Actual throughput (MSS/RTT units)."""
    rtt = actual_rtt(cwnd)
    return cwnd * (1.0 / BASE_RTT - 1.0 / rtt)   # = max(0, cwnd − CAPACITY)


def simulate():
    cwnd     = float(INIT_CWND)
    ssthresh = float(INIT_SSTHRESH)
    state    = SLOW_START
    min_rtt  = actual_rtt(cwnd)   # tracks BaseRTT

    times, cwnds, ssthreshs, phases = [], [], [], []
    event_rtts = {}

    for t in range(TOTAL_RTTS):
        times.append(t)
        cwnds.append(cwnd)
        ssthreshs.append(ssthresh)
        phases.append(state)

        curr_rtt = actual_rtt(cwnd)
        min_rtt  = min(min_rtt, curr_rtt)

        # ── Loss events (forced) ─────────────────────────────────────────────
        if t == FAST_RX_RTT:
            # Fast retransmit: ssthresh = cwnd/2, cwnd = ssthresh
            # Vegas skips fast recovery and re-enters Vegas mode directly
            ssthresh = max(cwnd / 2.0, 2.0)
            cwnd     = ssthresh
            state    = VEGAS
            event_rtts[t] = "Fast Retransmit\n(3 dup-ACKs)"

        elif t == RTO_RTT:
            ssthresh = max(cwnd / 2.0, 2.0)
            cwnd     = float(INIT_CWND)
            state    = SLOW_START
            min_rtt  = BASE_RTT     # reset RTT baseline after RTO
            event_rtts[t] = "RTO\n(Timeout)"

        # ── Normal per-RTT update ────────────────────────────────────────────
        else:
            if state == SLOW_START:
                # Exit if RTT has started to rise (queue detected) or ssthresh hit
                if curr_rtt > min_rtt or cwnd >= ssthresh:
                    state = VEGAS
                    # fall through into Vegas logic this same RTT
                else:
                    cwnd = min(cwnd * 2.0, ssthresh)

            if state == VEGAS:
                diff = vegas_diff(cwnd)
                if diff < ALPHA:
                    cwnd += 1.0
                elif diff > BETA:
                    cwnd -= 1.0
                # else: no change (in the α–β sweet spot)

    return times, cwnds, ssthreshs, phases, event_rtts


def collect_phase_spans(times, phases):
    spans = []
    span_start = 0
    for i in range(1, len(phases)):
        if phases[i] != phases[i - 1]:
            spans.append((times[span_start], times[i - 1] + 1, phases[i - 1]))
            span_start = i
    spans.append((times[span_start], times[-1] + 1, phases[-1]))
    return spans


def plot(times, cwnds, ssthreshs, phases, event_rtts):
    phase_colors = {
        SLOW_START: "#cfe2ff",
        VEGAS:      "#d4edda",
    }
    event_colors = {
        "Fast Retransmit\n(3 dup-ACKs)": "#e07b00",
        "RTO\n(Timeout)":                "#cc0000",
    }
    annotation_offsets = {
        FAST_RX_RTT: ( 2,  5),
        RTO_RTT:     ( 2,  5),
    }

    fig, ax = plt.subplots(figsize=(16, 7))

    # Phase background shading
    for start, end, phase in collect_phase_spans(times, phases):
        ax.axvspan(start, end, alpha=0.25, color=phase_colors[phase], zorder=1)

    # Capacity reference line
    ax.axhline(y=CAPACITY, color="gray", linewidth=1.0, linestyle="-.",
               label=f"Bottleneck capacity ({CAPACITY} MSS)", zorder=2)

    # α / β stable-zone band
    ax.axhspan(CAPACITY + ALPHA, CAPACITY + BETA,
               alpha=0.15, color="green", zorder=1,
               label=f"Vegas stable zone (C+α … C+β = {CAPACITY+ALPHA:.0f}–{CAPACITY+BETA:.0f})")

    # ssthresh dashed line
    ax.step(times, ssthreshs, color="orangered", linewidth=1.4,
            linestyle="--", where="post", label="ssthresh (MSS)", zorder=3)

    # cwnd line
    ax.plot(times, cwnds, color="steelblue", linewidth=2.2,
            label="cwnd (MSS)", zorder=4)
    ax.scatter(times, cwnds, color="steelblue", s=18, zorder=5)

    # Event markers + annotations
    for rtt, label in event_rtts.items():
        color = event_colors[label]
        ax.axvline(x=rtt, color=color, linestyle=":", linewidth=1.8, zorder=2)
        dx, dy = annotation_offsets.get(rtt, (1, 5))
        ax.annotate(
            label,
            xy=(rtt, cwnds[rtt]),
            xytext=(rtt + dx, cwnds[rtt] + dy),
            fontsize=9, color=color, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=color, lw=1.4),
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=color, alpha=0.85),
            zorder=6,
        )

    # Legend
    ss_patch = mpatches.Patch(color=phase_colors[SLOW_START], alpha=0.6, label="Slow Start phase")
    vg_patch = mpatches.Patch(color=phase_colors[VEGAS],      alpha=0.6, label="Vegas phase")
    handles, _ = ax.get_legend_handles_labels()
    ax.legend(handles=handles + [ss_patch, vg_patch],
              loc="upper right", fontsize=9, framealpha=0.9)

    # Parameter info box
    info = (
        f"Init cwnd = {INIT_CWND} MSS\n"
        f"Init ssthresh = {INIT_SSTHRESH} MSS\n"
        f"Bottleneck capacity = {CAPACITY} MSS\n"
        f"Vegas α = {ALPHA:.0f},  β = {BETA:.0f}\n"
        f"Fast Retransmit @ RTT {FAST_RX_RTT}\n"
        f"RTO             @ RTT {RTO_RTT}"
    )
    ax.text(0.01, 0.97, info, transform=ax.transAxes, fontsize=8,
            verticalalignment="top", horizontalalignment="left",
            bbox=dict(boxstyle="round", fc="lightyellow", ec="gray", alpha=0.8))

    ax.set_xlabel("Time (RTT)", fontsize=12)
    ax.set_ylabel("Congestion Window (MSS)", fontsize=12)
    ax.set_title("TCP Vegas — Congestion Window over Time", fontsize=14, fontweight="bold")
    ax.set_xlim(0, TOTAL_RTTS - 1)
    ax.set_ylim(0, max(cwnds) * 1.2)
    ax.grid(True, linestyle="--", alpha=0.35)

    plt.tight_layout()
    out = "tcp_vegas_cwnd.png"
    plt.savefig(out, dpi=150)
    print(f"Saved: {out}")
    plt.show()


if __name__ == "__main__":
    times, cwnds, ssthreshs, phases, event_rtts = simulate()

    print(f"{'RTT':>4}  {'cwnd':>6}  {'ssthresh':>8}  {'diff':>6}  {'phase'}")
    print("-" * 60)
    for t, c, s, p in zip(times, cwnds, ssthreshs, phases):
        diff = vegas_diff(c)
        marker = ""
        if t in event_rtts:
            marker = " <-- " + event_rtts[t].replace("\n", " ")
        print(f"{t:>4}  {c:>6.1f}  {s:>8.1f}  {diff:>6.2f}  {p}{marker}")

    plot(times, cwnds, ssthreshs, phases, event_rtts)
