"""Shared segment metrics for efforts/sprints across routes and map utilities."""

from typing import TypedDict

import numpy as np


class SegmentMetrics(TypedDict):
    duration: int
    elevation_gain: float
    dist_tot_m: float
    avg_speed: float
    avg_grade: float
    max_grade: float
    vam: float
    avg_watts_first: float
    avg_watts_second: float
    watts_ratio: float
    avg_hr: float
    max_hr: float
    best_5s_watt: int
    best_5s_watt_kg: float
    avg_power_per_kg: float
    avg_cadence: float
    kj: float
    kj_over_cp: float
    kj_kg: float
    kj_kg_over_cp: float
    kj_h_kg: float
    kj_h_kg_over_cp: float
    vam_teorico: float
    wkg_teoric: float
    diff_wkg: float
    perc_err: float
    vam_arrow: str
    diff_vam: float


def _compute_robust_max_grade(
    seg_grade: np.ndarray,
    seg_alt: np.ndarray,
    seg_dist_m: np.ndarray,
) -> float:
    """Return a stable max uphill gradient even when source grade stream is flat/invalid."""
    max_grade = 0.0

    if len(seg_grade) > 0:
        valid_grade = seg_grade[np.isfinite(seg_grade)]
        if len(valid_grade) > 0:
            max_grade = float(valid_grade.max())

    # Fallback: derive local slope from altitude/distance when grade stream is unusable.
    if max_grade <= 0.05 and len(seg_alt) >= 2 and len(seg_dist_m) >= 2:
        d_alt = np.diff(seg_alt.astype(float))
        d_dist = np.diff(seg_dist_m.astype(float))
        valid = np.isfinite(d_alt) & np.isfinite(d_dist) & (d_dist > 0.5)
        if np.any(valid):
            local_grade = (d_alt[valid] / d_dist[valid]) * 100.0
            if len(local_grade) > 0 and np.isfinite(local_grade).any():
                max_grade = float(np.nanmax(local_grade))

    return float(max(0.0, max_grade))


