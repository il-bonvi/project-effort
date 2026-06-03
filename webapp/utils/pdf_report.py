"""
pdf_report.py — PEFFORT PDF Report Generator

Layout per ogni effort/sprint:
  - Pagina 1: Altimetria + lista sommario efforts + lista sommario sprints
  - Pagine successive: per ogni effort/sprint
      [sinistra] scheda dettaglio metriche
      [destra]   grafico stream (potenza raw + altimetria / oppure power+cadence per sprint)
"""

from __future__ import annotations

import io
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ── Matplotlib (backend non-interattivo) ──────────────────────────────────────
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import to_rgba
from matplotlib.lines import Line2D

# ── ReportLab ─────────────────────────────────────────────────────────────────
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable, KeepTogether
)
from reportlab.platypus.flowables import Flowable
from reportlab.graphics.shapes import Drawing, Rect, String, PolyLine, Group, Path
from reportlab.graphics import renderPDF


# ══════════════════════════════════════════════════════════════════════════════
# COSTANTI COLORI & STILE
# ══════════════════════════════════════════════════════════════════════════════

PAGE_W, PAGE_H = landscape(A4)   # 297 × 210 mm landscape
MARGIN = 15 * mm
INNER_W = PAGE_W - 2 * MARGIN
INNER_H = PAGE_H - 2 * MARGIN

DEFAULT_ZONES = [
    {"min": 0,   "max": 60,  "color": "#009e80", "name": "Z1"},
    {"min": 60,  "max": 80,  "color": "#009e00", "name": "Z2"},
    {"min": 80,  "max": 90,  "color": "#ffcb0e", "name": "Z3"},
    {"min": 90,  "max": 105, "color": "#ff7f0e", "name": "Z4"},
    {"min": 105, "max": 135, "color": "#dd0447", "name": "Z5"},
    {"min": 135, "max": 300, "color": "#6633cc", "name": "Z6"},
    {"min": 300, "max": 999, "color": "#504861", "name": "Z7"},
]

COL_BG   = colors.HexColor("#1e293b")
COL_CARD = colors.HexColor("#0f172a")
COL_TEXT = colors.HexColor("#e2e8f0")
COL_MUTED= colors.HexColor("#94a3b8")
COL_BLUE = colors.HexColor("#60a5fa")
COL_YEL  = colors.HexColor("#fbbf24")
COL_GRN  = colors.HexColor("#22c55e")
COL_RED  = colors.HexColor("#ef4444")


# ══════════════════════════════════════════════════════════════════════════════
# UTILITY
# ══════════════════════════════════════════════════════════════════════════════

def fmt_dur(seconds: float) -> str:
    s = int(round(seconds or 0))
    m, r = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {r}s"
    if m:
        return f"{m}m {r}s"
    return f"{s}s"


def zone_color_for_power(watts: float, cp: float, zones=None) -> str:
    if zones is None:
        zones = DEFAULT_ZONES
    if cp <= 0:
        return "#6b7280"
    pct = watts / cp * 100
    for z in zones:
        if pct >= z["min"] and (z["max"] == 999 or pct < z["max"]):
            return z["color"]
    return "#6b7280"


def moving_avg(data: List[float], time_data: List[float], window_sec: float) -> List[float]:
    """Centered time-based moving average."""
    n = len(data)
    if n == 0:
        return []
    result = [0.0] * n
    lo = hi = 0
    s = 0.0
    for i in range(n):
        center = time_data[i]
        win_lo = center - window_sec / 2
        win_hi = center + window_sec / 2
        while hi < n and time_data[hi] <= win_hi:
            s += data[hi]
            hi += 1
        while lo < hi and time_data[lo] < win_lo:
            s -= data[lo]
            lo += 1
        cnt = hi - lo
        result[i] = s / cnt if cnt > 0 else data[i]
    return result


