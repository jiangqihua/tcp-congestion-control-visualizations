#!/usr/bin/env python3
"""
TCP HighSpeed (HSTCP) Congestion Window Simulation  —  RFC 3649

Problem with standard TCP on high-BDP paths
--------------------------------------------
Reno's Congestion Avoidance adds exactly +1 MSS per RTT regardless of cwnd.
At a 10 Gbps link with 100 ms RTT (BDP ≈ 125,000 MSS), recovering from a
single loss event would take ~125,000 RTTs — minutes of underutilisation.

HSTCP fix: state-dependent AIMD
---------------------------------
HSTCP uses two cwnd-dependent parameters:

  a(w)  — additive increase per RTT   (grows with cwnd: faster ramp-up)
  b(w)  — fraction of cwnd *kept* on loss  (grows with cwnd: softer cut)

Below LOW_WINDOW the parameters equal standard Reno (a=1, b=0.5).
Above LOW_WINDOW they are log-interpolated toward the high-window limits:

  cwnd ≤ LOW_WINDOW  :  a = A_LOW  = 1,    b = KEEP_LOW  = 0.50 (Reno)
  cwnd ≥ HIGH_WINDOW :  a = A_HIGH = 12,   b = KEEP_HIGH = 0.85 (15% cut)

  On fast retransmit  :  ssthresh = cwnd × b(cwnd),  cwnd = ssthresh
  On RTO              :  ssthresh = cwnd / 2,          cwnd = 1  (same as Reno)

The result: at large windows cwnd climbs ~10× faster than Reno and loses
only ~15% on loss instead of 50%, recovering throughput far more quickly.

Parameters
----------
LOW_WINDOW, HIGH_WINDOW : cwnd range over which a/b are interpolated (MSS)
A_LOW, A_HIGH           : additive-increase range
KEEP_LOW, KEEP_HIGH     : multiplicative-keep range on loss
"""

import math
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ─── Simulation parameters ────────────────────────────────────────────────────
INIT_CWND     = 1
INIT_SSTHRESH = 32   # MSS

LOW_WINDOW    = 10   # MSS – below this: standard Reno behaviour
HIGH_WINDOW   = 200  # MSS – above this: fully HSTCP

A_LOW         = 1.0   # additive increase at LOW_WINDOW  (= Reno)
A_HIGH        = 12.0  # additive increase at HIGH_WINDOW

KEEP_LOW      = 0.50  # fraction of cwnd kept on loss at LOW_WINDOW  (= Reno: halve)
KEEP_HIGH     = 0.85  # fraction of cwnd kept on loss at HIGH_WINDOW (only 15% cut)

FAST_RX_RTT   = 15
RTO_RTT       = 28
TOTAL_RTTS    = 48
# ─────────────────────────────────────────────────────────────────────────────

SLOW_START = "Slow Start"
HSTCP_CA   = "HSTCP Cong. Avoidance"


def _frac(cwnd):
    """Log-linear interpolation fraction in [0, 1] between LOW and HIGH window."""
    if cwnd <= LOW_WINDOW:
        return 0.0
    if cwnd >= HIGH_WINDOW:
        return 1.0
    return math.log(cwnd / LOW_WINDOW) / math.log(HIGH_WINDOW / LOW_WINDOW)


def hstcp_a(cwnd):
    """Additive increase parameter a(w)."""
    return A_LOW + _frac(cwnd) * (A_HIGH - A_LOW)


def hstcp_keep(cwnd):
    """Fraction of cwnd retained on a loss event — b(w) in HSTCP terms."""
    return KEEP_LOW + _frac(cwnd) * (KEEP_HIGH - KEEP_LOW)