def compute_segment_metrics(
    *,
    seg_power: np.ndarray,
    seg_time: np.ndarray,
    seg_alt: np.ndarray,
    seg_dist_m: np.ndarray,
    seg_hr: np.ndarray,
    seg_grade: np.ndarray,
    seg_cadence: np.ndarray,
    avg_power: float,
    weight: float,
    start_time_sec: float,
    kj: float,
    kj_over_cp: float,
) -> SegmentMetrics:
    """Compute a consistent set of performance metrics for one segment."""
    if len(seg_time) == 0:
        return {
            "duration": 0,
            "elevation_gain": 0.0,
            "dist_tot_m": 0.0,
            "avg_speed": 0.0,
            "avg_grade": 0.0,
            "max_grade": 0.0,
            "vam": 0.0,
            "avg_watts_first": 0.0,
            "avg_watts_second": 0.0,
            "watts_ratio": 0.0,
            "avg_hr": 0.0,
            "max_hr": 0.0,
            "best_5s_watt": 0,
            "best_5s_watt_kg": 0.0,
            "avg_power_per_kg": 0.0,
            "avg_cadence": 0.0,
            "kj": 0.0,
            "kj_over_cp": 0.0,
            "kj_kg": 0.0,
            "kj_kg_over_cp": 0.0,
            "kj_h_kg": 0.0,
            "kj_h_kg_over_cp": 0.0,
            "vam_teorico": 0.0,
            "wkg_teoric": 0.0,
            "diff_wkg": 0.0,
            "perc_err": 0.0,
            "vam_arrow": "",
            "diff_vam": 0.0,
        }

    duration = float(seg_time[-1] - seg_time[0] + 1)
    elevation_gain = float(seg_alt[-1] - seg_alt[0]) if len(seg_alt) > 0 else 0.0
    dist_tot_m = float(seg_dist_m[-1] - seg_dist_m[0]) if len(seg_dist_m) > 0 else 0.0
    avg_speed = float(dist_tot_m / (duration / 3600) / 1000) if duration > 0 else 0.0
    avg_grade = float((elevation_gain / dist_tot_m * 100) if dist_tot_m > 0 else 0.0)
    max_grade = _compute_robust_max_grade(seg_grade, seg_alt, seg_dist_m)
    vam = float(elevation_gain / (duration / 3600)) if duration > 0 else 0.0

    half = len(seg_power) // 2
    avg_watts_first = float(seg_power[:half].mean()) if half > 0 else 0.0
    avg_watts_second = float(seg_power[half:].mean()) if len(seg_power) > half else 0.0
    watts_ratio = float(avg_watts_first / avg_watts_second) if avg_watts_second > 0 else 0.0

    valid_hr = seg_hr[seg_hr > 0]
    avg_hr = float(valid_hr.mean()) if len(valid_hr) > 0 else 0.0
    max_hr = float(valid_hr.max()) if len(valid_hr) > 0 else 0.0

    valid_cadence = seg_cadence[seg_cadence > 0]
    avg_cadence = float(valid_cadence.mean()) if len(valid_cadence) > 0 else 0.0

    best_5s_watt = 0
    best_5s_watt_kg = 0.0
    if len(seg_power) >= 5:
        moving_avgs = [seg_power[i : i + 5].mean() for i in range(len(seg_power) - 4)]
        best_5s = max(moving_avgs) if moving_avgs else 0.0
        best_5s_watt = int(best_5s)
        if weight > 0:
            best_5s_watt_kg = float(best_5s / weight)

    avg_power_per_kg = float(avg_power / weight) if weight > 0 else 0.0

    kj_kg = float((kj / weight) if weight > 0 else 0.0)
    kj_kg_over_cp = float((kj_over_cp / weight) if weight > 0 else 0.0)
    hours = float(start_time_sec / 3600) if start_time_sec > 0 else 0.0
    kj_h_kg = float((kj_kg / hours) if hours > 0 else 0.0)
    kj_h_kg_over_cp = float((kj_kg_over_cp / hours) if hours > 0 else 0.0)

    gradient_factor = float(2 + (avg_grade / 10))
    vam_teorico = float((avg_power / weight) * (gradient_factor * 100)) if weight > 0 else 0.0
    wkg_teoric = float(vam / (gradient_factor * 100)) if gradient_factor > 0 else 0.0
    diff_wkg = float(abs(avg_power_per_kg - wkg_teoric))
    perc_err = (
        float(((wkg_teoric - avg_power_per_kg) / avg_power_per_kg * 100)) if avg_power_per_kg != 0 else 0.0
    )

    return {
        "duration": int(duration),
        "elevation_gain": elevation_gain,
        "dist_tot_m": dist_tot_m,
        "avg_speed": avg_speed,
        "avg_grade": avg_grade,
        "max_grade": max_grade,
        "vam": vam,
        "avg_watts_first": avg_watts_first,
        "avg_watts_second": avg_watts_second,
        "watts_ratio": watts_ratio,
        "avg_hr": avg_hr,
        "max_hr": max_hr,
        "best_5s_watt": best_5s_watt,
        "best_5s_watt_kg": best_5s_watt_kg,
        "avg_power_per_kg": avg_power_per_kg,
        "avg_cadence": avg_cadence,
        "kj": float(kj),
        "kj_over_cp": float(kj_over_cp),
        "kj_kg": kj_kg,
        "kj_kg_over_cp": kj_kg_over_cp,
        "kj_h_kg": kj_h_kg,
        "kj_h_kg_over_cp": kj_h_kg_over_cp,
        "vam_teorico": vam_teorico,
        "wkg_teoric": wkg_teoric,
        "diff_wkg": diff_wkg,
        "perc_err": perc_err,
        "vam_arrow": "⬆️" if vam_teorico - vam > 0 else ("⬇️" if vam_teorico - vam < 0 else ""),
        "diff_vam": float(abs(vam_teorico - vam)),
    }
