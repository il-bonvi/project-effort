# ==============================================================================
# Copyright (c) 2026 Andrea Bonvicin - bFactor Project
# PROPRIETARY LICENSE - TUTTI I DIRITTI RISERVATI
# Sharing, distribution or reproduction is strictly prohibited.
# La condivisione, distribuzione o riproduzione è severamente vietata.
# ==============================================================================

"""
CORE ENGINE - Logica pura per analisi efforts e sprints
Contiene: parsing FIT, calcoli VAM, filtraggio, analisi sprint
"""

from typing import List, Tuple, Dict, Any
import logging
import numpy as np
import pandas as pd
from fitparse import FitFile

logger = logging.getLogger(__name__)

# =====================
# CONFIGURAZIONE DEFAULT
# =====================
WINDOW_SECONDS = 60
MERGE_POWER_DIFF_PERCENT = 15
MIN_EFFORT_INTENSITY_FTP = 100
TRIM_WINDOW_SECONDS = 10
TRIM_LOW_PERCENT = 85
EXTEND_WINDOW_SECONDS = 15
EXTEND_LOW_PERCENT = 80

# Sprint defaults
SPRINT_WINDOW_SECONDS = 5
MIN_SPRINT_POWER = 500

# GPS conversion constant
SEMICIRCLES_TO_DEGREES = 180 / (2**31 - 1)

ZONE_COLORS = [
    (106, "#1f77b4", "CP–just above"),
    (116, "#3eb33e", "Threshold+"),
    (126, "#ff7f0e", "VO₂max"),
    (136, "#da2fbd", "High VO₂max / MAP"),
    (999, "#7315ca", "Supra-MAP"),
]
ZONE_DEFAULT = ("Anaerobico", "#6B3C3C73")



# =====================
# FUNZIONI UTILITY
# =====================