def mpl_fig_to_rl_image(fig, width_pt: float, height_pt: float) -> Image:
    """Convert matplotlib figure → ReportLab Image at given pt dimensions."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    img = Image(buf, width=width_pt, height=height_pt)
    plt.close(fig)
    return img


# ══════════════════════════════════════════════════════════════════════════════
# STYLES
# ══════════════════════════════════════════════════════════════════════════════

def build_styles():
    base = getSampleStyleSheet()
    styles = {}

    def ps(name, **kw):
        return ParagraphStyle(name, **kw)

    styles["title"] = ps("RPTitle",
        fontName="Helvetica-Bold", fontSize=18, textColor=COL_BLUE,
        spaceAfter=4)
    styles["subtitle"] = ps("RPSub",
        fontName="Helvetica", fontSize=10, textColor=COL_MUTED,
        spaceAfter=8)
    styles["h2"] = ps("RPH2",
        fontName="Helvetica-Bold", fontSize=12, textColor=COL_BLUE,
        spaceBefore=8, spaceAfter=4)
    styles["h3"] = ps("RPH3",
        fontName="Helvetica-Bold", fontSize=10, textColor=COL_YEL,
        spaceBefore=6, spaceAfter=2)
    styles["body"] = ps("RPBody",
        fontName="Helvetica", fontSize=8, textColor=COL_TEXT,
        spaceAfter=2)
    styles["small"] = ps("RPSmall",
        fontName="Helvetica", fontSize=7, textColor=COL_MUTED,
        spaceAfter=1)
    styles["label"] = ps("RPLabel",
        fontName="Helvetica", fontSize=7, textColor=COL_MUTED)
    styles["value"] = ps("RPValue",
        fontName="Helvetica-Bold", fontSize=8, textColor=COL_YEL)
    return styles


# ══════════════════════════════════════════════════════════════════════════════
# ALTITUDE AXIS LIMITS — d3.js rules
# ══════════════════════════════════════════════════════════════════════════════

def _calculate_altitude_limits(altitude_data: List[Dict]) -> Tuple[float, float]:
    """
    Calculate Y-axis limits for altitude charts using d3.js rules.
    
    Rules from altimetria_d3.js:
    - paddingTop = 300 m
    - paddingBottom = 80 m (if minAlt >= 100) or minAlt * 0.5 (otherwise)
    - rangeY_base = max(elevationGain * 1.5, elevationGain + 300)
    - rangeY_final = rangeY_base + paddingBottom + paddingTop
    - Round all limits to nearest 50 m
    - yMin = floor((minAlt - paddingBottom) / 50) * 50
    - yMaxRaw = ceil((yMin + rangeY_final) / 50) * 50
    - yMaxCap = ceil((maxAlt + paddingTop) / 50) * 50
    - yMax = min(yMaxRaw, yMaxCap)
    
    Args:
        altitude_data: List of dicts with 'alt' key
    
    Returns:
        (yMin, yMax) tuple for matplotlib ax.set_ylim()
    """
    if not altitude_data:
        return (0, 1000)
    
    alts = [p.get("alt", 0) for p in altitude_data]
    if not alts:
        return (0, 1000)
    
    min_alt = min(alts)
    max_alt = max(alts)
    elevation_gain = max_alt - min_alt
    
    padding_top = 300
    padding_bottom = 80 if min_alt >= 100 else max(0, min_alt * 0.5)
    
    range_y_base = max(elevation_gain * 1.5, elevation_gain + 300)
    range_y_final = range_y_base + padding_bottom + padding_top
    
    round_to = 50
    y_min = math.floor((min_alt - padding_bottom) / round_to) * round_to
    y_max_raw = math.ceil((y_min + range_y_final) / round_to) * round_to
    y_max_cap = math.ceil((max_alt + padding_top) / round_to) * round_to
    y_max = min(y_max_raw, y_max_cap)
    
    return (y_min, y_max)


# ══════════════════════════════════════════════════════════════════════════════
# ALTIMETRIA CHART  (matplotlib)
# ══════════════════════════════════════════════════════════════════════════════

def build_altimetry_chart(chart_data: Dict, width_pt: float, height_pt: float,
                          zones=None) -> Image:
    """Render the elevation profile with colored effort/sprint segments."""
    if zones is None:
        zones = DEFAULT_ZONES

    elev_data = chart_data.get("elevation_data", [])
    efforts   = chart_data.get("efforts", [])
    sprints   = chart_data.get("sprints", [])

    if not elev_data:
        fig, ax = plt.subplots(figsize=(width_pt/72, height_pt/72))
        ax.text(0.5, 0.5, "No elevation data", ha="center", va="center",
                color="white", transform=ax.transAxes)
        fig.patch.set_facecolor("#1e293b")
        ax.set_facecolor("#1e293b")
        return mpl_fig_to_rl_image(fig, width_pt, height_pt)

    dists = [p["dist"] for p in elev_data]
    alts  = [p["alt"]  for p in elev_data]

    fig, ax = plt.subplots(figsize=(width_pt / 72, height_pt / 72))
    fig.patch.set_facecolor("#1e293b")  # Sfondo esterno della pagina
    ax.set_facecolor("#0f172a")        # Contenitore interno del grafico scuro (Dashboard)

    # Applichiamo i limiti geometrici verticali secondo le regole d3.js del tuo file
    y_min, y_max = _calculate_altitude_limits(elev_data)
    ax.set_ylim(y_min, y_max)

    # --- EFFETTO SOLID/GRADIENT ANCORATO AL TERRENO (D3 Style) ---
    ax.fill_between(dists, alts, y_min, color="#334155", alpha=0.45, linewidth=0, zorder=1)
    
    # Linea di cresta dell'altimetria
    ax.plot(dists, alts, color="#cbd5e1", linewidth=1.2, zorder=2)

    # --- CORREZIONE ASSE X: ELIMINAZIONE PADDING AUTOMATICO ---
    # Forza l'inizio del grafico sul primo punto e la fine sull'ultimo punto della distanza
    if dists:
        ax.set_xlim(min(dists), max(dists))

    # Stilizzazione assi e cornice geometrica pulita
    for spine in ax.spines.values():
        spine.set_edgecolor("#334155")
        spine.set_linewidth(0.6)
        
    ax.grid(axis="y", color="#334155", linewidth=0.4, alpha=0.5, zorder=0)
    ax.tick_params(colors="#9ca3af", labelsize=6)

    # Effort segments
    for e in efforts:
        ld = e.get("line_data", [])
        if not ld:
            continue
        xs = [p[0] for p in ld]
        ys = [p[1] for p in ld]
        ax.plot(xs, ys, color=e.get("color", "#60a5fa"),
                linewidth=3.5, solid_capstyle="round", zorder=3)
        # Label
        mid = len(xs) // 2
        ax.annotate(
            f"E#{e['id']+1}",
            xy=(xs[mid], ys[mid]),
            xytext=(0, 8), textcoords="offset points",
            fontsize=6, color="white",
            ha="center", va="bottom",
            bbox=dict(boxstyle="round,pad=0.2", fc=e.get("color", "#60a5fa"),
                      alpha=0.85, ec="none"),
        )

    # Sprint segments
    for s in sprints:
        ld = s.get("line_data", [])
        if not ld:
            continue
        xs = [p[0] for p in ld]
        ys = [p[1] for p in ld]
        ax.plot(xs, ys, color="#000000", linewidth=3.5,
                solid_capstyle="round", zorder=3)
        mid = len(xs) // 2
        ax.annotate(
            f"S#{s['rank']}",
            xy=(xs[mid], ys[mid]),
            xytext=(0, 8), textcoords="offset points",
            fontsize=6, color="white",
            ha="center", va="bottom",
            bbox=dict(boxstyle="round,pad=0.2", fc="#374151",
                      alpha=0.85, ec="none"),
        )

    ax.set_xlabel("Distance (km)", fontsize=7, color="#9ca3af")
    ax.set_ylabel("Altitude (m)", fontsize=7, color="#9ca3af")
    ax.tick_params(colors="#9ca3af", labelsize=6)

    fig.tight_layout(pad=0.4)
    return mpl_fig_to_rl_image(fig, width_pt, height_pt)


# ══════════════════════════════════════════════════════════════════════════════
# STREAM CHART  (matplotlib)
# ══════════════════════════════════════════════════════════════════════════════

def build_stream_chart(segment: Dict, cp: float, width_pt: float, height_pt: float,
                       zones=None, altitude_data: Optional[List[Dict]] = None,
                       elevation_data: Optional[List[Dict]] = None) -> Image:
    """
    For efforts with altitude_data: 2-panel (raw power + altitude with full track highlighted).
    For efforts without altitude_data: 2-panel (raw power + altitude, full track).
    For sprints: 2-panel (power / cadence+torque).
    """
    if zones is None:
        zones = DEFAULT_ZONES

    is_sprint = segment.get("type") == "sprint" if "type" in segment else False
    # detect sprint by absence of 'id' field starting from 0 with rank
    if not is_sprint and "rank" in segment and "avg_power" not in segment:
        is_sprint = True

    time_s  = segment.get("time_stream", [])
    pow_s   = segment.get("power_stream", [])
    hr_s    = segment.get("hr_stream", [])
    cad_s   = segment.get("cadence_stream", [])
    tor_s   = segment.get("torque_stream", [])
    spd_s   = segment.get("speed_stream", [])

    if not time_s or not pow_s:
        fig, ax = plt.subplots(figsize=(width_pt/72, height_pt/72))
        ax.text(0.5, 0.5, "No stream data", ha="center", va="center",
                color="white", transform=ax.transAxes)
        fig.patch.set_facecolor("#1e293b")
        ax.set_facecolor("#1e293b")
        return mpl_fig_to_rl_image(fig, width_pt, height_pt)

    e_start = segment.get("stream_effort_start", 0)
    e_end   = segment.get("stream_effort_end",   time_s[-1] if time_s else 0)

    # Filter to effort window only (no buffer)
    mask = [e_start <= t <= e_end for t in time_s]
    t_arr  = [t for t, m in zip(time_s, mask) if m]
    p_arr  = [p for p, m in zip(pow_s, mask)  if m]
    hr_arr = [h for h, m in zip(hr_s or [None]*len(time_s), mask) if m] if hr_s else []
    cad_arr= [c for c, m in zip(cad_s or [None]*len(time_s), mask) if m] if cad_s else []
    tor_arr= [tr for tr, m in zip(tor_s or [None]*len(time_s), mask) if m] if tor_s else []

    if not t_arr:
        t_arr = list(time_s)
        p_arr = list(pow_s)

    # ── Sprint: 2-panel ──────────────────────────────────────────────────────
    if is_sprint:
        n_panels = 2
        fig, axes = plt.subplots(n_panels, 1, figsize=(width_pt/72, height_pt/72),
                                 sharex=True)
        fig.patch.set_facecolor("#1e293b")

        ax_pow, ax_cad = axes

        # Limiti esatti per l'asse X (inizio e fine perfetti sul tempo reale)
        t_start = t_arr[0]
        t_end = t_arr[-1]

        # Power panel
        ax_pow.set_facecolor("#0f172a")
        
        # Calcolo limiti dinamici per la Potenza
        max_p = max(p_arr) if len(p_arr) > 0 else 100
        min_p = min(p_arr) if len(p_arr) > 0 else 0
        p_range = max_p - min_p
        p_bottom = max(0, min_p - p_range * 0.1)
        p_top = max_p + (p_range * 0.1 if p_range > 0 else max_p * 0.1)
        
        ax_pow.fill_between(t_arr, p_arr, p_bottom, alpha=0.3, color="#3b82f6")
        ax_pow.plot(t_arr, p_arr, color="#3b82f6", linewidth=1.2)
        
        ax_pow.set_xlim(t_start, t_end)
        ax_pow.set_ylim(p_bottom, p_top)
        
        ax_pow.set_ylabel("W", fontsize=6, color="#3b82f6")
        ax_pow.tick_params(colors="#9ca3af", labelsize=5, which='both', left=False)
        ax_pow.grid(color="#334155", linewidth=0.3, alpha=0.5)
        ax_pow.set_title("Power", fontsize=7, color="#60a5fa", pad=2)

        # Rimozione bordi per il pannello Power
        ax_pow.spines['top'].set_visible(False)
        ax_pow.spines['left'].set_visible(False)
        ax_pow.spines['right'].set_visible(False)
        ax_pow.spines['bottom'].set_visible(False)

        # Cadence + Torque panel
        ax_cad.set_facecolor("#0f172a")
        cad_clean = [c if c and c > 0 else None for c in cad_arr]
        tor_clean = [tr if tr and tr > 0 else None for tr in tor_arr]

        # Gestione Cadence con smussamento (Media mobile a 3 punti)
        valid_c = [c for c in cad_clean if c is not None]
        if valid_c:
            c_arr_filled = [c or 0 for c in cad_clean]
            if len(c_arr_filled) >= 3:
                c_smoothed = np.convolve(c_arr_filled, np.ones(3)/3, mode='same')
                c_smoothed[0] = c_arr_filled[0]
                c_smoothed[-1] = c_arr_filled[-1]
            else:
                c_smoothed = c_arr_filled

            max_c = max(c_smoothed)
            min_c = min(c_smoothed)
            c_range = max_c - min_c
            c_bottom = max(0, min_c - c_range * 0.1)
            c_top = max_c + (c_range * 0.1 if c_range > 0 else max_c * 0.1)
            
            ax_cad.fill_between(t_arr, c_smoothed, c_bottom, alpha=0.25, color="#10b981")
            ax_cad.plot(t_arr, c_smoothed, color="#10b981", linewidth=1.2, label="rpm")
            
            ax_cad.set_xlim(t_start, t_end)
            ax_cad.set_ylim(c_bottom, c_top)
            
            # Forziamo Matplotlib a usare solo numeri interi per i tick della Cadenza
            ax_cad.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))

        # Gestione Torque
        valid_t = [tr for tr in tor_clean if tr is not None]
        if valid_t:
            ax_tor = ax_cad.twinx()
            max_t = max(valid_t)
            min_t = min(valid_t)
            t_range = max_t - min_t
            t_bottom = max(0, min_t - t_range * 0.1)
            t_top = max_t + (t_range * 0.1 if t_range > 0 else max_t * 0.1)
            
            ax_tor.plot(t_arr, [tr or 0 for tr in tor_clean],
                        color="#f59e0b", linewidth=1.2,
                        linestyle="--", label="Nm")
            ax_tor.set_ylim(t_bottom, t_top)
            ax_tor.set_ylabel("Nm", fontsize=6, color="#f59e0b")
            ax_tor.tick_params(colors="#f59e0b", labelsize=5, which='both', right=False)
            
            # Forziamo anche la coppia a numeri interi per coerenza
            ax_tor.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
            
            ax_tor.spines['top'].set_visible(False)
            ax_tor.spines['left'].set_visible(False)
            ax_tor.spines['right'].set_visible(False)
            ax_tor.spines['bottom'].set_color("#334155")

        ax_cad.set_ylabel("rpm", fontsize=6, color="#10b981")
        ax_cad.set_xlabel("Time (s)", fontsize=6, color="#9ca3af")
        ax_cad.tick_params(colors="#9ca3af", labelsize=5, which='both', left=False)
        ax_cad.grid(color="#334155", linewidth=0.3, alpha=0.5)
        ax_cad.set_title("Cadence / Torque", fontsize=7, color="#10b981", pad=2)

        # Allineamento perfetto e rimozione bordi sul pannello inferiore
        ax_cad.spines['top'].set_visible(False)
        ax_cad.spines['left'].set_visible(False)
        ax_cad.spines['right'].set_visible(False)
        ax_cad.spines['bottom'].set_color("#334155")

        fig.tight_layout(pad=0.4, h_pad=0.8)
        return mpl_fig_to_rl_image(fig, width_pt, height_pt)
    
    # ── Effort: Raw Power + Altitude (with full track highlighted) ─────────
    fig, axes = plt.subplots(2, 1, figsize=(width_pt/72, height_pt/72), sharex=False)
    fig.patch.set_facecolor("#1e293b")
    
    ax_pow, ax_alt = axes
    
    # Panel 1: Raw Power with zone coloring + HR overlay
    ax_pow.set_facecolor("#0f172a")
    for sp in ax_pow.spines.values():
        sp.set_edgecolor("#334155")
    ax_pow.grid(color="#334155", linewidth=0.3, alpha=0.5, zorder=0)
    ax_pow.tick_params(colors="#9ca3af", labelsize=5)
    ax_pow.set_title("Raw Power", fontsize=7, color="#3b82f6", pad=4)
    ax_pow.set_ylabel("W", fontsize=6, color="#9ca3af")
    ax_pow.set_xlabel("Time (s)", fontsize=6, color="#9ca3af")  # <-- Correzione 1: Asse X aggiunto

    # --- SMOOTHING DELLA POTENZA (Media mobile a 3 secondi) ---
    p_arr_smooth = moving_avg(p_arr, t_arr, window_sec=3) if p_arr else []
    if not p_arr_smooth:
        p_arr_smooth = list(p_arr)

    max_p = max(v for v in p_arr_smooth if v is not None) if p_arr_smooth else 1
    y_limit = max(max_p * 1.10, cp * 1.35)

    # --- DISEGNO STRATI DELLE ZONE (Meno trasparenti) ---
    for zone in zones:
        min_w = (zone["min"] / 100) * cp
        max_w_z = (zone["max"] / 100) * cp if zone["max"] != 999 else y_limit * 2
        # Alpha alzato a 0.70 come piace a te
        ax_pow.axhspan(min_w, max_w_z, facecolor=zone["color"], alpha=0.70, zorder=1)

    # --- CONFIGURAZIONE DOPPIA GRIGLIA (25W e 100W) AD ALTA VISIBILITÀ ---
    import matplotlib.ticker as ticker
    
    # Attiviamo esplicitamente i minor ticks sul grafico, altrimenti Matplotlib potrebbe ignorare la griglia secondaria
    ax_pow.minorticks_on()
    
    # Impostiamo i passaggi: 100W principali, 25W secondari
    ax_pow.yaxis.set_major_locator(ticker.MultipleLocator(100))
    ax_pow.yaxis.set_minor_locator(ticker.MultipleLocator(25))

    # 1. Griglia secondaria (ogni 25W): colore chiaro (#94a3b8), solida (alpha=1.0) ma sottile (0.45)
    ax_pow.grid(axis="y", which="minor", color="#94a3b8", linewidth=0.45, alpha=1.0, zorder=1.1)
    
    # 2. Griglia principale (ogni 100W): stessa tonalità ma molto più spessa (1.0) per staccare visivamente
    ax_pow.grid(axis="y", which="major", color="#94a3b8", linewidth=1.0, alpha=1.0, zorder=1.2)

    # Pulizia: disattiviamo i minorticks sull'asse X (perché non ci servono) e nascondiamo i trattini neri a sinistra
    ax_pow.tick_params(axis="x", which="minor", bottom=False)
    ax_pow.tick_params(axis="y", which="minor", left=False)

    # Maschera scura sopra la linea di potenza per nascondere i colori non raggiunti
    ax_pow.fill_between(t_arr, p_arr_smooth, y_limit, color="#0f172a", zorder=2)

    # --- Correzione 3: ASSI E LIVELLAMENTO FREQUENZA CARDIACA (HR) ---
    hr_valid = [h for h in hr_arr if h is not None and h > 0] if hr_arr else []
    if hr_valid:
        t_hr_valid = [t for t, h in zip(t_arr, hr_arr) if h is not None and h > 0]
        # Smoothing morbido a 5 secondi per la linea cardiaca
        hr_smooth = moving_avg(hr_valid, t_hr_valid, window_sec=5)
        
        ax2 = ax_pow.twinx()
        ax2.plot(t_hr_valid, hr_smooth, color="#ef4444", linewidth=1.2, zorder=4, alpha=0.85)
        ax2.set_ylabel("bpm", fontsize=5, color="#ef4444")
        ax2.tick_params(colors="#ef4444", labelsize=4)
        ax2.set_ylim(min(hr_smooth) - 5, max(hr_smooth) + 5)
        ax2.spines['right'].set_edgecolor("#334155")
        ax2.grid(False) # Impedisce la sovrapposizione di griglie

    # Linea di riferimento CP
    if cp > 0:
        ax_pow.axhline(cp, color="#f59e0b", linewidth=0.8, linestyle="--", alpha=0.8, zorder=5)
        ax_pow.text(t_arr[0], cp * 1.03, f"CP {int(cp)}W", color="#f59e0b", fontsize=4.5, ha="left", zorder=6)

    ax_pow.set_ylim(0, y_limit)
    ax_pow.set_xlim(min(t_arr), max(t_arr))
    
    # Panel 2: Altitude profile - full track with effort highlighted
    ax_alt.set_facecolor("#0f172a")
    
    # --- CORREZIONE ASSE X: ELIMINAZIONE PADDING AUTOMATICO ---
    altitude_for_limits = elevation_data if (elevation_data and len(elevation_data) > 0) else altitude_data
    if altitude_for_limits:
        # Forza l'inizio del grafico sul primo punto e la fine sull'ultimo punto della distanza
        ax_alt.set_xlim(altitude_for_limits[0]["dist"], altitude_for_limits[-1]["dist"])
    
    # Draw full track in grey
    if elevation_data and len(elevation_data) > 0:
        full_dists = [p["dist"] for p in elevation_data]
        full_alts  = [p["alt"]  for p in elevation_data]
        
        # Calcoliamo i limiti Y temporaneamente per gestire correttamente l'altezza del fill
        y_min_tmp, _ = _calculate_altitude_limits(altitude_for_limits) if altitude_for_limits else (0, 100)
        
        # --- CORREZIONE SPAZIO VUOTO SOTTO ---
        # Facciamo scendere il fondo del riempimento grigio oltre il limite dell'asse per ancorarlo perfettamente a terra
        ax_alt.fill_between(full_dists, full_alts, y_min_tmp - 500, alpha=0.25,
                            color="#9ca3af", linewidth=0)
        ax_alt.plot(full_dists, full_alts, color="#9ca3af", linewidth=0.8)
    
    # Highlight effort segment in color
    if altitude_data and len(altitude_data) > 0:
        effort_dists = [p["dist"] for p in altitude_data]
        effort_alts  = [p["alt"]  for p in altitude_data]
        effort_color = segment.get("color", "#60a5fa")
        ax_alt.plot(effort_dists, effort_alts, color=effort_color, linewidth=2.5,
                    solid_capstyle="round", zorder=3)
    
    ax_alt.set_xlabel("Distance (km)", fontsize=6, color="#9ca3af")
    ax_alt.set_ylabel("Altitude (m)", fontsize=6, color="#9ca3af")
    
    # 'left=False' rimuove i trattini fisici sporgenti a sinistra dei numeri Y
    ax_alt.tick_params(colors="#9ca3af", labelsize=5, which='both', left=False)
    ax_alt.set_title("Altitude Profile", fontsize=7, color="#10b981", pad=2)
    
    # ── STILIZZAZIONE ASSI E RIMOZIONE BORDI (SPINES) COERENTE ────────────────
    # Nasconde sopra, destra e sinistra; mantiene solo la retta inferiore colorata
    ax_alt.spines['top'].set_visible(False)
    ax_alt.spines['left'].set_visible(False)
    ax_alt.spines['right'].set_visible(False)
    ax_alt.spines['bottom'].set_color("#334155")
    
    ax_alt.grid(axis="y", color="#334155", linewidth=0.3, alpha=0.5)
    
    # Apply d3.js altitude limits rules (prioritize full track if available)
    if altitude_for_limits:
        y_min, y_max = _calculate_altitude_limits(altitude_for_limits)
        ax_alt.set_ylim(y_min, y_max)
        
        # Forza la visualizzazione dei valori a soli numeri interi senza decimali (.0)
        ax_alt.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    
    fig.tight_layout(pad=0.4, h_pad=0.6)
    return mpl_fig_to_rl_image(fig, width_pt, height_pt)


# ══════════════════════════════════════════════════════════════════════════════
# METRIC TABLE  helpers
# ══════════════════════════════════════════════════════════════════════════════

def _metric_row(label: str, value: str, styles) -> List:
    return [
        Paragraph(label, styles["label"]),
        Paragraph(str(value), styles["value"]),
    ]


def _section_row(title: str, styles) -> List:
    return [
        Paragraph(f"<b>{title}</b>", ParagraphStyle(
            "sec", fontName="Helvetica-Bold", fontSize=7,
            textColor=COL_BLUE, spaceBefore=3, spaceAfter=1)),
        Paragraph("", styles["label"]),
    ]


def build_effort_metrics_table(e: Dict, cp: float, styles) -> Table:
    """Build a 2-col metrics table for one effort."""
    show_vam = float(e.get("avg_grade", 0)) >= 4.5

    rows = []
    rows.append(_section_row("General", styles))
    rows.append(_metric_row("Rank",        f"#{e.get('rank', '?')}", styles))
    rows.append(_metric_row("Start",        e.get("start_time", ""), styles))
    rows.append(_metric_row("Duration",     fmt_dur(e.get("duration", 0)), styles))
    rows.append(_metric_row("Distance",     f"{e.get('distance_tot', 0)} km", styles))
    rows.append(_metric_row("Elevation",    f"{e.get('elevation_gain', 0)} m", styles))

    rows.append(_section_row("Power", styles))
    
    avg_p = int(float(e.get('avg_power', 0)))
    rows.append(_metric_row("Avg Power",    f"{avg_p} W  ({e.get('avg_power_per_kg', 0)} W/kg)  [{e.get('cp_pct', 0)}%]", styles))
    
    best_5s = int(float(e.get('best_5s_watt', 0)))
    rows.append(_metric_row("5\" Peak",     f"{best_5s} W  ({e.get('best_5s_watt_kg', 0)} W/kg)", styles))
    
    p1 = int(float(e.get('avg_watts_first', 0)))
    p2 = int(float(e.get('avg_watts_second', 0)))
    rows.append(_metric_row("1st | 2nd",    f"{p1} | {p2} W  ratio {e.get('watts_ratio', 0)}", styles))
    
    cadence = int(float(e.get('avg_cadence', 0)))
    rows.append(_metric_row("Cadence",      f"{cadence} rpm", styles))
    avg_hr = e.get("avg_hr", 0)
    max_hr = e.get("max_hr", 0)
    rows.append(_metric_row("HR (Avg|Max)", f"{int(avg_hr)} | {int(max_hr)} bpm" if avg_hr else "—", styles))

    rows.append(_section_row("Climb & Environment", styles))
    rows.append(_metric_row("Grade (Avg | Max)", f"{e.get('avg_grade', 0)}% | {e.get('max_grade', 0)}%", styles))
    rows.append(_metric_row("Speed",        f"{e.get('avg_speed', 0)} km/h", styles))
    
    vam_real = int(e.get('vam', 0))
    vam_teor = int(e.get('vam_teorico', 0))
    w_teor = e.get('wkg_teoric', 0)
    rows.append(_metric_row("VAM (Real | Teor | W/kg Teor)", f"{vam_real} | {vam_teor} m/h | {w_teor} W/kg", styles))

    rows.append(_section_row("Energy", styles))
    rows.append(_metric_row("kJ Total",     f"{int(e.get('kj', 0))} kJ", styles))
    rows.append(_metric_row("kJ > CP",      f"{int(e.get('kj_over_cp', 0))} kJ", styles))
    rows.append(_metric_row("kJ/kg",        str(e.get("kj_kg", 0)), styles))
    rows.append(_metric_row("kJ/kg > CP",   str(e.get("kj_kg_over_cp", 0)), styles))
    rows.append(_metric_row("kJ/h/kg",      str(e.get("kj_h_kg", 0)), styles))
    rows.append(_metric_row("kJ/h/kg > CP", str(e.get("kj_h_kg_over_cp", 0)), styles))

    col_w = [INNER_W * 0.22, INNER_W * 0.22]
    tbl = Table(rows, colWidths=col_w)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
        ("TEXTCOLOR",  (0, 0), (-1, -1), COL_TEXT),
        ("FONTSIZE",   (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1),
         [colors.HexColor("#0f172a"), colors.HexColor("#1e293b")]),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",   (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 1),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#334155")),
    ]))
    return tbl


def build_sprint_metrics_table(s: Dict, styles) -> Table:
    """Build a 2-col metrics table for one sprint."""
    rows = []
    
    # 1) GENERAL
    rows.append(_section_row("General", styles))
    rows.append(_metric_row("Rank",         f"#{s.get('rank', '?')}", styles))
    rows.append(_metric_row("Start",         s.get("start_time", ""), styles))
    rows.append(_metric_row("Duration",      fmt_dur(s.get("duration", 0)), styles))
    rows.append(_metric_row("Distance",      f"{s.get('distance_tot', 0)} km", styles))
    rows.append(_metric_row("Elevation",     f"{s.get('elevation_gain', 0)} m", styles))

    # 2) POWER & HEART RATE
    rows.append(_section_row("Power", styles))
    
    avg_p = int(float(s.get('avg_power', 0)))
    w_kg = s.get('avg_power_per_kg', 0)
    # Nel dizionario degli sprint potrebbe non esserci cp_pct, usiamo un fallback sicuro
    cp_pct = s.get('cp_pct', 0)
    rows.append(_metric_row("Avg Power",    f"{avg_p} W  ({w_kg} W/kg)  [{cp_pct}%]" if cp_pct else f"{avg_p} W  ({w_kg} W/kg)", styles))
    
    rows.append(_metric_row("Max Power",     f"{int(float(s.get('max_watt', 0)))} W  @ {int(float(s.get('rpm_at_max', 0)))} rpm", styles))
    rows.append(_metric_row("Min Power",     f"{int(float(s.get('min_watt', 0)))} W  @ {int(float(s.get('rpm_at_min', 0)))} rpm", styles))
    
    avg_hr = int(float(s.get('avg_hr', 0))) if s.get('avg_hr') else None
    min_hr = int(float(s.get('min_hr', 0)))
    max_hr = int(float(s.get('max_hr', 0)))
    if avg_hr:
        rows.append(_metric_row("HR (Avg | Max)", f"{avg_hr} | {max_hr} bpm", styles))
    else:
        rows.append(_metric_row("HR (Min / Max)", f"{min_hr} / {max_hr} bpm", styles))

    # 3) CLIMB & ENVIRONMENT (Adattato con le dinamiche cinematiche dello sprint)
    rows.append(_section_row("Climb & Environment", styles))
    rows.append(_metric_row("Grade (Avg | Max)", f"{s.get('avg_grade', 0)}% | {s.get('max_grade', 0)}%", styles))
    
    # Velocità di picco e progressione (Inizio -> Max -> Fine) sulla stessa riga per massima densità grafica
    v1 = s.get('v1', 0)
    v_max = s.get('v_max', 0)
    v2 = s.get('v2', 0)
    rows.append(_metric_row("Speed (Start|Max|End)", f"{v1} | {v_max} | {v2} km/h", styles))
    
    avg_cad = int(float(s.get('avg_cadence', 0)))
    min_cad = int(float(s.get('min_cadence', 0)))
    max_cad = int(float(s.get('max_cadence', 0)))
    rows.append(_metric_row("Cadence (Avg | Max)", f"{avg_cad} | {max_cad} rpm", styles))

    # 4) ENERGY
    rows.append(_section_row("Energy", styles))
    rows.append(_metric_row("kJ Total",      f"{int(float(s.get('kj', 0)))} kJ", styles))
    rows.append(_metric_row("kJ > CP",       f"{int(float(s.get('kj_over_cp', 0)))} kJ", styles))
    rows.append(_metric_row("kJ/kg",         str(s.get("kj_kg", 0)), styles))
    rows.append(_metric_row("kJ/h/kg",       str(s.get("kj_h_kg", 0)), styles))

    col_w = [INNER_W * 0.22, INNER_W * 0.22]
    tbl = Table(rows, colWidths=col_w)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
        ("TEXTCOLOR",  (0, 0), (-1, -1), COL_TEXT),
        ("FONTSIZE",   (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1),
         [colors.HexColor("#0f172a"), colors.HexColor("#1e293b")]),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",   (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 1),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#334155")),
    ]))
    return tbl


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY TABLES (no details)
# ══════════════════════════════════════════════════════════════════════════════

def build_efforts_summary_table(efforts: List[Dict], cp: float, styles) -> Table:
    header = ["#", "Start", "Dur", "Dist", "Avg W", "% CP", "W/kg",
              "5\"W", "HR", "VAM", "kJ"]
    rows = [header]
    for e in efforts:
        rows.append([
            f"E#{e['id']+1}",
            e.get("start_time", ""),
            fmt_dur(e.get("duration", 0)),
            f"{e.get('distance_tot', 0)} km",
            f"{int(e.get('avg_power', 0))} W",
            f"{int(e.get('cp_pct', 0))}%",
            str(e.get("avg_power_per_kg", 0)),
            f"{int(e.get('best_5s_watt', 0))} W",
            f"{int(e.get('avg_hr', 0))} bpm" if e.get('avg_hr') else "—",
            f"{int(e.get('vam', 0))} m/h",
            f"{int(e.get('kj', 0))} kJ",
        ])

    col_w = [
        18*mm, 22*mm, 18*mm, 18*mm, 20*mm,
        16*mm, 16*mm, 18*mm, 20*mm, 22*mm, 16*mm
    ]

    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    effort_colors_rl = []
    for i, e in enumerate(efforts, start=1):
        hex_c = e.get("color", "#60a5fa")
        effort_colors_rl.append(
            ("BACKGROUND", (0, i), (0, i), colors.HexColor(hex_c))
        )

    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), COL_BLUE),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.HexColor("#0f172a"), colors.HexColor("#1e293b")]),
        ("TEXTCOLOR",  (0, 1), (-1, -1), COL_TEXT),
        ("LEFTPADDING",  (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING",   (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#334155")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ] + effort_colors_rl))
    return tbl


def build_sprints_summary_table(sprints: List[Dict], styles) -> Table:
    header = ["#", "Start", "Dur", "Avg W", "Max W", "W/kg",
              "Avg rpm", "v_start", "v_max", "v_end", "kJ"]
    rows = [header]
    for s in sprints:
        rows.append([
            f"S#{s['rank']}",
            s.get("start_time", ""),
            fmt_dur(s.get("duration", 0)),
            f"{int(s.get('avg_power', 0))} W",
            f"{int(s.get('max_watt', 0))} W",
            str(s.get("avg_power_per_kg", 0)),
            f"{int(s.get('avg_cadence', 0))} rpm",
            f"{s.get('v1', 0)} km/h",
            f"{s.get('v_max', 0)} km/h",
            f"{s.get('v2', 0)} km/h",
            f"{int(s.get('kj', 0))} kJ",
        ])

    col_w = [
        18*mm, 22*mm, 18*mm, 20*mm, 20*mm,
        16*mm, 20*mm, 20*mm, 20*mm, 20*mm, 16*mm
    ]

    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), COL_MUTED),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.HexColor("#0f172a"), colors.HexColor("#1e293b")]),
        ("TEXTCOLOR",  (0, 1), (-1, -1), COL_TEXT),
        ("LEFTPADDING",  (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING",   (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#334155")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


# ══════════════════════════════════════════════════════════════════════════════
# DARK-BACKGROUND PAGE TEMPLATE
# ══════════════════════════════════════════════════════════════════════════════

def on_page(canvas, doc):
    canvas.saveState()
    # Dark background
    canvas.setFillColor(colors.HexColor("#1e293b"))
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    # Thin top bar
    canvas.setFillColor(colors.HexColor("#0f172a"))
    canvas.rect(0, PAGE_H - 8*mm, PAGE_W, 8*mm, fill=1, stroke=0)
    # Page number
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawRightString(PAGE_W - MARGIN, 6*mm, f"Page {doc.page}")
    canvas.restoreState()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_pdf_report(
    chart_data: Dict,
    filename: str = "peffort_report",
    zones: Optional[List[Dict]] = None,
    cp_override: Optional[float] = None,
) -> bytes:
    """
    Build the full PDF report and return bytes.

    chart_data: the same dict returned by prepare_chart_data() / get_chart_data_json().
    """
    if zones is None:
        zones = DEFAULT_ZONES

    cp     = float(cp_override or chart_data.get("cp", 250))
    weight = float(chart_data.get("weight", 70))
    efforts  = chart_data.get("efforts", [])
    sprints  = chart_data.get("sprints", [])
    config   = chart_data.get("config", {})

    styles = build_styles()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=(PAGE_W, PAGE_H),
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN + 1*mm, bottomMargin=MARGIN,
        title=f"PEFFORT Report – {filename}",
    )

    story = []

    # ── PAGE 1: Header ────────────────────────────────────────────────────────
    story.append(Paragraph(f"PEFFORT — {filename}", styles["title"]))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(
        f"CP: {int(cp)} W  |  Weight: {weight} kg  |  "
        f"Efforts: {len(efforts)}  |  Sprints: {len(sprints)}  |  "
        f"Win: {int(config.get('window_sec', 0))}s  "
        f"Min CP: {int(config.get('min_cp_pct', 0))}%  "
        f"Merge: {int(config.get('merge_pct', 0))}%",
        styles["subtitle"]
    ))

    # Altimetry chart — full width
    alti_h = 75 * mm
    alti_img = build_altimetry_chart(chart_data, INNER_W, alti_h, zones=zones)
    story.append(alti_img)
    story.append(Spacer(1, 4*mm))

    # ── Efforts summary table ─────────────────────────────────────────────────
    if efforts:
        story.append(Paragraph("Efforts Summary", styles["h2"]))
        story.append(build_efforts_summary_table(efforts, cp, styles))
        story.append(Spacer(1, 3*mm))

    # ── Sprints summary table ─────────────────────────────────────────────────
    if sprints:
        story.append(Paragraph("Sprints Summary", styles["h2"]))
        story.append(build_sprints_summary_table(sprints, styles))

    story.append(PageBreak())

    # ── EFFORT DETAIL PAGES ───────────────────────────────────────────────────
    # Each effort gets its own page: left = full-detail metrics table,
    # right = stream chart.
    DETAIL_LEFT_W  = INNER_W * 0.46
    DETAIL_RIGHT_W = INNER_W * 0.52
    STREAM_H       = INNER_H - 20*mm   # leave room for title

    for e in efforts:
        color_hex = e.get("color", "#60a5fa")

        # Title row
        story.append(Paragraph(
            f"<font color='{color_hex}'><b>E#{e['id']+1}</b></font> "
            f"— Rank #{e.get('rank','?')} — {e.get('start_time','')} "
            f"— {fmt_dur(e.get('duration',0))} "
            f"— {int(e.get('avg_power',0))} W ({e.get('cp_pct',0)}%)",
            styles["h3"]
        ))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=colors.HexColor(color_hex), spaceAfter=4))

        # Left: metric table   Right: stream chart
        metrics_tbl = build_effort_metrics_table(e, cp, styles)
        
        # Prepare altitude data for this effort from line_data
        altitude_data = []
        if e.get("line_data"):
            for point in e["line_data"]:
                altitude_data.append({"dist": point[0], "alt": point[1]})
        
        stream_img  = build_stream_chart(
            e, cp,
            width_pt=DETAIL_RIGHT_W,
            height_pt=STREAM_H,
            zones=zones,
            altitude_data=altitude_data if altitude_data else None,
            elevation_data=chart_data.get("elevation_data", [])
        )

        side_by_side = Table(
            [[metrics_tbl, stream_img]],
            colWidths=[DETAIL_LEFT_W, DETAIL_RIGHT_W]
        )
        side_by_side.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ]))
        story.append(side_by_side)
        story.append(PageBreak())

    # ── SPRINT DETAIL PAGES ───────────────────────────────────────────────────
    for s in sprints:
        story.append(Paragraph(
            f"<font color='#94a3b8'><b>S#{s.get('rank','?')}</b></font> "
            f"— {s.get('start_time','')} "
            f"— {fmt_dur(s.get('duration',0))} "
            f"— {int(s.get('avg_power',0))} W  max {int(s.get('max_watt',0))} W",
            styles["h3"]
        ))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=colors.HexColor("#374151"), spaceAfter=4))

        # Mark segment as sprint for stream chart
        s_copy = dict(s)
        s_copy["type"] = "sprint"

        metrics_tbl = build_sprint_metrics_table(s, styles)
        stream_img  = build_stream_chart(
            s_copy, cp,
            width_pt=DETAIL_RIGHT_W,
            height_pt=STREAM_H,

            zones=zones
        )

        side_by_side = Table(
            [[metrics_tbl, stream_img]],
            colWidths=[DETAIL_LEFT_W, DETAIL_RIGHT_W]
        )
        side_by_side.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ]))
        story.append(side_by_side)
        story.append(PageBreak())

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