def simulate():
    cwnd     = float(INIT_CWND)
    ssthresh = float(INIT_SSTHRESH)
    state    = SLOW_START

    times, cwnds, ssthreshs, phases = [], [], [], []
    event_rtts = {}

    for t in range(TOTAL_RTTS):
        times.append(t)
        cwnds.append(cwnd)
        ssthreshs.append(ssthresh)
        phases.append(state)

        # ── Loss events ──────────────────────────────────────────────────────
        if t == FAST_RX_RTT:
            keep      = hstcp_keep(cwnd)
            ssthresh  = max(cwnd * keep, 2.0)
            cwnd      = ssthresh
            state     = HSTCP_CA
            event_rtts[t] = f"Fast Retransmit\n(keep {keep:.0%} vs Reno 50%)"

        elif t == RTO_RTT:
            ssthresh  = max(cwnd / 2.0, 2.0)
            cwnd      = float(INIT_CWND)
            state     = SLOW_START
            event_rtts[t] = "RTO\n(Timeout)"

        # ── Normal per-RTT update ────────────────────────────────────────────
        else:
            if state == SLOW_START:
                cwnd = min(cwnd * 2.0, ssthresh)
                if cwnd >= ssthresh:
                    state = HSTCP_CA
            else:
                cwnd += hstcp_a(cwnd)   # HSTCP: increase by a(w) instead of 1

    return times, cwnds, ssthreshs, phases, event_rtts


def collect_phase_spans(times, phases):
    spans = []
    start = 0
    for i in range(1, len(phases)):
        if phases[i] != phases[i - 1]:
            spans.append((times[start], times[i - 1] + 1, phases[i - 1]))
            start = i
    spans.append((times[start], times[-1] + 1, phases[-1]))
    return spans