def format_time_hhmmss(seconds: float) -> str:
    """Formatta secondi in HH:MM:SS"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_time_mmss(seconds: float) -> str:
    """Formatta secondi in MM:SS"""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"


# =====================
# FUNZIONI CORE - PARSING & DATA
# =====================

def parse_fit(file_path: str) -> pd.DataFrame:
    """
    Estrae dati FIT in DataFrame con validazione.
    
    Args:
        file_path: Percorso al file FIT
        
    Returns:
        DataFrame con colonne: time, power, altitude, distance, heartrate, grade, cadence, 
        position_lat, position_long, time_sec, distance_km
        
    Raises:
        FileNotFoundError: Se il file non esiste
        ValueError: Se il file è corrotto o vuoto
    """
    import os
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File FIT non trovato: {file_path}")
    
    try:
        fit = FitFile(file_path)
        logger.info(f"Parsing FIT file: {file_path}")
    except Exception as e:
        raise ValueError(f"Errore apertura file FIT: {str(e)}")
    
    data = {
        "time": [], "power": [], "altitude": [], "distance": [], 
        "heartrate": [], "grade": [], "cadence": [],
        "position_lat": [], "position_long": []
    }
    
    record_count = 0
    try:
        for record in fit.get_messages("record"):
            vals = {f.name: f.value for f in record}
            data["time"].append(vals.get("timestamp"))
            data["power"].append(vals.get("power"))
            data["altitude"].append(vals.get("enhanced_altitude"))
            data["distance"].append(vals.get("distance"))
            data["heartrate"].append(vals.get("heart_rate"))
            data["grade"].append(vals.get("grade"))
            data["cadence"].append(vals.get("cadence"))
            data["position_lat"].append(vals.get("position_lat"))
            data["position_long"].append(vals.get("position_long"))
            record_count += 1
    except Exception as e:
        raise ValueError(f"Errore durante parsing record: {str(e)}")
    
    if record_count == 0:
        raise ValueError("Nessun record trovato nel file FIT")
    
    logger.info(f"Importati {record_count} record")
    
    df = pd.DataFrame(data)
    
    # Validazione timestamp
    try:
        df["time"] = pd.to_datetime(df["time"], errors='coerce')
        if df["time"].isna().all():
            raise ValueError("Nessun timestamp valido trovato")
    except Exception as e:
        raise ValueError(f"Errore parsing timestamp: {str(e)}")
    
    # Riempimento intelligente con fallback
    df["power"] = pd.to_numeric(df["power"], errors='coerce').fillna(0).astype(int)
    df["heartrate"] = pd.to_numeric(df["heartrate"], errors='coerce').fillna(0).astype(int)
    df["cadence"] = pd.to_numeric(df["cadence"], errors='coerce').fillna(0).astype(int)
    
    # Distance con gestione NaN completi
    df["distance"] = pd.to_numeric(df["distance"], errors='coerce')
    if df["distance"].isna().all():
        logger.warning("Tutti i valori di distance sono NaN - impossibile calcolare distanze")
        df["distance"] = 0
    else:
        df["distance"] = df["distance"].ffill().fillna(0)
    
    df["grade"] = pd.to_numeric(df["grade"], errors='coerce').fillna(0)
    
    # Altitude con gestione NaN completi
    df["altitude"] = pd.to_numeric(df["altitude"], errors='coerce')
    if df["altitude"].isna().all():
        logger.warning("Tutti i valori di altitude sono NaN - impossibile calcolare elevazioni")
        df["altitude"] = 0
    else:
        df["altitude"] = df["altitude"].ffill().fillna(0)
    
    # GPS coordinates (possono non essere presenti per indoor)
    df["position_lat"] = pd.to_numeric(df["position_lat"], errors='coerce')
    df["position_long"] = pd.to_numeric(df["position_long"], errors='coerce')
    
    # Converti semicircles in gradi se necessario
    if df["position_lat"].notna().any() and df["position_lat"].abs().max() > 180:
        # Corretto: semicircles to degrees = value * (180 / (2^31 - 1))
        df["position_lat"] = df["position_lat"] * SEMICIRCLES_TO_DEGREES
        df["position_long"] = df["position_long"] * SEMICIRCLES_TO_DEGREES
        logger.info("Coordinate GPS convertite da semicircles a gradi")
    
    df["time_sec"] = (df["time"] - df["time"].iloc[0]).dt.total_seconds()
    df["distance_km"] = df["distance"] / 1000
    
    logger.info(f"DataFrame creato: {len(df)} righe")
    return df


def get_zone_color(avg_power: float, ftp: float) -> str:
    """Determina colore zona in base alla potenza
    
    Args:
        avg_power: Potenza media [W]
        ftp: Functional Threshold Power [W]
        
    Returns:
        Colore hex della zona
    """
    if ftp <= 0:
        return "#cccccc"  # grigio neutro
    
    perc = (avg_power / ftp) * 100
    
    # Gestione valori estremi
    if perc < 0:
        return "#cccccc"  # grigio per valori negativi
    
    for th, color, _ in ZONE_COLORS:
        if perc < th:
            return color
    
    # Valori > 999% FTP usano default
    return ZONE_DEFAULT[1]


# =====================
# FUNZIONI CORE - EFFORTS
# =====================

def trim_segment(power: np.ndarray, start: int, end: int, trim_win: int, trim_pct: float, 
                 max_iterations: int = 100) -> Tuple[int, int]:
    """Limatura inizio/fine di un segmento di potenza.
    
    Args:
        power: Array di potenza
        start: Indice inizio
        end: Indice fine
        trim_win: Finestra trim [samples]
        trim_pct: Percentuale soglia [%]
        max_iterations: Max iterazioni protezione infinite loop
        
    Returns:
        Tuple (start_trimmed, end_trimmed)
    """
    iterations = 0
    
    while iterations < max_iterations:
        iterations += 1
        changed = False
        
        if end - start < trim_win * 2:
            break
            
        seg = power[start:end]
        avg = seg.mean() if len(seg) > 0 else 0
        
        if avg <= 0:
            break

        # Trim inizio (con boundary check)
        # Verifica che la finestra non vada oltre l'array
        if start + trim_win < end:
            head_avg = power[start:start+trim_win].mean()
            if head_avg < avg * trim_pct / 100:
                start += trim_win
                changed = True

        # Trim fine (con boundary check)
        # Verifica che la finestra non vada oltre l'array
        if end - trim_win > start:
            tail_avg = power[end-trim_win:end].mean()
            if tail_avg < avg * trim_pct / 100:
                end -= trim_win
                changed = True

        if not changed:
            break
    
    if iterations >= max_iterations:
        logger.warning(f"trim_segment raggiunto max_iterations ({max_iterations})")
    
    return start, end


def create_efforts(df: pd.DataFrame, ftp: float, window_sec: int = 60, merge_pct: float = 15, 
                   min_ftp_pct: float = 100, trim_win: int = 10, trim_low: float = 85) -> List[Tuple[int, int, float]]:
    """Crea finestre, merge, trim, filtro FTP.
    
    Args:
        df: DataFrame con dati potenza
        ftp: Functional Threshold Power [W]
        window_sec: Dimensione finestra [s]
        merge_pct: Threshold merge [%]
        min_ftp_pct: Minima intensità [%FTP]
        trim_win: Finestra trim [s]
        trim_low: Soglia trim [%]
        
    Returns:
        Lista di tuple (start_idx, end_idx, avg_power)
        
    Raises:
        ValueError: Se parametri invalidi
    """
    if ftp <= 0:
        raise ValueError(f"FTP non valida: {ftp}")
    if window_sec <= 0:
        raise ValueError(f"window_sec non valido: {window_sec}")
    if min_ftp_pct < 0 or min_ftp_pct > 300:
        raise ValueError(f"min_ftp_pct fuori range: {min_ftp_pct}")
    
    power = df["power"].values
    n = len(power)
    windows = []
    i = 0
    
    while i + window_sec <= n:
        seg = power[i:i+window_sec]
        windows.append((i, i+window_sec, seg.mean()))
        i += window_sec

    merged = []
    idx = 0
    
    while idx < len(windows):
        s, e, avg = windows[idx]
        tot = avg * window_sec
        length = window_sec
        j = idx + 1
        
        while j < len(windows):
            s2, e2, avg2 = windows[j]
            diff = abs(avg2 - avg) / avg * 100 if avg > 0 else 0
            if diff <= merge_pct:
                tot += avg2 * window_sec
                length += window_sec
                avg = tot / length
                e = e2
                j += 1
            else:
                break
        
        s_trim, e_trim = trim_segment(power, s, e, trim_win, trim_low)
        avg_trim = power[s_trim:e_trim].mean() if e_trim > s_trim else 0
        
        if avg_trim > ftp * min_ftp_pct / 100:
            merged.append((s_trim, e_trim, avg_trim))
        
        idx = j
    
    logger.info(f"Creati {len(merged)} efforts")
    return merged


def merge_extend(df: pd.DataFrame, efforts: List[Tuple[int, int, float]], 
                 merge_pct: float = 15, trim_win: int = 10, trim_low: float = 85, 
                 extend_win: int = 15, extend_low: float = 80) -> List[Tuple[int, int, float]]:
    """Merge + estensione iterativa
    
    Args:
        df: DataFrame con dati power
        efforts: Lista di tuple (start, end, avg_power)
        merge_pct: Percentuale differenza potenza per merge
        trim_win: Finestra trim [s]
        trim_low: Soglia trim [%]
        extend_win: Finestra estensione [s]
        extend_low: Soglia estensione [%]
        
    Returns:
        Lista di efforts dopo merge/extend
    """
    power = df["power"].values
    changed = True
    
    while changed:
        changed = False
        new_eff = []
        efforts.sort(key=lambda x: x[0])
        i = 0
        
        while i < len(efforts):
            s, e, avg = efforts[i]
            j = i + 1
            
            while j < len(efforts) and efforts[j][0] < e:
                s2, e2, avg2 = efforts[j]
                diff = abs(avg2 - avg) / ((avg + avg2) / 2) * 100 if avg > 0 else 0
                if diff <= merge_pct:
                    s = min(s, s2)
                    e = max(e, e2)
                    avg = power[s:e].mean()
                    j += 1
                else:
                    break
            
            # Extend front
            while s - extend_win >= 0:
                ext = power[s-extend_win:s].mean()
                if ext >= avg * extend_low / 100:
                    s -= extend_win
                    avg = power[s:e].mean()
                else:
                    break
            
            # Extend back
            while e + extend_win <= len(power):
                ext = power[e:e+extend_win].mean()
                if ext >= avg * extend_low / 100:
                    e += extend_win
                    avg = power[s:e].mean()
                else:
                    break
            
            s_trim, e_trim = trim_segment(power, s, e, trim_win, trim_low)
            avg_trim = power[s_trim:e_trim].mean() if e_trim > s_trim else 0
            new_eff.append((s_trim, e_trim, avg_trim))
            i = j
        
        if new_eff != efforts:
            changed = True
        efforts = new_eff
    
    return efforts


def split_included(df: pd.DataFrame, efforts: List[Tuple[int, int, float]]) -> List[Tuple[int, int, float]]:
    """Split se un effort è contenuto in un altro
    
    Args:
        df: DataFrame con dati power
        efforts: Lista di tuple (start, end, avg_power)
        
    Returns:
        Lista di efforts modificati dopo split
    """
    power = df["power"].values
    sorted_efforts = sorted(efforts, key=lambda x: x[0])  # Create sorted copy
    changed = True
    
    while changed:
        changed = False
        # Create a copy to avoid mutation during iteration
        current_efforts = list(sorted_efforts)
        
        for i in range(len(current_efforts)):
            if changed:  # Exit early if we've made a change
                break
                
            for j in range(len(current_efforts)):
                if i == j:
                    continue
                
                s, e, avg = current_efforts[i]
                s2, e2, avg2 = current_efforts[j]
                
                # j completamente dentro i
                if s < s2 and e2 < e:
                    new_efforts = []
                    
                    # Prima di j
                    if s2 > s:
                        pow1 = power[s:s2]
                        if len(pow1) > 0:
                            new_efforts.append((s, s2, pow1.mean()))
                    
                    # j stesso
                    new_efforts.append((s2, e2, avg2))
                    
                    # Dopo j
                    if e2 < e:
                        pow2 = power[e2:e]
                        if len(pow2) > 0:
                            new_efforts.append((e2, e, pow2.mean()))
                    
                    # Rimuovi i e j, aggiungi nuovi
                    sorted_efforts = [eff for k, eff in enumerate(current_efforts) if k != i and k != j]
                    sorted_efforts.extend(new_efforts)
                    sorted_efforts.sort(key=lambda x: x[0])
                    changed = True
                    break
    
    return sorted_efforts


# =====================
# FUNZIONI CORE - SPRINTS
# =====================

def detect_sprints(df: pd.DataFrame, min_power: float, min_duration_sec: float, 
                   merge_gap_sec: float = 1.0) -> List[Dict[str, Any]]:
    """
    Rilevamento sprint dinamici - Rileva blocchi di potenza sopra min_power e li unisce se vicini.
    
    Args:
        df: DataFrame con dati potenza
        min_power: Potenza minima per sprint [W]
        min_duration_sec: Durata minima sprint [s]
        merge_gap_sec: Gap massimo per merge [s]
        
    Returns:
        Lista di dizionari {start, end, avg} per ogni sprint
        
    Raises:
        ValueError: Se parametri invalidi
    """
    if min_power <= 0:
        raise ValueError(f"min_power non valida: {min_power}")
    if min_duration_sec <= 0:
        raise ValueError(f"min_duration_sec non valida: {min_duration_sec}")
    
    power = df["power"].values
    time_sec = df["time_sec"].values
    
    above_threshold = power >= min_power
    sprints = []
    i = 0
    
    while i < len(above_threshold):
        if above_threshold[i]:
            start = i
            while i < len(above_threshold) and above_threshold[i]:
                i += 1
            end = i
            
            if end > start:
                durata = time_sec[end-1] - time_sec[start]
                if durata >= min_duration_sec:
                    sprints.append({
                        'start': start, 
                        'end': end, 
                        'avg': np.mean(power[start:end])
                    })
        else:
            i += 1
    
    if not sprints:
        logger.info("Nessuno sprint rilevato")
        return []

    # Unisce sprint con gap temporale piccolo
    merged = []
    curr = sprints[0]
    
    for nxt in sprints[1:]:
        gap = time_sec[nxt['start']] - time_sec[curr['end']-1]
        if gap <= merge_gap_sec:
            new_start = curr['start']
            new_end = nxt['end']
            curr = {
                'start': new_start, 
                'end': new_end, 
                'avg': np.mean(power[new_start:new_end])
            }
        else:
            merged.append(curr)
            curr = nxt
    
    merged.append(curr)
    logger.info(f"Rilevati {len(merged)} sprint")
    return merged
