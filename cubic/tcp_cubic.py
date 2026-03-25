#!/usr/bin/env python3
"""
TCP CUBIC Congestion Window Simulation  —  RFC 9438

CUBIC replaces the linear Congestion Avoidance ramp with a cubic function of
time elapsed since the last loss event:

  W_cubic(t) = C × (t − K)³ + W_max
  K          = ∛(W_max × β / C)

where W_max is the cwnd at which the last loss occurred, t is the time (RTTs)
since the loss, and K is the time at which W_cubic returns to W_max (the
inflection point).

Shape of the S-curve
--------------------
  t < K  (left of inflection)  : concave-down  — fast initial probe toward W_max
  t = K                        : inflection    — cwnd = W_max again
  t > K  (right of inflection) : concave-up    — aggressive growth past W_max

This is more efficient than Reno's linear ramp on high-BDP paths because
CUBIC recovers lost throughput quickly after a loss event.

On loss
-------
  Fast Retransmit : W_max = cwnd,  cwnd = W_max × (1−β),  K recomputed
  RTO (Timeout)   : ssthresh = cwnd/2,  cwnd = 1  (same hard reset as Reno)

Parameters
----------
C       : cubic scaling constant (MSS/RTT³)
BETA    : reduction factor on loss (0.3 = 30% cut, vs Reno's 50%)
"""

import math
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ─── Simulation parameters ────────────────────────────────────────────────────
INIT_CWND     = 1      # MSS
INIT_SSTHRESH = 32     # MSS
C             = 0.015  # cubic scaling constant  (MSS / RTT³)
BETA          = 0.3    # multiplicative decrease  (30% cut on loss)

FAST_RX_RTT   = 22     # RTT where 3 dup-ACKs trigger fast retransmit
RTO_RTT       = 40     # RTT where RTO fires
TOTAL_RTTS    = 60
# ─────────────────────────────────────────────────────────────────────────────

SLOW_START = "Slow Start"
CUBIC_CA   = "CUBIC Cong. Avoidance"


def cubic_K(w_max):
    """RTTs from post-loss cwnd back up to W_max (inflection point time)."""
    return (w_max * BETA / C) ** (1.0 / 3.0)


def w_cubic(t_epoch, w_max, k):
    """CUBIC window target at t_epoch RTTs after the last loss."""
    return C * (t_epoch - k) ** 3 + w_max


def init_cubic_from_ss(cwnd):
    """
    Initialise CUBIC state when entering congestion avoidance from slow start.
    Uses a 'virtual prior loss' so that W_cubic(0) == cwnd, giving us
    the full S-curve (concave-down probe toward W_max, then past it).
    """
    vm = cwnd / (1.0 - BETA)   # virtual W_max such that W_cubic(0) = cwnd
    k  = cubic_K(vm)
    return vm, k, 0.0           # (w_max, K, t_epoch)


def simulate():
    cwnd     = float(INIT_CWND)
    ssthresh = float(INIT_SSTHRESH)
    state    = SLOW_START

    w_max, K, t_epoch = 0.0, 0.0, 0.0

    times, cwnds, ssthreshs, phases = [], [], [], []
    event_rtts      = {}
    inflections     = {}    # fractional RTT -> (W_max value, annotation text)

    for t in range(TOTAL_RTTS):
        # Record state at start of this RTT
        times.append(t)
        cwnds.append(cwnd)
        ssthreshs.append(ssthresh)
        phases.append(state)

        # ── Loss events ──────────────────────────────────────────────────────
        if t == FAST_RX_RTT:
            w_max    = cwnd
            ssthresh = max(cwnd * (1.0 - BETA), 2.0)
            cwnd     = ssthresh              # = W_max × (1−β)
            K        = cubic_K(w_max)
            t_epoch  = 0.0
            state    = CUBIC_CA
            event_rtts[t] = "Fast Retransmit\n(3 dup-ACKs)"
            t_infl = t + K
            if t_infl < TOTAL_RTTS:
                inflections[t_infl] = (w_max, f"inflection\nW_max={w_max:.0f}")

        elif t == RTO_RTT:
            ssthresh = max(cwnd / 2.0, 2.0)
            cwnd     = float(INIT_CWND)
            state    = SLOW_START
            event_rtts[t] = "RTO\n(Timeout)"

        # ── Normal per-RTT update ────────────────────────────────────────────
        else:
            if state == SLOW_START:
                cwnd = min(cwnd * 2.0, ssthresh)
                if cwnd >= ssthresh:
                    w_max, K, t_epoch = init_cubic_from_ss(cwnd)
                    state = CUBIC_CA
                    t_infl = t + K
                    if t_infl < TOTAL_RTTS:
                        inflections[t_infl] = (w_max, f"inflection\nW_max={w_max:.0f}")

            elif state == CUBIC_CA:
                t_epoch += 1.0
                target = w_cubic(t_epoch, w_max, K)
                # Take the max with Reno-like +1/RTT (TCP-friendliness)
                cwnd = max(target, cwnd + 1.0)

    return times, cwnds, ssthreshs, phases, event_rtts, inflections