def plot(times, cwnds, ssthreshs, phases, event_rtts):
    phase_colors = {
        SLOW_START: "#cfe2ff",
        HSTCP_CA:   "#d4edda",
    }
    event_colors = {
        event_rtts.get(FAST_RX_RTT, ""): "#e07b00",
        "RTO\n(Timeout)":                "#cc0000",
    }
    # rebuild with actual label strings
    ec = {"RTO\n(Timeout)": "#cc0000"}
    for label in event_rtts.values():
        if "Fast Retransmit" in label:
            ec[label] = "#e07b00"

    annotation_offsets = {
        FAST_RX_RTT: ( 2,  12),
        RTO_RTT:     ( 1,  15),
    }

    fig, ax = plt.subplots(figsize=(15, 7))

    # Reno reference: dashed grey line showing what Reno cwnd would look like
    # (simple Reno: +1/RTT in CA, halve on loss – approximate, same events)
    r_cwnd, r_ssthresh = float(INIT_CWND), float(INIT_SSTHRESH)
    r_state = SLOW_START
    reno_cwnds = []
    for t in range(TOTAL_RTTS):
        reno_cwnds.append(r_cwnd)
        if t == FAST_RX_RTT:
            r_ssthresh = max(r_cwnd / 2.0, 2.0)
            r_cwnd     = r_ssthresh
            r_state    = HSTCP_CA
        elif t == RTO_RTT:
            r_ssthresh = max(r_cwnd / 2.0, 2.0)
            r_cwnd     = float(INIT_CWND)
            r_state    = SLOW_START
        else:
            if r_state == SLOW_START:
                r_cwnd = min(r_cwnd * 2.0, r_ssthresh)
                if r_cwnd >= r_ssthresh:
                    r_state = HSTCP_CA
            else:
                r_cwnd += 1.0

    ax.plot(times, reno_cwnds, color="gray", linewidth=1.4, linestyle="--",
            alpha=0.6, label="TCP Reno cwnd (reference)", zorder=3)

    # Phase shading
    for start, end, phase in collect_phase_spans(times, phases):
        ax.axvspan(start, end, alpha=0.2, color=phase_colors[phase], zorder=1)

    # ssthresh
    ax.step(times, ssthreshs, color="orangered", linewidth=1.4,
            linestyle=":", where="post", label="ssthresh (MSS)", zorder=3)

    # HSTCP cwnd
    ax.plot(times, cwnds, color="steelblue", linewidth=2.3,
            label="HSTCP cwnd (MSS)", zorder=4)
    ax.scatter(times, cwnds, color="steelblue", s=18, zorder=5)

    # a(w) annotations along the HSTCP line
    for t in range(0, TOTAL_RTTS, 4):
        if phases[t] == HSTCP_CA and t not in event_rtts:
            a = hstcp_a(cwnds[t])
            if a > 1.5:
                ax.text(t, cwnds[t] + 2, f"a={a:.1f}", fontsize=6.5,
                        color="steelblue", ha="center", va="bottom", alpha=0.75)

    # Event markers
    for rtt, label in event_rtts.items():
        color = ec.get(label, "#555")
        ax.axvline(x=rtt, color=color, linestyle=":", linewidth=1.8, zorder=2)
        dx, dy = annotation_offsets.get(rtt, (1, 8))
        ax.annotate(
            label,
            xy=(rtt, cwnds[rtt]),
            xytext=(rtt + dx, cwnds[rtt] + dy),
            fontsize=9, color=color, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=color, lw=1.4),
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=color, alpha=0.9),
            zorder=6,
        )

    # Legend
    ss_patch = mpatches.Patch(color=phase_colors[SLOW_START], alpha=0.5, label="Slow Start phase")
    ca_patch = mpatches.Patch(color=phase_colors[HSTCP_CA],   alpha=0.5, label="HSTCP CA phase")
    handles, _ = ax.get_legend_handles_labels()
    ax.legend(handles=handles + [ss_patch, ca_patch],
              loc="upper left", fontsize=9, framealpha=0.9)

    # Parameter box
    info = (
        f"Init cwnd = {INIT_CWND} MSS,  ssthresh = {INIT_SSTHRESH} MSS\n"
        f"Low window = {LOW_WINDOW} MSS  →  a={A_LOW:.0f}, keep={KEEP_LOW:.0%}\n"
        f"High window = {HIGH_WINDOW} MSS →  a={A_HIGH:.0f}, keep={KEEP_HIGH:.0%}\n"
        f"Fast Retransmit @ RTT {FAST_RX_RTT}\n"
        f"RTO             @ RTT {RTO_RTT}"
    )
    ax.text(0.99, 0.97, info, transform=ax.transAxes, fontsize=8,
            va="top", ha="right",
            bbox=dict(boxstyle="round", fc="lightyellow", ec="gray", alpha=0.85))

    ax.set_xlabel("Time (RTT)", fontsize=12)
    ax.set_ylabel("Congestion Window (MSS)", fontsize=12)
    ax.set_title("TCP HighSpeed (HSTCP) — Congestion Window over Time\n"
                 "(dashed grey = TCP Reno reference with identical loss events)",
                 fontsize=13, fontweight="bold")
    ax.set_xlim(0, TOTAL_RTTS - 1)
    ax.set_ylim(0, max(cwnds) * 1.2)
    ax.grid(True, linestyle="--", alpha=0.35)

    plt.tight_layout()
    out = "tcp_highspeed_cwnd.png"
    plt.savefig(out, dpi=150)
    print(f"Saved: {out}")
    plt.show()


if __name__ == "__main__":
    times, cwnds, ssthreshs, phases, event_rtts = simulate()

    print(f"{'RTT':>4}  {'cwnd':>7}  {'ssthresh':>8}  {'a(w)':>6}  {'keep':>6}  {'phase'}")
    print("-" * 65)
    for t, c, s, p in zip(times, cwnds, ssthreshs, phases):
        a    = hstcp_a(c)
        keep = hstcp_keep(c)
        mark = ""
        if t in event_rtts:
            mark = " <-- " + event_rtts[t].replace("\n", " ")
        print(f"{t:>4}  {c:>7.1f}  {s:>8.1f}  {a:>6.2f}  {keep:>5.0%}  {p}{mark}")

    plot(times, cwnds, ssthreshs, phases, event_rtts)
