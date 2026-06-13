# ==============================================================================
# analysis_config.py — Configuration dataclasses for effort/sprint detection
# ==============================================================================

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class EffortConfig:
    """
    Legacy dataclass kept for backward compatibility with existing route code
    (altimetria_d3, map2d, map3d, export).
    When using ruptures-based detection, this is populated with a shim in
    upload.py so that downstream code that reads e.g. effort_config.window_seconds
    doesn't break.
    """
    window_seconds: int = 30
    min_effort_intensity_cp: float = 100.0
    merge_power_diff_percent: float = 0.0
    trim_window_seconds: int = 0
    trim_low_percent: float = 85.0
    extend_window_seconds: int = 0
    extend_low_percent: float = 80.0


@dataclass
class SprintConfig:
    """Configuration for sprint (peak-power burst) detection."""
    min_power: int = 500
    window_seconds: int = 5
    merge_gap_sec: int = 3


# Re-export RupturesConfig from ruptures_analyzer so existing import paths
# (from utils.analysis_config import RupturesConfig) continue to work.
from utils.ruptures_analyzer import RupturesConfig  # noqa: E402

__all__ = ["EffortConfig", "SprintConfig", "RupturesConfig"]
