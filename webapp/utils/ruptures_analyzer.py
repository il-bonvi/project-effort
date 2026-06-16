"""
ruptures_analyzer.py — Changepoint-based effort detection using ruptures.

Post-merge filter logic
-----------------------
After Pelt + merge, each candidate effort passes the display filter if:
  (A) duration >= min_effort_sec                          [sustained effort]
  OR
  (B) avg_power >= cp * opener_threshold_pct / 100       [short but very intense]

Example with CP=235, min_effort_sec=60, opener_threshold_pct=200:
  - 30s @ 100% CP  → merged with nothing → fails (A) fails (B) → SCARTATO
  - 30s @ 100% CP  → merged into 5min effort → passes (A)      → MOSTRATO
  - 40s @ 250% CP  → fails (A) but passes (B)                  → MOSTRATO
  - 40s @ 101% CP  → fails (A) fails (B)                       → SCARTATO
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
    # ── Detection ─────────────────────────────────────────────────────────────
    model: str             = "l2"
    penalty: float         = 10.0
    min_segment_sec: int   = 15       # granularità Pelt (min_size)
    smooth_window_sec: int = 20       # smoothing pre-detection

    # ── Intensity threshold ────────────────────────────────────────────────────
    min_cp_pct: float      = 100.0    # soglia per label "above/below"

    # ── Merge ─────────────────────────────────────────────────────────────────
    merge_gap_sec: int          = 30   # gap massimo tra effort adiacenti
    merge_power_diff_pct: float = 15.0 # Δ potenza massimo per il merge

    # ── Post-merge display filter ──────────────────────────────────────────────
    min_effort_sec: int         = 60   # durata minima per essere mostrato (A)
    opener_threshold_pct: float = 200.0  # se più corto ma sopra questa % CP → mostrato (B)

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
        if self.min_effort_sec < 0:
            raise ValueError("min_effort_sec must be >= 0")
        if self.opener_threshold_pct <= 0:
            raise ValueError("opener_threshold_pct must be > 0")


def detect_efforts_ruptures(
    df: pd.DataFrame,
    cp: float,
    config: RupturesConfig | None = None,
) -> List[Tuple[int, int, float]]:
    """
    Pipeline:
      1. Smooth signal
      2. Downsample to 1 Hz
      3. Pelt → breakpoints
      4. Remap to original indices
      5. Label above/below min_cp_pct threshold
      6. Merge adjacent above-threshold segments
      7. Post-merge filter:
           keep if duration >= min_effort_sec  [sustained]
           OR   avg_power >= cp * opener_threshold_pct / 100  [intense sprint]
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

    # ── 2. Downsample to 1 Hz ─────────────────────────────────────────────────
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

    # ── 4. Remap ───────────────────────────────────────────────────────────────
    starts_orig = [0]             + [min(b * factor, n) for b in bkps[:-1]]
    ends_orig   = [min(b * factor, n) for b in bkps]

    # ── 5. Label ──────────────────────────────────────────────────────────────
    threshold = cp * config.min_cp_pct / 100.0
    segments  = []
    for s, e in zip(starts_orig, ends_orig):
        seg = power[s:e]
        if len(seg) == 0:
            continue
        avg   = float(seg.mean())
        above = avg >= threshold
        segments.append({"s": s, "e": e, "avg": avg, "above": above})

    # ── 6. Merge ───────────────────────────────────────────────────────────────
    def _similar_power(avg_a: float, avg_b: float) -> bool:
        if config.merge_power_diff_pct >= 100:
            return True
        if avg_a <= 0 or avg_b <= 0:
            return False
        return abs(avg_a - avg_b) / max(avg_a, avg_b) * 100 <= config.merge_power_diff_pct

    merged: List[Tuple[int, int, float]] = []
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
            gap = nxt["s"] - me

            if nxt["above"] and gap <= config.merge_gap_sec and _similar_power(m_avg, nxt["avg"]):
                me    = nxt["e"]
                m_avg = float(power[ms:me].mean())
                j    += 1
            elif not nxt["above"] and j + 1 < len(segments):
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

        merged.append((int(ms), int(me), float(power[ms:me].mean())))
        i = j

    # ── 7. Post-merge display filter ───────────────────────────────────────────
    # Duration in seconds (at original sampling rate, 1 sample ≈ 1/sps seconds)
    sprint_watt_threshold = cp * config.opener_threshold_pct / 100.0

    efforts: List[Tuple[int, int, float]] = []
    discarded = 0
    for ms, me, avg in merged:
        duration_sec = (me - ms) / sps          # seconds at original rate
        is_sustained = duration_sec >= config.min_effort_sec
        is_sprint    = avg >= sprint_watt_threshold
        if is_sustained or is_sprint:
            efforts.append((ms, me, avg))
        else:
            discarded += 1

    logger.info(
        "ruptures: %d segments → %d merged → %d efforts "
        "(discarded %d: too short + not intense enough) "
        "[model=%s pen=%.1f smooth=%ds gap=%ds Δpwr≤%.0f%% "
        "min_dur=%ds sprint≥%.0f%%CP]",
        len(segments), len(merged), len(efforts), discarded,
        config.model, config.penalty,
        config.smooth_window_sec, config.merge_gap_sec,
        config.merge_power_diff_pct,
        config.min_effort_sec, config.opener_threshold_pct,
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
        min_effort_sec       = int(d.get("ruptures_min_effort", 60)),
        opener_threshold_pct = float(d.get("ruptures_opener_threshold", 200.0)),
    )