def collect_phase_spans(times, phases):
    spans, start = [], 0
    for i in range(1, len(phases)):
        if phases[i] != phases[i - 1]:
            spans.append((times[start], times[i - 1] + 1, phases[i - 1]))
            start = i
    spans.append((times[start], times[-1] + 1, phases[-1]))
    return spans


def plot(times, cwnds, ssthreshs, phases, event_rtts, inflections):
    phase_colors = {
        SLOW_START: "#cfe2ff",
        CUBIC_CA:   "#d4edda",
    }
    event_colors = {
        "Fast Retransmit\n(3 dup-ACKs)": "#e07b00",
        "RTO\n(Timeout)":                "#cc0000",
    }
    annotation_offsets = {
        FAST_RX_RTT: ( 2,  8),
        RTO_RTT:     ( 1, 10),
    }

    fig, ax = plt.subplots(figsize=(15, 7))

    # Phase background shading
    for start, end, phase in collect_phase_spans(times, phases):
        ax.axvspan(start, end, alpha=0.22, color=phase_colors[phase], zorder=1)

    # ssthresh dashed line
    ax.step(times, ssthreshs, color="orangered", linewidth=1.4,
            linestyle="--", where="post", label="ssthresh (MSS)", zorder=3)

    # cwnd
    ax.plot(times, cwnds, color="steelblue", linewidth=2.2,
            label="cwnd (MSS)", zorder=4)
    ax.scatter(times, cwnds, color="steelblue", s=18, zorder=5)

    # Inflection point markers
    for t_infl, (wm, label) in inflections.items():
        ax.axvline(t_infl, color="green", linestyle="-.", linewidth=1.3,
                   alpha=0.75, zorder=2)
        ax.axhline(wm, color="green", linestyle=":", linewidth=0.9,
                   alpha=0.45, zorder=2)
        y_text = wm + max(cwnds) * 0.04
        ax.annotate(
            label,
            xy=(t_infl, wm),
            xytext=(t_infl + 0.6, y_text),
            fontsize=8, color="green",
            arrowprops=dict(arrowstyle="->", color="green", lw=1.1),
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="green", alpha=0.85),
            zorder=6,
        )

    # Loss event markers
    for rtt, label in event_rtts.items():
        color = event_colors[label]
        ax.axvline(rtt, color=color, linestyle=":", linewidth=1.8, zorder=2)
        dx, dy = annotation_offsets.get(rtt, (1, 6))
        ax.annotate(
            label,
            xy=(rtt, cwnds[rtt]),
            xytext=(rtt + dx, cwnds[rtt] + dy),
            fontsize=9, color=color, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=color, lw=1.4),
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=color, alpha=0.88),
            zorder=6,
        )

    # Legend
    ss_patch = mpatches.Patch(color=phase_colors[SLOW_START], alpha=0.6,
                               label="Slow Start phase")
    ca_patch = mpatches.Patch(color=phase_colors[CUBIC_CA],   alpha=0.6,
                               label="CUBIC Cong. Avoidance phase")
    handles, _ = ax.get_legend_handles_labels()
    ax.legend(handles=handles + [ss_patch, ca_patch],
              loc="upper left", fontsize=9, framealpha=0.9)

    # Parameter info box
    info = (
        f"Init cwnd = {INIT_CWND} MSS,  ssthresh = {INIT_SSTHRESH} MSS\n"
        f"C = {C}  (cubic scaling, MSS/RTT³)\n"
        f"β = {BETA}  (30% reduction on loss vs Reno's 50%)\n"
        f"W_cubic(t) = C·(t−K)³ + W_max\n"
        f"Fast Retransmit @ RTT {FAST_RX_RTT}\n"
        f"RTO             @ RTT {RTO_RTT}"
    )
    ax.text(0.99, 0.03, info, transform=ax.transAxes, fontsize=8,
            va="bottom", ha="right",
            bbox=dict(boxstyle="round", fc="lightyellow", ec="gray", alpha=0.85))

    ax.set_xlabel("Time (RTT)", fontsize=12)
    ax.set_ylabel("Congestion Window (MSS)", fontsize=12)
    ax.set_title(
        "TCP CUBIC — Congestion Window over Time\n"
        "Green dash-dot = inflection point (t=K, cwnd returns to W_max)",
        fontsize=13, fontweight="bold"
    )
    ax.set_xlim(0, TOTAL_RTTS - 1)
    ax.set_ylim(0, max(cwnds) * 1.25)
    ax.grid(True, linestyle="--", alpha=0.35)

    plt.tight_layout()
    out = "tcp_cubic_cwnd.png"
    plt.savefig(out, dpi=150)
    print(f"Saved: {out}")
    plt.show()


if __name__ == "__main__":
    times, cwnds, ssthreshs, phases, event_rtts, inflections = simulate()

    print(f"{'RTT':>4}  {'cwnd':>7}  {'ssthresh':>8}  {'phase'}")
    print("-" * 50)
    for t, c, s, p in zip(times, cwnds, ssthreshs, phases):
        mark = ""
        if t in event_rtts:
            mark = " <-- " + event_rtts[t].replace("\n", " ")
        print(f"{t:>4}  {c:>7.1f}  {s:>8.1f}  {p}{mark}")

    plot(times, cwnds, ssthreshs, phases, event_rtts, inflections)
