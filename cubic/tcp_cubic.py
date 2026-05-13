#!/usr/bin/env python3
"""
TCP CUBIC Congestion Window Simulation  —  RFC 9438

CUBIC replaces the linear Congestion Avoidance ramp with a cubic function of
*elapsed wall-clock time* since the last loss event:

  W_cubic(t) = C × (t − K)³ + W_max
  K          = ∛(W_max × β / C)

where W_max is the cwnd at which the last loss occurred, t is elapsed time in
*seconds* since the loss, and K is the time at which W_cubic returns to W_max
(the inflection point).

Unlike Reno (which adds 1 MSS per RTT), CUBIC's growth depends on real time,
not RTT count.  Two flows with different RTTs but the same bandwidth converge
to the same cwnd at the same wall-clock time, which makes CUBIC RTT-fair.

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
C       : cubic scaling constant (MSS/s³, RFC 9438 default = 0.4)
BETA    : reduction factor on loss (0.3 = 30% cut, vs Reno's 50%)
RTT_SEC : assumed fixed RTT in seconds (used to convert loop ticks to real time)
"""

import math
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ─── Simulation parameters ────────────────────────────────────────────────────
INIT_CWND     = 1      # MSS
INIT_SSTHRESH = 32     # MSS
C             = 4.0    # cubic scaling constant  (MSS / s³); RFC 9438 default is 0.4,
                       # scaled 10× here so the superlinear phase is visible in simulation
BETA          = 0.3    # multiplicative decrease  (30% cut on loss vs Reno's 50%)
RTT_SEC       = 0.1    # assumed RTT in seconds (100 ms)

FAST_RX_RTT   = 50     # RTT tick where 3 dup-ACKs trigger fast retransmit
RTO_RTT       = 100    # RTT tick where RTO fires
TOTAL_RTTS    = 130
# ─────────────────────────────────────────────────────────────────────────────

SLOW_START = "Slow Start"
CUBIC_CA   = "CUBIC Cong. Avoidance"


def cubic_K(w_max):
    """Seconds from post-loss cwnd back up to W_max (inflection point time)."""
    return (w_max * BETA / C) ** (1.0 / 3.0)


def w_cubic(t_epoch, w_max, k):
    """CUBIC window target at t_epoch seconds after the last loss."""
    return C * (t_epoch - k) ** 3 + w_max


def init_cubic_from_ss(cwnd):
    """
    Initialise CUBIC state when entering congestion avoidance from slow start.
    Uses a 'virtual prior loss' so that W_cubic(0) == cwnd, giving us
    the full S-curve (concave-down probe toward W_max, then past it).
    """
    vm = cwnd / (1.0 - BETA)   # virtual W_max such that W_cubic(0) = cwnd
    k  = cubic_K(vm)
    return vm, k, 0.0           # (w_max, K, t_epoch_seconds)


def simulate():
    cwnd     = float(INIT_CWND)
    ssthresh = float(INIT_SSTHRESH)
    state    = SLOW_START

    w_max, K, t_epoch = 0.0, 0.0, 0.0

    times, cwnds, ssthreshs, phases = [], [], [], []
    # event_rtts: time_sec -> (cwnd_at_event, annotation_text)
    event_rtts  = {}
    # inflections: time_sec -> (W_max value, annotation text)
    inflections = {}

    for t in range(TOTAL_RTTS):
        t_sec = t * RTT_SEC

        # Record state at start of this RTT
        times.append(t_sec)
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
            event_rtts[t_sec] = (cwnds[t], "Fast Retransmit\n(3 dup-ACKs)")
            t_infl = t_sec + K
            if t_infl < TOTAL_RTTS * RTT_SEC:
                inflections[t_infl] = (w_max, f"inflection\nW_max={w_max:.0f}")

        elif t == RTO_RTT:
            ssthresh = max(cwnd / 2.0, 2.0)
            cwnd     = float(INIT_CWND)
            state    = SLOW_START
            event_rtts[t_sec] = (cwnds[t], "RTO\n(Timeout)")

        # ── Normal per-RTT update ────────────────────────────────────────────
        else:
            if state == SLOW_START:
                cwnd = min(cwnd * 2.0, ssthresh)
                if cwnd >= ssthresh:
                    w_max, K, t_epoch = init_cubic_from_ss(cwnd)
                    state = CUBIC_CA
                    t_infl = t_sec + K
                    if t_infl < TOTAL_RTTS * RTT_SEC:
                        inflections[t_infl] = (w_max, f"inflection\nW_max={w_max:.0f}")

            elif state == CUBIC_CA:
                t_epoch += RTT_SEC
                target = w_cubic(t_epoch, w_max, K)
                # Take the max with Reno-like +1/RTT (TCP-friendliness guarantee)
                cwnd = max(target, cwnd + 1.0)

    return times, cwnds, ssthreshs, phases, event_rtts, inflections


