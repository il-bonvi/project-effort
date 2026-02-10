"""
CORE 3D MAP - Calcoli e logica per la mappa 3D
Elaborazione dati geografici, calcolo parametri effort
"""

import json
import logging
import numpy as np
import pandas as pd
from typing import List, Tuple, Dict, Any
from .effort_analyzer import get_zone_color

logger = logging.getLogger(__name__)


def export_traccia_geojson(df: pd.DataFrame) -> Tuple[dict, List[int]]:
    """
    Esporta la traccia in formato GeoJSON LineString con altitudine.
    
    Args:
        df: DataFrame con colonne position_lat, position_long, altitude
        
    Returns:
        Dict GeoJSON FeatureCollection con traccia LineString, lista indici originali
    """
    if 'position_lat' not in df.columns or 'position_long' not in df.columns:
        raise ValueError("DataFrame deve contenere position_lat e position_long")
    
    lat = df['position_lat'].values
    lon = df['position_long'].values
    alt = df['altitude'].values if 'altitude' in df.columns else [0] * len(lat)
    
    # Crea coordinate [lon, lat, alt] (GeoJSON format)
    coordinates = [[float(lon[i]), float(lat[i]), float(alt[i])] for i in range(len(lat))]
    # Mantieni mappatura verso indici originali del DataFrame filtrato
    orig_indices = df.index.to_list()
    
    feature = {
        "type": "Feature",
        "properties": {
            "name": "Traccia ciclo",
            "description": f"Traccia con {len(coordinates)} punti"
        },
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates
        }
    }
    
    return {
        "type": "FeatureCollection",
        "features": [feature]
    }, orig_indices


