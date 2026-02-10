"""Metrics calculation module for cycling performance analysis"""

from typing import List, Dict, Any
import numpy as np
import pandas as pd


def calculate_normalized_power(power_data: List[float]) -> float:
    """Calculate Normalized Power (NP) using 30-second rolling average to the 4th power"""
    if not power_data or len(power_data) == 0:
        return 0.0

    power_array = np.array(power_data)
    power_array = power_array[power_array >= 0]  # Remove negative values

    if len(power_array) == 0:
        return 0.0

    # 30-second rolling average
    window_size = 30
    if len(power_array) < window_size:
        avg_power = np.mean(power_array)
        return float(avg_power)

    # Calculate rolling average
    rolling_avg = np.convolve(power_array, np.ones(window_size)/window_size, mode='valid')

    # Raise to 4th power, average, then take 4th root
    np_value = np.power(np.mean(np.power(rolling_avg, 4)), 0.25)

    return float(np_value)


def calculate_intensity_factor(np_value: float, ftp: float) -> float:
    """Calculate Intensity Factor (IF) = NP / FTP"""
    if ftp <= 0:
        return 0.0
    return np_value / ftp


def calculate_tss(np_value: float, ftp: float, duration_hours: float) -> float:
    """Calculate Training Stress Score (TSS)"""
    if ftp <= 0 or duration_hours <= 0:
        return 0.0

    if_value = calculate_intensity_factor(np_value, ftp)
    tss = (duration_hours * np_value * if_value) / (ftp * 36) * 100

    return float(tss)


def calculate_variability_index(np_value: float, avg_power: float) -> float:
    """Calculate Variability Index (VI) = NP / Avg Power"""
    if avg_power <= 0:
        return 1.0
    return np_value / avg_power


def calculate_ride_stats(df: pd.DataFrame, ftp: float) -> Dict[str, Any]:
    """Calculate comprehensive ride statistics"""
    power_data = df['power'].tolist()
    duration_sec = df['time_sec'].iloc[-1] - df['time_sec'].iloc[0] if len(df) > 0 else 0
    duration_hours = duration_sec / 3600

    # Basic stats
    avg_power = df['power'].mean()
    max_power = df['power'].max()

    # Advanced metrics
    np_value = calculate_normalized_power(power_data)
    if_value = calculate_intensity_factor(np_value, ftp)
    tss = calculate_tss(np_value, ftp, duration_hours)
    vi = calculate_variability_index(np_value, avg_power)

    # Distance and elevation
    total_distance = df['distance_km'].iloc[-1] if len(df) > 0 else 0
    elevation_gain = df['altitude'].diff().clip(lower=0).sum() if 'altitude' in df.columns else 0

    # Heart rate
    avg_hr = df['heartrate'].mean() if 'heartrate' in df.columns and df['heartrate'].max() > 0 else 0
    max_hr = df['heartrate'].max() if 'heartrate' in df.columns else 0

    return {
        'duration_sec': duration_sec,
        'duration_hours': duration_hours,
        'avg_power': avg_power,
        'max_power': max_power,
        'normalized_power': np_value,
        'intensity_factor': if_value,
        'tss': tss,
        'variability_index': vi,
        'total_distance_km': total_distance,
        'elevation_gain_m': elevation_gain,
        'avg_hr': avg_hr,
        'max_hr': max_hr
    }
