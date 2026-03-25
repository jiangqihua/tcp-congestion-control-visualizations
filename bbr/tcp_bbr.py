#!/usr/bin/env python3
"""
TCP BBR Congestion Window Simulation  —  Google 2016

BBR is fundamentally different from all loss-based algorithms (Reno, CUBIC,
HSTCP).  Instead of reacting to packet loss, BBR continuously estimates two
ground-truth network parameters:

  BtlBW   — bottleneck bandwidth   (windowed max of delivery rate)
  RTprop  — propagation delay RTT  (windowed min of RTT measurements)

and sets cwnd so that inflight ≈ BDP = BtlBW × RTprop — just enough data to
keep the pipe full without building a standing queue.

BBR State Machine
-----------------
  STARTUP    Double pacing rate each RTT until BtlBW estimate stops growing
             (< 25 % gain for 3 consecutive rounds).  Equivalent to slow start
             but exits on BW plateau, not packet loss.
  DRAIN      Drain the queue built during STARTUP.  pacing_gain = 1/startup_gain.
             Lasts only a few RTTs until inflight ≤ BDP.
  PROBE_BW   Steady state.  Cycles through an 8-RTT pacing-gain schedule:
               [1.25, 0.75, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
             The 1.25 round probes for more bandwidth; 0.75 drains the probe
             queue; 1.0 cruises at the estimated BDP.
  PROBE_RTT  Every PROBE_RTT_INTERVAL RTTs, BBR drops cwnd to a minimum (4 MSS)
             for PROBE_RTT_DURATION RTTs to let the queue drain and get a clean
             RTprop measurement.  Then returns to PROBE_BW.

Key difference from loss-based algorithms
------------------------------------------
BBR does NOT react to packet loss as a congestion signal.  Loss is treated as
noise.  cwnd is set by the BtlBW × RTprop model.  As a result:
  • No sawtooth pattern — cwnd stays near BDP in steady state.
  • Gentle ±25 % oscillation during PROBE_BW cycles.
  • Sharp periodic dips during PROBE_RTT (2 RTTs every ~24 RTTs).

Network model (simplified, RTT-granularity)
-------------------------------------------
  inflight ≤ BDP  →  delivered = inflight,  RTT = RTprop_true   (no queue)
  inflight > BDP  →  delivered = BtlBW,     RTT = RTprop + (inflight−BDP)/BtlBW

Parameters
----------
BtlBW_TRUE, RTprop_TRUE : ground truth (unknown to BBR, derived from measurements)
BW_FILTER_LEN           : window length for windowed-max BtlBW estimate
PROBE_RTT_INTERVAL      : PROBE_BW RTTs between PROBE_RTT events
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from collections import deque

# ─── Ground-truth network (hidden from the algorithm) ────────────────────────
BtlBW_TRUE  = 20.0   # MSS/RTT  — true bottleneck bandwidth
RTprop_TRUE = 1.0    # RTT (normalised)  — true min propagation delay
BDP         = BtlBW_TRUE * RTprop_TRUE    # = 20 MSS
BUFFER      = 20     # MSS of extra buffer above BDP

# ─── BBR algorithm parameters ────────────────────────────────────────────────
STARTUP_GAIN            = 2.0
DRAIN_GAIN              = 1.0 / STARTUP_GAIN       # = 0.5
PROBE_BW_GAIN_CYCLE     = [1.25, 0.75, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
PROBE_RTT_CWND          = 4      # MSS  — minimum window in PROBE_RTT
PROBE_RTT_INTERVAL      = 24     # PROBE_BW RTTs between PROBE_RTT events
PROBE_RTT_DURATION      = 2      # RTTs spent in PROBE_RTT
BW_FILTER_LEN           = 10     # rounds in windowed-max BtlBW filter
STARTUP_PLATEAU_ROUNDS  = 3      # non-growth rounds before leaving STARTUP

# ─── Simulation ──────────────────────────────────────────────────────────────
TOTAL_RTTS = 70

# ─── State labels ────────────────────────────────────────────────────────────
STARTUP   = "Startup"
DRAIN     = "Drain"
PROBE_BW  = "ProbeBW"
PROBE_RTT_STATE = "ProbeRTT"


def simulate():
    cwnd      = 1.0
    state     = STARTUP

    btlbw_est = 1.0
    rtprop_est = RTprop_TRUE
    bw_samples = deque(maxlen=BW_FILTER_LEN)

    plateau_count = 0
    prev_bw_est   = 0.0

    cycle_idx        = 0
    probe_rtt_timer  = PROBE_RTT_INTERVAL   # counts down PROBE_BW RTTs
    probe_rtt_elapsed = 0

    times, cwnds, states_rec, bdp_ests = [], [], [], []

    for t in range(TOTAL_RTTS):
        # ── Record state at start of RTT ─────────────────────────────────────
        times.append(t)
        cwnds.append(cwnd)
        states_rec.append(state)

        # ── Network measurement ───────────────────────────────────────────────
        inflight = cwnd
        if inflight <= BDP:
            delivered = inflight
            rtt = RTprop_TRUE
        else:
            queue     = min(inflight - BDP, BUFFER)
            delivered = BtlBW_TRUE
            rtt       = RTprop_TRUE + queue / BtlBW_TRUE

        dr = delivered / rtt
        bw_samples.append(dr)
        btlbw_est  = max(bw_samples)
        rtprop_est = min(rtprop_est, rtt)
        bdp_est    = btlbw_est * rtprop_est
        bdp_ests.append(bdp_est)

        # ── State machine: compute cwnd for RTT t+1 ──────────────────────────
        if state == STARTUP:
            growth = btlbw_est > 1.25 * prev_bw_est
            plateau_count = 0 if growth else plateau_count + 1
            prev_bw_est = max(prev_bw_est, btlbw_est)

            if plateau_count >= STARTUP_PLATEAU_ROUNDS:
                state = DRAIN
                cwnd  = bdp_est
            else:
                cwnd = STARTUP_GAIN * bdp_est

        elif state == DRAIN:
            cwnd = bdp_est
            if inflight <= bdp_est + 1:   # queue drained
                state           = PROBE_BW
                cycle_idx       = 0
                probe_rtt_timer = PROBE_RTT_INTERVAL
                gain  = PROBE_BW_GAIN_CYCLE[cycle_idx]
                cwnd  = gain * bdp_est
                cycle_idx += 1

        elif state == PROBE_BW:
            probe_rtt_timer -= 1
            if probe_rtt_timer <= 0:
                state             = PROBE_RTT_STATE
                probe_rtt_elapsed = 0
                cwnd              = float(PROBE_RTT_CWND)
            else:
                gain  = PROBE_BW_GAIN_CYCLE[cycle_idx % len(PROBE_BW_GAIN_CYCLE)]
                cwnd  = max(gain * bdp_est, float(PROBE_RTT_CWND))
                cycle_idx += 1

        elif state == PROBE_RTT_STATE:
            cwnd              = float(PROBE_RTT_CWND)
            rtprop_est        = min(rtprop_est, rtt)   # fresh RTprop sample
            probe_rtt_elapsed += 1
            if probe_rtt_elapsed >= PROBE_RTT_DURATION:
                state           = PROBE_BW
                cycle_idx       = 0
                probe_rtt_timer = PROBE_RTT_INTERVAL
                gain  = PROBE_BW_GAIN_CYCLE[cycle_idx]
                cwnd  = gain * bdp_est
                cycle_idx += 1

    return times, cwnds, states_rec, bdp_ests


# ── Helpers ───────────────────────────────────────────────────────────────────

def collect_phase_spans(times, states):
    spans, start = [], 0
    for i in range(1, len(states)):
        if states[i] != states[i - 1]:
            spans.append((times[start], times[i - 1] + 1, states[i - 1]))
            start = i
    spans.append((times[start], times[-1] + 1, states[-1]))
    return spans


def find_transitions(states):
    """Return {rtt: new_state} for every state change."""
    transitions = {}
    for i in range(1, len(states)):
        if states[i] != states[i - 1]:
            transitions[i] = states[i]
    return transitions


# ── Plot ──────────────────────────────────────────────────────────────────────

def plot(times, cwnds, states, bdp_ests):
    phase_colors = {
        STARTUP:         "#cfe2ff",
        DRAIN:           "#e2d9f3",
        PROBE_BW:        "#d4edda",
        PROBE_RTT_STATE: "#fff3cd",
    }
    transition_colors = {
        DRAIN:           "#8b44ac",
        PROBE_BW:        "#1a7a4a",
        PROBE_RTT_STATE: "#e07b00",
    }

    fig, ax = plt.subplots(figsize=(16, 7))

    # Phase background shading
    for start, end, phase in collect_phase_spans(times, states):
        ax.axvspan(start, end, alpha=0.22, color=phase_colors[phase], zorder=1)

    # True BDP reference
    ax.axhline(BDP, color="gray", linewidth=1.0, linestyle="-.",
               label=f"True BDP = {BDP:.0f} MSS", zorder=2, alpha=0.7)

    # BDP estimate (dashed orange) — shows BBR learning the network
    ax.plot(times, bdp_ests, color="orangered", linewidth=1.3, linestyle="--",
            label="BDP estimate (BtlBW_est × RTprop_est)", zorder=3, alpha=0.85)

    # cwnd
    ax.plot(times, cwnds, color="steelblue", linewidth=2.2,
            label="cwnd (MSS)", zorder=4)
    ax.scatter(times, cwnds, color="steelblue", s=16, zorder=5)

    # Transition markers
    transitions = find_transitions(states)
    annotated = set()
    for rtt, new_state in transitions.items():
        color = transition_colors.get(new_state, "#555")
        ax.axvline(rtt, color=color, linestyle=":", linewidth=1.7, zorder=2)
        label_str = f"→ {new_state}"
        if label_str not in annotated:
            annotated.add(label_str)
        y_pos = cwnds[rtt] if cwnds[rtt] > 6 else max(cwnds) * 0.15
        dy = 6 if new_state != PROBE_RTT_STATE else -10
        ax.annotate(
            f"→ {new_state}",
            xy=(rtt, cwnds[rtt]),
            xytext=(rtt + 0.6, y_pos + dy),
            fontsize=8.5, color=color, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=color, lw=1.3),
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=color, alpha=0.88),
            zorder=6,
        )

    # Annotate PROBE_BW gain values at peaks and troughs
    probe_bw_gains = PROBE_BW_GAIN_CYCLE
    cycle_counter = 0
    for i, (t, s) in enumerate(zip(times, states)):
        if s == PROBE_BW and i not in transitions:
            g = probe_bw_gains[cycle_counter % len(probe_bw_gains)]
            cycle_counter += 1
            if g != 1.0:   # only label probe-up / probe-drain rounds
                ax.text(t, cwnds[i] + 1.5, f"×{g}", fontsize=7,
                        color="steelblue", ha="center", va="bottom", alpha=0.8)
        else:
            cycle_counter = 0   # reset on state change (approximate)

    # Legend
    phase_patches = [
        mpatches.Patch(color=phase_colors[s], alpha=0.5, label=f"{s} phase")
        for s in [STARTUP, DRAIN, PROBE_BW, PROBE_RTT_STATE]
    ]
    handles, _ = ax.get_legend_handles_labels()
    ax.legend(handles=handles + phase_patches, loc="upper right",
              fontsize=8.5, framealpha=0.9)

    # Parameter info box
    info = (
        f"True BtlBW = {BtlBW_TRUE:.0f} MSS/RTT\n"
        f"True RTprop = {RTprop_TRUE:.1f} RTT  →  BDP = {BDP:.0f} MSS\n"
        f"PROBE_BW gains: {PROBE_BW_GAIN_CYCLE}\n"
        f"PROBE_RTT interval = {PROBE_RTT_INTERVAL} RTTs,  duration = {PROBE_RTT_DURATION} RTTs"
    )
    ax.text(0.01, 0.97, info, transform=ax.transAxes, fontsize=8,
            va="top", ha="left",
            bbox=dict(boxstyle="round", fc="lightyellow", ec="gray", alpha=0.85))

    ax.set_xlabel("Time (RTT)", fontsize=12)
    ax.set_ylabel("Congestion Window (MSS)", fontsize=12)
    ax.set_title(
        "TCP BBR — Congestion Window over Time\n"
        "Model-based, not loss-based: cwnd tracks BtlBW × RTprop estimate",
        fontsize=13, fontweight="bold"
    )
    ax.set_xlim(0, TOTAL_RTTS - 1)
    ax.set_ylim(0, max(cwnds) * 1.25)
    ax.grid(True, linestyle="--", alpha=0.3)

    plt.tight_layout()
    out = "tcp_bbr_cwnd.png"
    plt.savefig(out, dpi=150)
    print(f"Saved: {out}")
    plt.show()


if __name__ == "__main__":
    times, cwnds, states, bdp_ests = simulate()

    print(f"{'RTT':>4}  {'cwnd':>7}  {'bdp_est':>8}  state")
    print("-" * 45)
    prev_state = None
    for t, c, s, b in zip(times, cwnds, states, bdp_ests):
        marker = "  <-- new state" if s != prev_state else ""
        print(f"{t:>4}  {c:>7.1f}  {b:>8.2f}  {s}{marker}")
        prev_state = s

    plot(times, cwnds, states, bdp_ests)
