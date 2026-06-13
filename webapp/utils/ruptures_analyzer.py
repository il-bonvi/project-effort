"""
ruptures_analyzer.py — Changepoint-based effort detection using ruptures.

Merge logic
-----------
After Pelt segments the signal, adjacent above-threshold segments are merged
only when BOTH conditions hold:
  1. The time gap between them is ≤ merge_gap_sec
  2. Their average powers differ by ≤ merge_power_diff_pct %
     (a 250W effort next to a 150W segment are NOT merged even if close)
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_TARGET_HZ = 1


@dataclass
class RupturesConfig:
    model: str                  = "l2"
    penalty: float              = 10.0
    min_segment_sec: int        = 15
    smooth_window_sec: int      = 20
    min_cp_pct: float           = 100.0
    merge_gap_sec: int          = 30
    merge_power_diff_pct: float = 15.0   # ← NEW: max % power diff to allow merge

    def __post_init__(self):
        valid = ("rbf", "l2", "l1", "cosine", "linear", "clinear")
        if self.model not in valid:
            raise ValueError(f"Unknown model '{self.model}'")
        if self.penalty <= 0:
            raise ValueError("penalty must be > 0")
        if self.min_segment_sec < 1:
            raise ValueError("min_segment_sec must be >= 1")
        if self.smooth_window_sec < 0:
            raise ValueError("smooth_window_sec must be >= 0")
        if not (0 < self.min_cp_pct <= 300):
            raise ValueError("min_cp_pct must be in (0, 300]")
        if self.merge_gap_sec < 0:
            raise ValueError("merge_gap_sec must be >= 0")
        if not (0 <= self.merge_power_diff_pct <= 100):
            raise ValueError("merge_power_diff_pct must be in [0, 100]")


def detect_efforts_ruptures(
    df: pd.DataFrame,
    cp: float,
    config: RupturesConfig | None = None,
) -> List[Tuple[int, int, float]]:
    """
    Detect efforts via Pelt changepoint detection on the power stream.

    Pipeline
    --------
    1. Smooth power (rolling mean, smooth_window_sec)
    2. Downsample to 1 Hz (fast Pelt on any FIT frequency)
    3. Pelt → breakpoints, remap to original row indices
    4. Label each segment above/below intensity threshold
    5. Merge adjacent above-threshold segments when:
         - time gap ≤ merge_gap_sec  AND
         - power difference ≤ merge_power_diff_pct %
    6. Return List[(start_idx, end_idx, avg_power)]
    """
    try:
        import ruptures as rpt
    except ImportError:
        raise ImportError("Run: pip install ruptures")

    if config is None:
        config = RupturesConfig()

    power    = df["power"].values.astype(float)
    time_sec = df["time_sec"].values.astype(float)
    n        = len(power)

    if n < 10:
        logger.warning("Too few samples (%d)", n)
        return []

    # ── 1. Smooth ──────────────────────────────────────────────────────────────
    if config.smooth_window_sec > 0:
        w  = max(3, config.smooth_window_sec)
        k  = np.ones(w) / w
        sm = np.convolve(power, k, mode="same")
        h  = w // 2
        sm[:h]  = power[:h]
        sm[-h:] = power[-h:]
        sm = np.clip(sm, 0, None)
    else:
        sm = np.clip(power.copy(), 0, None)

    # ── 2. Downsample ─────────────────────────────────────────────────────────
    median_dt = float(np.median(np.diff(time_sec))) if n > 1 else 1.0
    sps       = 1.0 / median_dt if median_dt > 0 else 1.0
    factor    = max(1, int(round(sps / _TARGET_HZ)))

    if factor > 1:
        trim = (n // factor) * factor
        ds   = sm[:trim].reshape(-1, factor).mean(axis=1)
        logger.info("Downsampled %d→%d (factor=%d)", n, len(ds), factor)
    else:
        ds   = sm
        trim = n

    # ── 3. Pelt ────────────────────────────────────────────────────────────────
    min_size_ds = max(2, int(config.min_segment_sec / factor))
    try:
        algo = rpt.Pelt(model=config.model, min_size=min_size_ds, jump=1).fit(ds.reshape(-1, 1))
        bkps = algo.predict(pen=config.penalty)
    except Exception as exc:
        logger.error("Pelt failed: %s", exc)
        return []

    starts_orig = [0]             + [min(b * factor, n) for b in bkps[:-1]]
    ends_orig   = [min(b * factor, n) for b in bkps]

    # ── 4. Label ──────────────────────────────────────────────────────────────
    threshold = cp * config.min_cp_pct / 100.0
    segments  = []
    for s, e in zip(starts_orig, ends_orig):
        seg = power[s:e]
        if len(seg) == 0:
            continue
        avg = float(seg.mean())
        segments.append({"s": s, "e": e, "avg": avg, "above": avg >= threshold})

    # ── 5. Merge ───────────────────────────────────────────────────────────────
    def _similar_power(avg_a: float, avg_b: float) -> bool:
        """True if the two averages are within merge_power_diff_pct of each other."""
        if config.merge_power_diff_pct >= 100:
            return True                              # no power constraint
        if avg_a <= 0 or avg_b <= 0:
            return False
        diff_pct = abs(avg_a - avg_b) / max(avg_a, avg_b) * 100
        return diff_pct <= config.merge_power_diff_pct

    efforts: List[Tuple[int, int, float]] = []
    i = 0
    while i < len(segments):
        seg = segments[i]
        if not seg["above"]:
            i += 1
            continue

        ms, me, m_avg = seg["s"], seg["e"], seg["avg"]
        j = i + 1

        while j < len(segments):
            nxt = segments[j]
            gap = nxt["s"] - me     # seconds @ 1 Hz

            if nxt["above"] and gap <= config.merge_gap_sec and _similar_power(m_avg, nxt["avg"]):
                # Merge: extend end, recalc running avg
                me    = nxt["e"]
                m_avg = float(power[ms:me].mean())
                j    += 1

            elif not nxt["above"] and j + 1 < len(segments):
                # Gap segment: peek at what's after
                after = segments[j + 1]
                if (after["above"]
                        and after["s"] - me <= config.merge_gap_sec
                        and _similar_power(m_avg, after["avg"])):
                    me    = after["e"]
                    m_avg = float(power[ms:me].mean())
                    j    += 2
                else:
                    break
            else:
                break

        efforts.append((int(ms), int(me), float(power[ms:me].mean())))
        i = j

    logger.info(
        "ruptures: %d segments → %d efforts ≥%.0fW  "
        "[model=%s pen=%.1f smooth=%ds gap=%ds Δpwr≤%.0f%%]",
        len(segments), len(efforts), threshold,
        config.model, config.penalty,
        config.smooth_window_sec, config.merge_gap_sec,
        config.merge_power_diff_pct,
    )
    return efforts


def ruptures_config_from_dict(d: dict) -> RupturesConfig:
    return RupturesConfig(
        model                = str(d.get("ruptures_model", "l2")),
        penalty              = float(d.get("ruptures_penalty", 10.0)),
        min_segment_sec      = int(d.get("ruptures_min_seg", 15)),
        smooth_window_sec    = int(d.get("ruptures_smooth", 20)),
        min_cp_pct           = float(d.get("min_cp_pct", 100.0)),
        merge_gap_sec        = int(d.get("ruptures_merge_gap", 30)),
        merge_power_diff_pct = float(d.get("ruptures_merge_power_diff", 15.0)),
    )