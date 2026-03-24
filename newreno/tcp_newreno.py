#!/usr/bin/env python3
"""
TCP New Reno Congestion Window Simulation

Key difference from TCP Reno: New Reno stays in Fast Recovery on a Partial ACK
(i.e. when only some of the lost packets have been recovered) and only exits
recovery when a Full ACK (covering all data sent before fast retransmit) arrives.

Phases shown
------------
- Slow Start            : cwnd doubles each RTT until ssthresh
- Congestion Avoidance  : cwnd grows +1 MSS/RTT
- Fast Recovery         : cwnd inflates +1/RTT per dup-ACK; on Partial ACK
                          deflates but stays in recovery; exits on Full ACK
- RTO (Timeout)         : ssthresh = cwnd/2, cwnd = 1, restart Slow Start

Parameters
----------
INIT_CWND        : initial congestion window (MSS)
INIT_SSTHRESH    : initial slow-start threshold (MSS)
FAST_RX_RTT      : RTT where 3 dup-ACKs trigger fast retransmit
PARTIAL_ACK_RTT  : RTT inside recovery where a Partial ACK arrives
FULL_ACK_RTT     : RTT where the Full ACK exits Fast Recovery
RTO_RTT          : RTT where an RTO fires
TOTAL_RTTS       : total simulation length
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ─── Simulation parameters ────────────────────────────────────────────────────
INIT_CWND       = 1    # MSS
INIT_SSTHRESH   = 32   # MSS
FAST_RX_RTT     = 18   # 3 dup-ACKs detected → fast retransmit
PARTIAL_ACK_RTT = 20   # Partial ACK during fast recovery (2nd loss still pending)
FULL_ACK_RTT    = 22   # Full ACK → exit fast recovery
RTO_RTT         = 38   # Timeout
TOTAL_RTTS      = 56
# ─────────────────────────────────────────────────────────────────────────────

SLOW_START    = "Slow Start"
CONG_AVOID    = "Congestion Avoidance"
FAST_RECOVERY = "Fast Recovery"


def simulate():
    cwnd     = float(INIT_CWND)
    ssthresh = float(INIT_SSTHRESH)
    state    = SLOW_START

    times, cwnds, ssthreshs, phases = [], [], [], []
    event_rtts = {}  # rtt -> (label, note)

    for t in range(TOTAL_RTTS):
        # Record state at the START of this RTT (before any event)
        times.append(t)
        cwnds.append(cwnd)
        ssthreshs.append(ssthresh)
        phases.append(state)

        # ── Loss / recovery events ───────────────────────────────────────────
        if t == FAST_RX_RTT:
            # Fast retransmit: ssthresh = cwnd/2, cwnd = ssthresh + 3 (RFC 3782)
            ssthresh = max(cwnd / 2.0, 2.0)
            cwnd     = ssthresh + 3.0   # inflate window by 3 dup-ACKs
            state    = FAST_RECOVERY
            event_rtts[t] = "Fast Retransmit\n(3 dup-ACKs)"

        elif t == PARTIAL_ACK_RTT and state == FAST_RECOVERY:
            # Partial ACK: some losses still pending — stay in Fast Recovery
            # Retransmit next missing segment; deflate cwnd
            cwnd = ssthresh + 1.0       # rough RTT-level model of partial deflation
            # state stays FAST_RECOVERY
            event_rtts[t] = "Partial ACK\n(retransmit next missing)"

        elif t == FULL_ACK_RTT and state == FAST_RECOVERY:
            # Full ACK: all data sent before fast retransmit is now acknowledged
            cwnd  = ssthresh            # deflate to ssthresh
            state = CONG_AVOID
            event_rtts[t] = "Full ACK\n(exit Fast Recovery)"

        elif t == RTO_RTT:
            # Timeout: ssthresh = cwnd/2, cwnd = 1, restart slow start
            ssthresh = max(cwnd / 2.0, 2.0)
            cwnd     = float(INIT_CWND)
            state    = SLOW_START
            event_rtts[t] = "RTO\n(Timeout)"

        # ── Normal per-RTT update ────────────────────────────────────────────
        else:
            if state == SLOW_START:
                cwnd = min(cwnd * 2.0, ssthresh)
                if cwnd >= ssthresh:
                    state = CONG_AVOID
            elif state == CONG_AVOID:
                cwnd += 1.0
            elif state == FAST_RECOVERY:
                cwnd += 1.0             # inflate: one more dup-ACK per RTT

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
        SLOW_START:    "#cfe2ff",
        CONG_AVOID:    "#d4edda",
        FAST_RECOVERY: "#fff3cd",
    }
    event_colors = {
        "Fast Retransmit\n(3 dup-ACKs)":          "#e07b00",
        "Partial ACK\n(retransmit next missing)":  "#8b44ac",
        "Full ACK\n(exit Fast Recovery)":          "#1a7a4a",
        "RTO\n(Timeout)":                          "#cc0000",
    }
    # (dx, dy) offset for annotation text relative to event point
    annotation_offsets = {
        FAST_RX_RTT:     ( 2,  8),
        PARTIAL_ACK_RTT: ( 2, -10),
        FULL_ACK_RTT:    ( 2,  8),
        RTO_RTT:         ( 2, 10),
    }

    fig, ax = plt.subplots(figsize=(16, 7))

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
    phase_patches = [
        mpatches.Patch(color=phase_colors[p], alpha=0.6, label=f"{p} phase")
        for p in [SLOW_START, CONG_AVOID, FAST_RECOVERY]
    ]
    handles, _ = ax.get_legend_handles_labels()
    ax.legend(handles=handles + phase_patches,
              loc="upper left", fontsize=9, framealpha=0.9)

    # Parameter info box
    info = (
        f"Init cwnd = {INIT_CWND} MSS\n"
        f"Init ssthresh = {INIT_SSTHRESH} MSS\n"
        f"Fast Retransmit @ RTT {FAST_RX_RTT}\n"
        f"Partial ACK     @ RTT {PARTIAL_ACK_RTT}\n"
        f"Full ACK        @ RTT {FULL_ACK_RTT}\n"
        f"RTO             @ RTT {RTO_RTT}"
    )
    ax.text(0.98, 0.97, info, transform=ax.transAxes, fontsize=8,
            verticalalignment="top", horizontalalignment="right",
            bbox=dict(boxstyle="round", fc="lightyellow", ec="gray", alpha=0.8))

    ax.set_xlabel("Time (RTT)", fontsize=12)
    ax.set_ylabel("Congestion Window (MSS)", fontsize=12)
    ax.set_title("TCP New Reno — Congestion Window over Time", fontsize=14, fontweight="bold")
    ax.set_xlim(0, TOTAL_RTTS - 1)
    ax.set_ylim(0, max(cwnds) * 1.25)
    ax.grid(True, linestyle="--", alpha=0.35)

    plt.tight_layout()
    out = "tcp_newreno_cwnd.png"
    plt.savefig(out, dpi=150)
    print(f"Saved: {out}")
    plt.show()


if __name__ == "__main__":
    times, cwnds, ssthreshs, phases, event_rtts = simulate()

    print(f"{'RTT':>4}  {'cwnd':>6}  {'ssthresh':>8}  {'phase'}")
    print("-" * 55)
    for t, c, s, p in zip(times, cwnds, ssthreshs, phases):
        marker = ""
        if t in event_rtts:
            marker = " <-- " + event_rtts[t].replace("\n", " ")
        print(f"{t:>4}  {c:>6.1f}  {s:>8.1f}  {p}{marker}")

    plot(times, cwnds, ssthreshs, phases, event_rtts)