def validate_and_filter_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filtra coordinate non valide (NaN, fuori range, 0,0).
    
    Args:
        df: DataFrame con dati attività
        
    Returns:
        DataFrame filtrato con coordinate valide
    """
    lat_all = df['position_lat'].values
    lon_all = df['position_long'].values
    
    nan_mask = (~np.isnan(lat_all)) & (~np.isnan(lon_all))
    range_mask = (np.abs(lat_all) <= 90) & (np.abs(lon_all) <= 180)
    zero_mask = ~((np.abs(lat_all) < 1e-9) & (np.abs(lon_all) < 1e-9))
    valid_mask = nan_mask & range_mask & zero_mask

    df_valid = df.loc[valid_mask].copy()
    logger.info(f"Dati geografici: {len(df_valid)} punti validi su {len(df)} totali")
    
    return df_valid


def calculate_zoom_level(lat_values: np.ndarray, lon_values: np.ndarray) -> int:
    """
    Calcola il livello di zoom ottimale basato sull'estensione geografica.
    
    Args:
        lat_values: Array di latitudini
        lon_values: Array di longitudini
        
    Returns:
        Livello zoom (int)
    """
    lat_range = float(lat_values.max() - lat_values.min())
    lon_range = float(lon_values.max() - lon_values.min())
    max_range = float(max(lat_range, lon_range))
    
    if max_range < 0.01:
        return 15
    elif max_range < 0.05:
        return 14
    elif max_range < 0.1:
        return 13
    elif max_range < 0.5:
        return 12
    else:
        return 11


def calculate_effort_parameters(s: int, e: int, avg: float, 
                               df: pd.DataFrame, 
                               alt_values: np.ndarray,
                               dist_km_values: np.ndarray,
                               ftp: float, weight: float,
                               joules_cumulative: np.ndarray,
                               joules_over_cp_cumulative: np.ndarray) -> Dict[str, Any]:
    """
    Calcola tutti i parametri di un singolo effort.
    
    Args:
        s, e: Indici start/end dell'effort
        avg: Potenza media
        df: DataFrame completo con dati attività
        alt_values: Array altitudini filtrate
        dist_km_values: Array distanze filtrate
        ftp: Functional Threshold Power
        weight: Peso atleta
        joules_cumulative: Array Joules cumulativi
        joules_over_cp_cumulative: Array Joules > CP cumulativi
        
    Returns:
        Dict con tutti i parametri calcolati
    """
    time_sec = df['time_sec'].values if 'time_sec' in df.columns else np.arange(len(df))
    power_all = df['power'].values if 'power' in df.columns else np.zeros(len(df))
    hr_all = df['heartrate'].values if 'heartrate' in df.columns else np.zeros(len(df))
    cadence_all = df['cadence'].values if 'cadence' in df.columns else np.zeros(len(df))
    grade_all = df['grade'].values if 'grade' in df.columns else np.zeros(len(df))
    distance_all = df['distance'].values if 'distance' in df.columns else np.zeros(len(df))
    
    # Segmenti dati (con boundary checks appropriati)
    # Assicura che gli indici siano validi
    s = max(0, s)
    e = max(s, min(e, len(power_all)))
    
    seg_power = power_all[s:e]
    seg_time = time_sec[s:e]
    seg_alt_arr = alt_values[max(0, s):min(e, len(alt_values))]
    seg_hr = hr_all[s:e]
    seg_cadence = cadence_all[s:e]
    seg_grade = grade_all[s:e]
    seg_dist_km = dist_km_values[max(0, s):min(e, len(dist_km_values))]
    
    # Durata ed elevazione
    duration = int(seg_time[-1] - seg_time[0] + 1) if len(seg_time) > 0 else 0
    elevation_gain = seg_alt_arr[-1] - seg_alt_arr[0] if len(seg_alt_arr) > 0 else 0
    
    # Distanza (in km)
    dist_tot = seg_dist_km[-1] - seg_dist_km[0] if len(seg_dist_km) > 0 else 0
    
    # Potenza relativa
    w_kg = avg / weight if weight > 0 else 0
    
    # Best 5s
    best_5s_watt = 0
    best_5s_watt_kg = 0
    if len(seg_power) >= 5:
        best_5s = max([seg_power[i:i+5].mean() for i in range(len(seg_power)-4)])
        best_5s_watt = int(best_5s)
        if weight > 0:
            best_5s_watt_kg = best_5s / weight
    
    # Heart rate
    valid_hr = seg_hr[seg_hr > 0]
    avg_hr = valid_hr.mean() if len(valid_hr) > 0 else 0
    max_hr = valid_hr.max() if len(valid_hr) > 0 else 0
    
    # Cadence
    valid_cadence = seg_cadence[seg_cadence > 0]
    avg_cadence = valid_cadence.mean() if len(valid_cadence) > 0 else 0
    
    # Velocità e pendenza
    avg_speed = dist_tot / (duration / 3600) if duration > 0 and dist_tot > 0 else 0
    avg_grade = (elevation_gain / (dist_tot * 1000) * 100) if dist_tot > 0 else 0
    max_grade = seg_grade.max() if len(seg_grade) > 0 else 0
    
    # 1ª metà vs 2ª metà
    half = len(seg_power) // 2
    avg_watts_first = seg_power[:half].mean() if half > 0 else 0
    avg_watts_second = seg_power[half:].mean() if len(seg_power) > half else 0
    watts_ratio = avg_watts_first / avg_watts_second if avg_watts_second > 0 else 0
    
    # VAM
    vam = elevation_gain / (duration / 3600) if duration > 0 else 0
    
    # Joule calculations
    # Use cumulative joules at start of effort (total work at moment effort begins)
    kj = joules_cumulative[s] / 1000 if s < len(joules_cumulative) else 0
    kj_over_cp = joules_over_cp_cumulative[s] / 1000 if s < len(joules_over_cp_cumulative) else 0
    kj_kg = (kj / weight) if weight > 0 else 0
    kj_kg_over_cp = (kj_over_cp / weight) if weight > 0 else 0
    hours = time_sec[s] / 3600 if time_sec[s] > 0 else 0
    kj_h_kg = (kj_kg / hours) if hours > 0 else 0
    kj_h_kg_over_cp = (kj_kg_over_cp / hours) if hours > 0 else 0
    
    # VAM teorico (solo se salita significativa)
    gradient_factor = 2 + (avg_grade / 10) if avg_grade > 0 else 2
    vam_teorico = (avg / weight) * (gradient_factor * 100) if weight > 0 else 0
    
    return {
        'duration': int(duration),
        'elevation': float(elevation_gain),
        'w_kg': float(w_kg),
        'best_5s': int(best_5s_watt),
        'best_5s_watt_kg': float(best_5s_watt_kg),
        'avg_hr': float(avg_hr),
        'max_hr': float(max_hr),
        'avg_cadence': float(avg_cadence),
        'avg_speed': float(avg_speed),
        'avg_grade': float(avg_grade),
        'max_grade': float(max_grade),
        'vam': float(vam),
        'watts_first': float(avg_watts_first),
        'watts_second': float(avg_watts_second),
        'watts_ratio': float(watts_ratio),
        'kj': float(kj),
        'kj_over_cp': float(kj_over_cp),
        'kj_kg': float(kj_kg),
        'kj_kg_over_cp': float(kj_kg_over_cp),
        'kj_h_kg': float(kj_h_kg),
        'kj_h_kg_over_cp': float(kj_h_kg_over_cp),
        'vam_teorico': float(vam_teorico)
    }


def prepare_efforts_data(df: pd.DataFrame, efforts: List[Tuple[int, int, float]],
                        ftp: float, weight: float,
                        geojson_data: dict, orig_indices: List[int],
                        alt_values: np.ndarray, dist_km_values: np.ndarray) -> str:
    """
    Prepara i dati efforts per il JavaScript.
    
    Args:
        df: DataFrame con dati attività
        efforts: Lista efforts (start, end, avg_power)
        ftp: Functional Threshold Power
        weight: Peso atleta
        geojson_data: GeoJSON della traccia
        orig_indices: Indici originali per il mapping
        alt_values: Array altitudini filtrate
        dist_km_values: Array distanze filtrate
        
    Returns:
        JSON string con dati efforts
    """
    # Calcolo Joules cumulative
    time_sec = df['time_sec'].values if 'time_sec' in df.columns else np.arange(len(df))
    power_all = df['power'].values if 'power' in df.columns else np.zeros(len(df))
    
    joules_cumulative = np.zeros(len(power_all))
    joules_over_cp_cumulative = np.zeros(len(power_all))
    for i in range(1, len(power_all)):
        dt = time_sec[i] - time_sec[i-1]
        if dt > 0 and dt < 30:
            joules_cumulative[i] = joules_cumulative[i-1] + power_all[i] * dt
            if power_all[i] >= ftp:
                joules_over_cp_cumulative[i] = joules_over_cp_cumulative[i-1] + power_all[i] * dt
            else:
                joules_over_cp_cumulative[i] = joules_over_cp_cumulative[i-1]
        else:
            joules_cumulative[i] = joules_cumulative[i-1]
            joules_over_cp_cumulative[i] = joules_over_cp_cumulative[i-1]
    
    efforts_list: List[Dict[str, Any]] = []
    coords = geojson_data['features'][0]['geometry']['coordinates']
    
    for s, e, avg in efforts:
        # Mappa indici da effort a coordinate filtrate
        pos_start = 0
        for idx_f, idx_orig in enumerate(orig_indices):
            if idx_orig >= s:
                pos_start = idx_f
                break
        
        pos_end = len(orig_indices) - 1
        for idx_f, idx_orig in enumerate(orig_indices):
            if idx_orig >= e:
                pos_end = idx_f
                break
        
        if pos_end < pos_start:
            pos_end = pos_start + 1
        if pos_end >= len(coords):
            pos_end = len(coords) - 1
        
        zone_color = get_zone_color(avg, ftp)
        
        # Segmenti per visualizzazione
        segment_coords = coords[pos_start:pos_end+1]
        segment_alt = alt_values[pos_start:pos_end+1].tolist() if pos_end < len(alt_values) else []
        segment_dist = dist_km_values[pos_start:pos_end+1].tolist() if pos_end < len(dist_km_values) else []
        
        # Calcola parametri
        params = calculate_effort_parameters(s, e, avg, df, alt_values, dist_km_values, 
                                            ftp, weight, joules_cumulative, joules_over_cp_cumulative)
        
        if len(segment_coords) > 0:
            effort_dict = {
                'pos': int(pos_start),
                'start': int(pos_start),
                'end': int(pos_end),
                'avg': float(avg),
                'color': zone_color,
                'segment': segment_coords,
                'altitude': segment_alt,
                'distance': segment_dist,
                'distance_km': float(segment_dist[-1] - segment_dist[0]) if len(segment_dist) > 1 else 0,
            }
            effort_dict.update(params)
            efforts_list.append(effort_dict)
    
    return json.dumps(efforts_list)
