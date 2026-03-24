"""
TCP CUBIC congestion window simulation.

CUBIC window function:
    W_cubic(t) = C * (t - K)^3 + W_max
    K = cbrt(W_max * beta / C)

After congestion: W_max = cwnd, cwnd *= (1 - beta)

This script is set up to show the inflection point of the CUBIC curve.
Inflection is at t_epoch = K (where W_cubic = W_max).
Left of K: concave-down (decelerating, probing toward W_max).
Right of K: concave-up (accelerating, overshooting W_max).
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# --- Parameters ---
C = 0.4           # CUBIC scaling constant
BETA = 0.7        # multiplicative decrease factor (0.7 = 30% reduction)
RTT = 0.01        # RTT in seconds (10 ms)
INITIAL_CWND = 10 # initial cwnd in segments (MSS units)
MSS = 1           # 1 segment unit
MAX_CWND = 2000   # cap to keep simulation finite
SIM_DURATION = 12 # seconds — long enough to pass the inflection point

# Single congestion event so we can clearly see the full CUBIC S-curve
CONGESTION_EVENTS = [1.0]


def cubic_K(w_max):
    return (w_max * BETA / C) ** (1.0 / 3.0)


def cubic_w(t, w_max, K):
    return C * (t - K) ** 3 + w_max


def simulate():
    times = []
    cwnds = []
    event_times = []
    # Track state at the last congestion event for post-hoc annotation
    last_event_state = {}  # {t_event: (w_max, K)}

    cwnd = float(INITIAL_CWND)
    w_max = cwnd
    t = 0.0
    congestion_queue = sorted(CONGESTION_EVENTS)

    t_epoch = 0.0
    K = cubic_K(w_max)

    dt = RTT

    while t <= SIM_DURATION:
        times.append(t)
        cwnds.append(cwnd)

        if congestion_queue and t >= congestion_queue[0]:
            congestion_queue.pop(0)
            event_times.append(t)
            w_max = cwnd
            cwnd = max(cwnd * (1 - BETA), 1.0)
            t_epoch = 0.0
            K = cubic_K(w_max)
            last_event_state[t] = (w_max, K)

        t += dt
        t_epoch += dt

        w_cubic = cubic_w(t_epoch, w_max, K)

        if w_cubic < cwnd:
            cwnd += MSS / cwnd
        else:
            cwnd += (w_cubic - cwnd) / cwnd

        cwnd = min(cwnd, MAX_CWND)

    return np.array(times), np.array(cwnds), event_times, last_event_state


def plot(times, cwnds, event_times, last_event_state):
    fig, ax = plt.subplots(figsize=(12, 6))

    ax.plot(times, cwnds, color="steelblue", linewidth=1.8, label="simulated cwnd", zorder=3)

    # Overlay theoretical W_cubic curve after each congestion event
    for et, (w_max, K) in last_event_state.items():
        t_range = np.linspace(0, SIM_DURATION - et, 2000)
        w_theory = cubic_w(t_range, w_max, K)
        w_theory = np.clip(w_theory, 0, MAX_CWND)
        ax.plot(
            et + t_range, w_theory,
            color="orange", linewidth=1.2, linestyle="--",
            label="W_cubic(t) theoretical", zorder=2,
        )

        # Mark W_max (horizontal reference)
        ax.axhline(w_max, color="gray", linestyle=":", linewidth=1.0, alpha=0.7)
        ax.annotate(
            f"W_max = {w_max:.0f}",
            xy=(et + 0.2, w_max),
            xytext=(et + 0.3, w_max + max(cwnds) * 0.03),
            fontsize=8, color="gray",
        )

        # Mark inflection point at t_epoch = K  →  W_cubic(K) = W_max
        t_inflection = et + K
        if t_inflection <= SIM_DURATION:
            ax.axvline(t_inflection, color="green", linestyle="-.", linewidth=1.3, alpha=0.8)
            ax.annotate(
                f"inflection\n(t={t_inflection:.2f}s, W=W_max)",
                xy=(t_inflection, w_max),
                xytext=(t_inflection + 0.2, w_max - max(cwnds) * 0.12),
                fontsize=8, color="green",
                arrowprops=dict(arrowstyle="->", color="green", lw=1.0),
            )

    for et in event_times:
        ax.axvline(et, color="tomato", linestyle="--", linewidth=1.2)
        ax.annotate(
            "loss / MD",
            xy=(et, 0),
            xytext=(et + 0.1, max(cwnds) * 0.04),
            color="tomato", fontsize=8,
        )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("cwnd (segments)")
    ax.set_title("TCP CUBIC — Congestion Window over Time\n"
                 "Left of inflection: concave-down (slow probe).  "
                 "Right of inflection: concave-up (fast growth).")
    ax.set_xlim(0, SIM_DURATION)
    ax.set_ylim(0)
    ax.grid(True, linestyle=":", alpha=0.4)

    # Deduplicate legend entries
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), loc="upper left")

    K_val = list(last_event_state.values())[-1][1] if last_event_state else "n/a"
    param_text = (
        f"C={C}  β={BETA}  RTT={int(RTT*1000)} ms  "
        f"init_cwnd={INITIAL_CWND}  "
        f"K={K_val:.2f}s  (inflection at t_epoch=K)"
    )
    fig.text(0.5, 0.01, param_text, ha="center", fontsize=8, color="gray")

    plt.tight_layout(rect=[0, 0.04, 1, 1])
    out = "tcp_cubic_cwnd.png"
    plt.savefig(out, dpi=150)
    print(f"Saved: {out}")
    plt.show()


if __name__ == "__main__":
    times, cwnds, event_times, last_event_state = simulate()
    plot(times, cwnds, event_times, last_event_state)