def collect_phase_spans(times, phases):
    spans, start = [], 0
    for i in range(1, len(phases)):
        if phases[i] != phases[i - 1]:
            spans.append((times[start], times[i - 1] + RTT_SEC, phases[i - 1]))
            start = i
    spans.append((times[start], times[-1] + RTT_SEC, phases[-1]))
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
        FAST_RX_RTT * RTT_SEC: ( 0.2,  8),
        RTO_RTT     * RTT_SEC: ( 0.1, 10),
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
            xytext=(t_infl + 0.06, y_text),
            fontsize=8, color="green",
            arrowprops=dict(arrowstyle="->", color="green", lw=1.1),
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="green", alpha=0.85),
            zorder=6,
        )

    # Loss event markers
    for t_sec, (cwnd_val, label) in event_rtts.items():
        color = event_colors[label]
        ax.axvline(t_sec, color=color, linestyle=":", linewidth=1.8, zorder=2)
        dx, dy = annotation_offsets.get(t_sec, (0.1, 6))
        ax.annotate(
            label,
            xy=(t_sec, cwnd_val),
            xytext=(t_sec + dx, cwnd_val + dy),
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
        f"C = {C}  (cubic scaling, MSS/s³; RFC default 0.4, scaled 10× for visibility)\n"
        f"β = {BETA}  (30% reduction on loss vs Reno's 50%)\n"
        f"RTT = {RTT_SEC*1000:.0f} ms  (assumed fixed)\n"
        f"W_cubic(t) = C·(t−K)³ + W_max  [t in seconds]\n"
        f"Fast Retransmit @ t = {FAST_RX_RTT * RTT_SEC:.1f} s\n"
        f"RTO             @ t = {RTO_RTT     * RTT_SEC:.1f} s"
    )
    ax.text(0.99, 0.03, info, transform=ax.transAxes, fontsize=8,
            va="bottom", ha="right",
            bbox=dict(boxstyle="round", fc="lightyellow", ec="gray", alpha=0.85))

    ax.set_xlabel("Time (s)", fontsize=12)
    ax.set_ylabel("Congestion Window (MSS)", fontsize=12)
    ax.set_title(
        "TCP CUBIC — Congestion Window over Time\n"
        "Green dash-dot = inflection point (t=K, cwnd returns to W_max)",
        fontsize=13, fontweight="bold"
    )
    ax.set_xlim(0, (TOTAL_RTTS - 1) * RTT_SEC)
    ax.set_ylim(0, max(cwnds) * 1.25)
    ax.grid(True, linestyle="--", alpha=0.35)

    plt.tight_layout()
    out = "tcp_cubic_cwnd.png"
    plt.savefig(out, dpi=150)
    print(f"Saved: {out}")
    plt.show()


if __name__ == "__main__":
    times, cwnds, ssthreshs, phases, event_rtts, inflections = simulate()

    print(f"{'time(s)':>7}  {'cwnd':>7}  {'ssthresh':>8}  {'phase'}")
    print("-" * 55)
    for t, c, s, p in zip(times, cwnds, ssthreshs, phases):
        mark = ""
        if t in event_rtts:
            mark = " <-- " + event_rtts[t][1].replace("\n", " ")
        print(f"{t:>7.2f}  {c:>7.1f}  {s:>8.1f}  {p}{mark}")

    plot(times, cwnds, ssthreshs, phases, event_rtts, inflections)
