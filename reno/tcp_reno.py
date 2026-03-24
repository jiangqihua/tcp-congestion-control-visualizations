#!/usr/bin/env python3
"""
TCP Reno Congestion Window Simulation

Simulates and plots cwnd over time (in RTTs), covering:
  - Slow Start (exponential growth)
  - Congestion Avoidance (linear growth)
  - Fast Retransmit / Fast Recovery (3 dup-ACKs)
  - RTO (timeout → reset to slow start)

Parameters
----------
INIT_CWND      : initial congestion window (MSS)
INIT_SSTHRESH  : initial slow-start threshold (MSS)
FAST_RX_RTT    : RTT at which 3 dup-ACKs are detected
RTO_RTT        : RTT at which an RTO fires
TOTAL_RTTS     : total simulation length
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ─── Simulation parameters ────────────────────────────────────────────────────
INIT_CWND     = 1    # MSS
INIT_SSTHRESH = 32   # MSS
FAST_RX_RTT   = 18   # RTT index where fast retransmit is triggered
RTO_RTT       = 35   # RTT index where RTO fires
TOTAL_RTTS    = 52
# ─────────────────────────────────────────────────────────────────────────────


def simulate():
    cwnd     = float(INIT_CWND)
    ssthresh = float(INIT_SSTHRESH)

    times, cwnds, ssthreshs, phases = [], [], [], []
    event_rtts = {}  # rtt_index -> label string

    for t in range(TOTAL_RTTS):
        times.append(t)
        cwnds.append(cwnd)
        ssthreshs.append(ssthresh)
        phases.append("Slow Start" if cwnd < ssthresh else "Congestion Avoidance")

        # ── Loss events ──────────────────────────────────────────────────────
        if t == FAST_RX_RTT:
            # TCP Reno fast retransmit: ssthresh = cwnd/2, cwnd = ssthresh
            ssthresh = max(cwnd / 2.0, 2.0)
            cwnd     = ssthresh          # enter congestion avoidance immediately
            event_rtts[t] = "Fast Retransmit\n(3 dup-ACKs)"

        elif t == RTO_RTT:
            # Timeout: ssthresh = cwnd/2, cwnd = 1 (restart slow start)
            ssthresh = max(cwnd / 2.0, 2.0)
            cwnd     = float(INIT_CWND)
            event_rtts[t] = "RTO\n(Timeout)"

        # ── Normal per-RTT update ────────────────────────────────────────────
        else:
            if cwnd < ssthresh:
                cwnd = min(cwnd * 2.0, ssthresh)   # slow start: exponential
            else:
                cwnd += 1.0                         # cong. avoidance: +1 MSS/RTT

    return times, cwnds, ssthreshs, phases, event_rtts


def collect_phase_spans(times, phases):
    """Return list of (start, end, phase_label) for contiguous phase runs."""
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
        "Slow Start":            "#cfe2ff",
        "Congestion Avoidance":  "#d4edda",
    }
    event_colors = {
        "Fast Retransmit\n(3 dup-ACKs)": "#e07b00",
        "RTO\n(Timeout)":                "#cc0000",
    }
    annotation_offsets = {
        FAST_RX_RTT: (2,  8),
        RTO_RTT:     (2, 10),
    }

    fig, ax = plt.subplots(figsize=(15, 7))

    # Phase background shading
    for start, end, phase in collect_phase_spans(times, phases):
        ax.axvspan(start, end, alpha=0.25, color=phase_colors[phase], zorder=1)

    # ssthresh dashed line
    ax.step(times, ssthreshs, color="orangered", linewidth=1.4,
            linestyle="--", where="post", label="ssthresh (MSS)", zorder=3)

    # cwnd line
    ax.plot(times, cwnds, color="steelblue", linewidth=2.2,
            label="cwnd (MSS)", zorder=4)
    ax.scatter(times, cwnds, color="steelblue", s=18, zorder=5)

    # Event vertical lines + annotations
    for rtt, label in event_rtts.items():
        color = event_colors[label]
        ax.axvline(x=rtt, color=color, linestyle=":", linewidth=1.8, zorder=2)
        dx, dy = annotation_offsets.get(rtt, (1, 6))
        ax.annotate(
            label,
            xy=(rtt, cwnds[rtt]),
            xytext=(rtt + dx, cwnds[rtt] + dy),
            fontsize=9,
            color=color,
            fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=color, lw=1.4),
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=color, alpha=0.85),
            zorder=6,
        )

    # Legend
    ss_patch = mpatches.Patch(color=phase_colors["Slow Start"],
                               alpha=0.6, label="Slow Start phase")
    ca_patch = mpatches.Patch(color=phase_colors["Congestion Avoidance"],
                               alpha=0.6, label="Congestion Avoidance phase")
    handles, _ = ax.get_legend_handles_labels()
    ax.legend(handles=handles + [ss_patch, ca_patch],
              loc="upper left", fontsize=9, framealpha=0.9)

    # Parameter info box
    info = (
        f"Init cwnd = {INIT_CWND} MSS\n"
        f"Init ssthresh = {INIT_SSTHRESH} MSS\n"
        f"Fast Retransmit @ RTT {FAST_RX_RTT}\n"
        f"RTO @ RTT {RTO_RTT}"
    )
    ax.text(0.98, 0.97, info, transform=ax.transAxes, fontsize=8,
            verticalalignment="top", horizontalalignment="right",
            bbox=dict(boxstyle="round", fc="lightyellow", ec="gray", alpha=0.8))

    ax.set_xlabel("Time (RTT)", fontsize=12)
    ax.set_ylabel("Congestion Window (MSS)", fontsize=12)
    ax.set_title("TCP Reno — Congestion Window over Time", fontsize=14, fontweight="bold")
    ax.set_xlim(0, TOTAL_RTTS - 1)
    ax.set_ylim(0, max(cwnds) * 1.25)
    ax.grid(True, linestyle="--", alpha=0.35)

    plt.tight_layout()
    out = "tcp_reno_cwnd.png"
    plt.savefig(out, dpi=150)
    print(f"Saved: {out}")
    plt.show()


if __name__ == "__main__":
    times, cwnds, ssthreshs, phases, event_rtts = simulate()

    # Print a summary table
    print(f"{'RTT':>4}  {'cwnd':>6}  {'ssthresh':>8}  {'phase'}")
    print("-" * 42)
    for t, c, s, p in zip(times, cwnds, ssthreshs, phases):
        marker = " <-- " + event_rtts[t].replace("\n", " ") if t in event_rtts else ""
        print(f"{t:>4}  {c:>6.1f}  {s:>8.1f}  {p}{marker}")

    plot(times, cwnds, ssthreshs, phases, event_rtts)
