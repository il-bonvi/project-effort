"""
CORE 3D MAP - Calcoli e logica per la mappa 3D
Elaborazione dati geografici, calcolo parametri effort
"""

import json
import logging
import numpy as np
import pandas as pd
from typing import List, Tuple, Dict, Any, TypedDict
from .effort_analyzer import get_zone_color
from .segment_metrics import compute_segment_metrics

logger = logging.getLogger(__name__)


class EffortParameters(TypedDict):
    duration: int
    elevation: float
    w_kg: float
    best_5s: int
    best_5s_watt_kg: float
    avg_hr: float
    max_hr: float
    avg_cadence: float
    avg_speed: float
    avg_grade: float
    max_grade: float
    vam: float
    watts_first: float
    watts_second: float
    watts_ratio: float
    kj: float
    kj_over_cp: float
    kj_kg: float
    kj_kg_over_cp: float
    kj_h_kg: float
    kj_h_kg_over_cp: float
    vam_teorico: float


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
                               cp: float, weight: float,
                               joules_cumulative: np.ndarray,
                               joules_over_cp_cumulative: np.ndarray) -> EffortParameters:
    """
    Calcola tutti i parametri di un singolo effort.
    
    Args:
        s, e: Indici start/end dell'effort nel DataFrame completo
        avg: Potenza media
        df: DataFrame completo con dati attività
        alt_values: Array altitudini dal DataFrame COMPLETO (per calcoli con indici s, e)
        dist_km_values: Array distanze dal DataFrame COMPLETO (per calcoli con indici s, e)
        cp: Critical Power
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

    safe_len = min(
        len(time_sec),
        len(power_all),
        len(hr_all),
        len(cadence_all),
        len(grade_all),
        len(alt_values),
        len(dist_km_values)
    )

    if safe_len <= 0:
        return {
            'duration': 0,
            'elevation': 0.0,
            'w_kg': 0.0,
            'best_5s': 0,
            'best_5s_watt_kg': 0.0,
            'avg_hr': 0.0,
            'max_hr': 0.0,
            'avg_cadence': 0.0,
            'avg_speed': 0.0,
            'avg_grade': 0.0,
            'max_grade': 0.0,
            'vam': 0.0,
            'watts_first': 0.0,
            'watts_second': 0.0,
            'watts_ratio': 0.0,
            'kj': 0.0,
            'kj_over_cp': 0.0,
            'kj_kg': 0.0,
            'kj_kg_over_cp': 0.0,
            'kj_h_kg': 0.0,
            'kj_h_kg_over_cp': 0.0,
            'vam_teorico': 0.0
        }
    
    # Segmenti dati (con boundary checks appropriati)
    # Assicura che gli indici siano validi
    s = max(0, min(s, safe_len - 1))
    e = max(s + 1, min(e, safe_len))
    
    seg_power = power_all[s:e]
    seg_time = time_sec[s:e]
    seg_alt_arr = alt_values[s:e]
    seg_hr = hr_all[s:e]
    seg_cadence = cadence_all[s:e]
    seg_grade = grade_all[s:e]
    seg_dist_km = dist_km_values[s:e]
    
    kj = joules_cumulative[s] / 1000 if s < len(joules_cumulative) else 0
    kj_over_cp = joules_over_cp_cumulative[s] / 1000 if s < len(joules_over_cp_cumulative) else 0
    metrics = compute_segment_metrics(
        seg_power=seg_power,
        seg_time=seg_time,
        seg_alt=seg_alt_arr,
        seg_dist_m=seg_dist_km * 1000,
        seg_hr=seg_hr,
        seg_grade=seg_grade,
        seg_cadence=seg_cadence,
        avg_power=float(avg),
        weight=float(weight),
        start_time_sec=float(time_sec[s]),
        kj=float(kj),
        kj_over_cp=float(kj_over_cp),
    )
    
    return {
        'duration': int(metrics['duration']),
        'elevation': float(metrics['elevation_gain']),
        'w_kg': float(metrics['avg_power_per_kg']),
        'best_5s': int(metrics['best_5s_watt']),
        'best_5s_watt_kg': float(metrics['best_5s_watt_kg']),
        'avg_hr': float(metrics['avg_hr']),
        'max_hr': float(metrics['max_hr']),
        'avg_cadence': float(metrics['avg_cadence']),
        'avg_speed': float(metrics['avg_speed']),
        'avg_grade': float(metrics['avg_grade']),
        'max_grade': float(metrics['max_grade']),
        'vam': float(metrics['vam']),
        'watts_first': float(metrics['avg_watts_first']),
        'watts_second': float(metrics['avg_watts_second']),
        'watts_ratio': float(metrics['watts_ratio']),
        'kj': float(metrics['kj']),
        'kj_over_cp': float(metrics['kj_over_cp']),
        'kj_kg': float(metrics['kj_kg']),
        'kj_kg_over_cp': float(metrics['kj_kg_over_cp']),
        'kj_h_kg': float(metrics['kj_h_kg']),
        'kj_h_kg_over_cp': float(metrics['kj_h_kg_over_cp']),
        'vam_teorico': float(metrics['vam_teorico'])
    }


def prepare_efforts_data(df: pd.DataFrame, efforts: List[Tuple[int, int, float]],
                        sprints: List[Dict[str, Any]], cp: float, weight: float,
                        geojson_data: dict, orig_indices: List[int],
                        alt_values_full: np.ndarray, dist_km_values_full: np.ndarray,
                        alt_values_filtered: np.ndarray, dist_km_values_filtered: np.ndarray) -> str:
    """
    Prepara i dati efforts e sprints per il JavaScript.
    
    Args:
        df: DataFrame completo con dati attività (usato per calcoli energetici)
        efforts: Lista efforts (start, end, avg_power) con indici riferiti al df completo
        sprints: Lista sprints (dict con start, end, avg_power, ecc.) con indici riferiti al df completo
        cp: Critical Power
        weight: Peso atleta
        geojson_data: GeoJSON della traccia (da df filtrato)
        orig_indices: Indici del df filtrato nel df completo
        alt_values_full: Array altitudini da df COMPLETO (per calcoli parametri)
        dist_km_values_full: Array distanze da df COMPLETO (per calcoli parametri)
        alt_values_filtered: Array altitudini da df FILTRATO (allineato con coords GeoJSON)
        dist_km_values_filtered: Array distanze da df FILTRATO (allineato con coords GeoJSON)
        
    Returns:
        JSON string con dati efforts e sprints
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
            if power_all[i] >= cp:
                joules_over_cp_cumulative[i] = joules_over_cp_cumulative[i-1] + power_all[i] * dt
            else:
                joules_over_cp_cumulative[i] = joules_over_cp_cumulative[i-1]
        else:
            joules_cumulative[i] = joules_cumulative[i-1]
            joules_over_cp_cumulative[i] = joules_over_cp_cumulative[i-1]
    
    efforts_list: List[Dict[str, Any]] = []
    coords = geojson_data['features'][0]['geometry']['coordinates']
    
    for effort_idx, (s, e, avg) in enumerate(efforts):
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
        
        zone_color = get_zone_color(avg, cp)
        
        # Segmenti per visualizzazione (usa array filtrati allineati con coords)
        segment_coords = coords[pos_start:pos_end+1]
        segment_alt = alt_values_filtered[pos_start:pos_end+1].tolist() if pos_end < len(alt_values_filtered) else []
        segment_dist = dist_km_values_filtered[pos_start:pos_end+1].tolist() if pos_end < len(dist_km_values_filtered) else []
        
        # Calcola parametri (usa array completi dal df originale)
        params = calculate_effort_parameters(s, e, avg, df, alt_values_full, dist_km_values_full, 
                                            cp, weight, joules_cumulative, joules_over_cp_cumulative)
        
        if len(segment_coords) > 0:
            effort_dict = {
                'id': int(effort_idx),
                'type': 'effort',
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
    
    # ===== STEP 7: Sprints Data Processing =====
    for sprint_idx, sprint in enumerate(sprints):
        s = sprint['start']
        e = sprint['end']
        avg = sprint['avg']
        
        # Mappa indici da sprint a coordinate filtrate
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
        
        # Sprint color (nero per distinguerli dagli efforts)
        sprint_color = '#000000'
        
        # Segmenti per visualizzazione (usa array filtrati allineati con coords)
        segment_coords = coords[pos_start:pos_end+1]
        segment_alt = alt_values_filtered[pos_start:pos_end+1].tolist() if pos_end < len(alt_values_filtered) else []
        segment_dist = dist_km_values_filtered[pos_start:pos_end+1].tolist() if pos_end < len(dist_km_values_filtered) else []
        
        # Calcola parametri per sprint (usando stessa logica degli efforts, usa array completi)
        params = calculate_effort_parameters(s, e, avg, df, alt_values_full, dist_km_values_full, 
                                            cp, weight, joules_cumulative, joules_over_cp_cumulative)
        
        if len(segment_coords) > 0:
            sprint_dict = {
                'id': int(sprint_idx),
                'pos': int(pos_start),
                'start': int(pos_start),
                'end': int(pos_end),
                'avg': float(avg),
                'color': sprint_color,
                'segment': segment_coords,
                'altitude': segment_alt,
                'distance': segment_dist,
                'distance_km': float(segment_dist[-1] - segment_dist[0]) if len(segment_dist) > 1 else 0,
                'type': 'sprint'  # Marker per identificare gli sprint
            }
            sprint_dict.update(params)
            efforts_list.append(sprint_dict)
    
    return json.dumps(efforts_list)
