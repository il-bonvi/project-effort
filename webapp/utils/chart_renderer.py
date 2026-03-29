"""
EXPORT MANAGER - Gestione esportazione PDF e generazione grafici
Contiene: create_pdf_report, plot_unified_html, rendering plotly
"""

from typing import List, Tuple, Dict, Any
import logging
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import io
from xhtml2pdf import pisa

from .effort_analyzer import (
    format_time_hhmmss, format_time_mmss, get_zone_color
)

logger = logging.getLogger(__name__)


def create_pdf_report(df: pd.DataFrame, efforts: List[Tuple[int, int, float]], 
                      sprints: List[Dict[str, Any]], img_base64_str: str, 
                      cp: float, weight: float, output_path: str, 
                      params_str: str) -> bool:
    """
    Genera un file PDF contenente il grafico e le tabelle.
    
    Args:
        df: DataFrame con dati attività
        efforts: Lista efforts (start, end, avg_power)
        sprints: Lista sprints {start, end, avg}
        img_base64_str: Immagine grafico in base64
        cp: Critical Power
        weight: Peso atleta
        output_path: Percorso output PDF
        params_str: Stringa parametri configurazione
        
    Returns:
        True se successo, False se errore
    """
    try:
        logger.info(f"Inizio generazione PDF Report: {output_path}")
        
        # Costruiamo il tag immagine HTML
        if img_base64_str:
            img_html = f'<img src="data:image/png;base64,{img_base64_str}" style="width:100%; border:1px solid #ddd;">'
        else:
            img_html = "<p><i>Immagine grafico non disponibile</i></p>"

        # Dati per calcoli (con controllo colonne)
        required_cols = ["power", "time_sec", "altitude", "distance", "heartrate", "grade", "cadence", "distance_km"]
        for col in required_cols:
            if col not in df.columns:
                logger.warning(f"Colonna mancante nel DataFrame: {col}")
                df[col] = 0  # Fallback a zero per colonne mancanti
        
        power = df["power"].values
        time_sec = df["time_sec"].values
        alt = df["altitude"].values
        dist = df["distance"].values
        hr = df["heartrate"].values
        grade = df["grade"].values
        cadence = df["cadence"].values
        dist_km = df["distance_km"].values

        # --- HTML HEADER ---
        html_content = f"""
        <html>
        <head>
            <style>
                @page {{ size: A4; margin: 1cm; }}
                body {{ font-family: Helvetica, Arial, sans-serif; font-size: 10px; color: #333; }}
                h1 {{ font-size: 18px; color: #222; border-bottom: 2px solid #444; padding-bottom: 5px; }}
                h2 {{ font-size: 14px; margin-top: 20px; color: #444; background-color: #eee; padding: 5px; }}
                .params {{ font-size: 8px; color: #666; margin-bottom: 15px; }}
                table {{ width: 100%; border-collapse: collapse; margin-bottom: 10px; page-break-inside: auto; }}
                th {{ background-color: #333; color: white; padding: 4px; text-align: left; font-size: 9px; }}
                td {{ border-bottom: 1px solid #ddd; padding: 4px; font-size: 9px; }}
                tr:nth-child(even) {{ background-color: #f9f9f9; }}
                .right {{ text-align: right; }}
            </style>
        </head>
        <body>
            <h1>Effort Analysis Report</h1>
            <div class="params">
                {params_str} <br>
                CP: <b>{cp:.0f} W</b> | Weight: <b>{weight:.1f} kg</b>
            </div>
            {img_html}
        """

        # --- SEZIONE EFFORTS ---
        if efforts:
            html_content += """
            <h2>Efforts Table</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th><th>Start</th><th>Dur</th>
                        <th class="right">Power</th><th class="right">W/kg</th><th class="right">%CP</th>
                        <th class="right">Best 5s</th><th class="right">HR</th>
                        <th class="right">VAM</th><th class="right">Grade</th><th class="right">kJ</th>
                    </tr>
                </thead>
                <tbody>
            """
            
            ranked_efforts = sorted(enumerate(efforts), key=lambda x: x[1][2], reverse=True)
            effort_to_rank = {orig_idx: rank + 1 for rank, (orig_idx, _) in enumerate(ranked_efforts)}

            for i, (s, e, avg) in enumerate(efforts):
                seg_power = power[s:e]
                seg_alt = alt[s:e]
                seg_dist = dist[s:e]
                seg_time = time_sec[s:e]
                seg_hr = hr[s:e]

                duration = int(seg_time[-1] - seg_time[0] + 1)
                elevation_gain = seg_alt[-1] - seg_alt[0]
                dist_tot = seg_dist[-1] - seg_dist[0]
                avg_grade = (elevation_gain / dist_tot * 100) if dist_tot > 0 else 0
                vam = elevation_gain / (duration / 3600) if duration > 0 else 0

                w_kg = avg / weight if weight > 0 else 0
                perc_cp = (avg / cp * 100) if cp > 0 else 0

                valid_hr = seg_hr[seg_hr > 0]
                hr_str = f"{int(valid_hr.mean())}" if len(valid_hr) > 0 else "-"

                best_5s_watt = 0
                if len(seg_power) >= 5:
                    moving_avgs = [seg_power[i:i+5].mean() for i in range(len(seg_power)-4)]
                    best_5s = max(moving_avgs) if moving_avgs else 0
                    best_5s_watt = int(best_5s)

                kj_seg = 0
                skipped_gaps = 0
                for k in range(1, len(seg_time)):
                    dt = seg_time[k] - seg_time[k-1]
                    if 0 < dt < 30:
                        kj_seg += seg_power[k] * dt
                    elif dt >= 30:
                        skipped_gaps += 1
                
                if skipped_gaps > 0:
                    logger.warning(f"Effort #{effort_to_rank[i]}: {skipped_gaps} gap temporali >30s saltati nel calcolo kJ")

                html_content += f"""
                    <tr>
                        <td>#{effort_to_rank[i]}</td>
                        <td>{format_time_hhmmss(seg_time[0])}</td>
                        <td>{duration}s</td>
                        <td class="right"><b>{avg:.0f} W</b></td>
                        <td class="right">{w_kg:.2f}</td>
                        <td class="right">{perc_cp:.0f}%</td>
                        <td class="right">{best_5s_watt:.0f} W</td>
                        <td class="right">{hr_str}</td>
                        <td class="right">{vam:.0f}</td>
                        <td class="right">{avg_grade:.1f}%</td>
                        <td class="right">{kj_seg:.0f}</td>
                    </tr>
                """
            html_content += "</tbody></table>"

        # --- SEZIONE SPRINTS ---
        if sprints:
            html_content += """
            <h2>Sprints Table</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th><th>Start</th><th>Dur</th>
                        <th class="right">Avg Power</th><th class="right">Max Power</th>
                        <th class="right">W/kg</th><th class="right">HR Max</th>
                        <th class="right">Cadence Avg/Max</th><th class="right">Speed Max</th>
                    </tr>
                </thead>
                <tbody>
            """
            ranked_sprints = sorted(enumerate(sprints), key=lambda x: x[1]['avg'], reverse=True)
            sprint_to_rank = {orig_idx: rank + 1 for rank, (orig_idx, _) in enumerate(ranked_sprints)}

            for i, sprint in enumerate(sprints):
                start, end = sprint['start'], sprint['end']
                seg_power, seg_time = power[start:end], time_sec[start:end]
                seg_hr, seg_cadence = hr[start:end], cadence[start:end]
                seg_dist_km = dist_km[start:end]

                w_kg = sprint['avg'] / weight if weight > 0 else 0
                max_hr = seg_hr.max() if seg_hr[seg_hr > 0].any() else 0
                v_cad = seg_cadence[seg_cadence > 0]
                cad_str = f"{v_cad.mean():.0f}/{v_cad.max():.0f}" if len(v_cad) > 0 else "-"
                
                max_speed = 0
                if len(seg_dist_km) > 1:
                    diffs = []
                    for k in range(len(seg_dist_km)-1):
                        dt = time_sec[start+k+1] - time_sec[start+k]
                        if dt > 0:
                            speed_kmh = (seg_dist_km[k+1] - seg_dist_km[k]) / dt * 3600
                            diffs.append(speed_kmh)
                    max_speed = max(diffs) if diffs else 0

                html_content += f"""
                    <tr>
                        <td>S#{sprint_to_rank[i]}</td>
                        <td>{format_time_hhmmss(seg_time[0])}</td>
                        <td>{int(end-start)}s</td>
                        <td class="right"><b>{sprint['avg']:.0f} W</b></td>
                        <td class="right">{seg_power.max():.0f} W</td>
                        <td class="right">{w_kg:.2f}</td>
                        <td class="right">{max_hr:.0f}</td>
                        <td class="right">{cad_str}</td>
                        <td class="right">{max_speed:.1f}</td>
                    </tr>
                """
            html_content += "</tbody></table>"

        html_content += """
            <div style="text-align:center; margin-top: 30px; font-size: 8px; color: #888;">
                Generated by bFactor PEFFORT Engine
            </div>
        </body>
        </html>
        """

        with open(output_path, "wb") as result_file:
            pisa.CreatePDF(io.BytesIO(html_content.encode('utf-8')), dest=result_file)
        
        logger.info(f"PDF generato con successo: {output_path}")
        return True
        
    except IOError as e:
        logger.error(f"Errore I/O durante scrittura PDF: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Errore generazione PDF: {e}", exc_info=True)
        return False


def plot_unified_html(df: pd.DataFrame, efforts: List[Tuple[int, int, float]], 
                      sprints: List[Dict[str, Any]], cp: float, weight: float,
                      window_sec: int, merge_pct: float, min_cp_pct: float, 
                      trim_win: int, trim_low: float, extend_win: int, extend_low: float,
                      sprint_window_sec: int, min_sprint_power: float) -> str:
    """
    Genera grafico Plotly HTML unificato con efforts e sprints.
    """
    logger.info("Inizializzazione figura Plotly...")
    
    power = df["power"].values
    time_sec = df["time_sec"].values
    dist_km = df["distance_km"].values
    distance = df["distance"].values
    alt = df["altitude"].values
    hr = df["heartrate"].values
    grade = df["grade"].values
    cadence = df["cadence"].values
    
    fig = go.Figure()
    
    step = max(1, len(dist_km) // 1000)
    hover_alt_text = []
    for i in range(0, len(dist_km), step):
        t = time_sec[i]
        if t >= 3600:
            time_str = format_time_hhmmss(t)
        else:
            time_str = format_time_mmss(t)
        hover_alt_text.append(f"📏 {dist_km[i]:.2f} km<br>🏔️ {alt[i]:.1f} m<br>⏱️ {time_str}")
    
    fig.add_trace(go.Scatter(
        x=dist_km[::step],
        y=alt[::step],
        fill='tozeroy',
        name="Altitudine",
        fillcolor="whitesmoke",
        line=dict(color="lightgray", width=1),
        mode='lines',
        text=hover_alt_text,
        hoverinfo='text',
        hoverlabel=dict(bgcolor='lightgray', font=dict(color='black', size=12))
    ))
    
    joules_cumulative = np.zeros(len(power))
    joules_over_cp_cumulative = np.zeros(len(power))
    for i in range(1, len(power)):
        dt = time_sec[i] - time_sec[i-1]
        if dt > 0 and dt < 30:
            joules_cumulative[i] = joules_cumulative[i-1] + power[i] * dt
            if power[i] >= cp:
                joules_over_cp_cumulative[i] = joules_over_cp_cumulative[i-1] + power[i] * dt
            else:
                joules_over_cp_cumulative[i] = joules_over_cp_cumulative[i-1]
        else:
            joules_cumulative[i] = joules_cumulative[i-1]
            joules_over_cp_cumulative[i] = joules_over_cp_cumulative[i-1]
    
    global_max_alt = alt.max()
    alt_range = global_max_alt - alt.min()
    offsets = [0.25, 0.75, 1.25]
    annotations = []
    
    efforts_with_idx = [(i, eff) for i, eff in enumerate(efforts)]
    sorted_efforts = sorted(efforts_with_idx, key=lambda x: x[1][2], reverse=True)
    
    for idx, (orig_idx, (s, e, avg)) in enumerate(sorted_efforts):
        seg_power = power[s:e]
        seg_alt = alt[s:e]
        seg_dist_km = dist_km[s:e]
        seg_dist = distance[s:e]
        seg_time = time_sec[s:e]
        seg_hr = hr[s:e]
        seg_grade = grade[s:e]
        seg_cadence = cadence[s:e]
        
        avg_power = avg
        color = get_zone_color(avg_power, cp)
        
        duration = seg_time[-1] - seg_time[0] + 1
        elevation_gain = seg_alt[-1] - seg_alt[0]
        dist_tot = seg_dist[-1] - seg_dist[0]
        avg_speed = dist_tot / (duration / 3600) / 1000 if duration > 0 else 0
        vam = elevation_gain / (duration / 3600) if duration > 0 else 0
        avg_grade = (elevation_gain / dist_tot * 100) if dist_tot > 0 else 0
        
        half = len(seg_power) // 2
        avg_watts_first = seg_power[:half].mean() if half > 0 else 0
        avg_watts_second = seg_power[half:].mean() if len(seg_power) > half else 0
        watts_ratio = avg_watts_first / avg_watts_second if avg_watts_second > 0 else 0
        
        valid_hr = seg_hr[seg_hr > 0]
        avg_hr = valid_hr.mean() if len(valid_hr) > 0 else 0
        max_hr = valid_hr.max() if len(valid_hr) > 0 else 0
        max_grade = seg_grade.max() if len(seg_grade) > 0 else 0
        
        best_5s_watt = 0
        best_5s_watt_kg = 0
        if len(seg_power) >= 5 and weight > 0:
            moving_avgs = [seg_power[i:i+5].mean() for i in range(len(seg_power)-4)]
            best_5s = max(moving_avgs) if moving_avgs else 0
            best_5s_watt = int(best_5s)
            best_5s_watt_kg = best_5s / weight
        
        avg_power_per_kg = avg_power / weight if weight > 0 else 0
        avg_cadence = seg_cadence[seg_cadence > 0].mean() if len(seg_cadence[seg_cadence > 0]) > 0 else 0
        
        hours = time_sec[s] / 3600 if time_sec[s] > 0 else 0
        kj = joules_cumulative[s] / 1000 if s < len(joules_cumulative) else 0
        kj_over_cp = joules_over_cp_cumulative[s] / 1000 if s < len(joules_over_cp_cumulative) else 0
        kj_kg = (kj / weight) if weight > 0 else 0
        kj_kg_over_cp = (kj_over_cp / weight) if weight > 0 else 0
        kj_h_kg = (kj_kg / hours) if hours > 0 else 0
        kj_h_kg_over_cp = (kj_kg_over_cp / hours) if hours > 0 else 0
        
        gradient_factor = 2 + (avg_grade / 10)
        vam_teorico = (avg_power / weight) * (gradient_factor * 100) if weight > 0 else 0
        
        hover_lines = [
            f"⚡ {avg_power:.0f} W | 5\"🔺{best_5s_watt} W 🌀 {avg_cadence:.0f} rpm",
            f"⏱️ {format_time_mmss(duration)} | 🕒 {format_time_hhmmss(seg_time[0])} | {(avg_power/cp*100):.0f}%",
            f"⚖️ {avg_power_per_kg:.2f} W/kg | 5\"🔺{best_5s_watt_kg:.2f} W/kg",
            f"🔀 {avg_watts_first:.0f} W | {avg_watts_second:.0f} W | {watts_ratio:.2f}",
        ]
        if len(valid_hr) > 0:
            hover_lines.append(f"❤️ ∅{avg_hr:.0f} bpm | 🔺{max_hr:.0f} bpm")
        hover_lines.append(f"🚴‍♂️ {avg_speed:.1f} km/h 📏 ∅ {avg_grade:.1f}% | 🔺{max_grade:.1f}%")
        if avg_grade >= 4.5:
            diff_vam = abs(vam_teorico - vam)
            arrow = '⬆️' if vam_teorico - vam > 0 else ('⬇️' if vam_teorico - vam < 0 else '')
            wkg_teoric = vam / (gradient_factor * 100) if gradient_factor > 0 else 0
            diff_wkg = avg_power_per_kg - wkg_teoric
            perc_err = ((wkg_teoric - avg_power_per_kg) / avg_power_per_kg * 100) if avg_power_per_kg != 0 else 0
            sign = '+' if perc_err > 0 else ('-' if perc_err < 0 else '')
            hover_lines.append(f"🚵‍♂️ {vam:.0f} m/h {arrow} {diff_vam:.0f} m/h | {abs(diff_wkg):.2f} W/kg")
            hover_lines.append(f"🧮 {vam_teorico:.0f} m/h | {wkg_teoric:.2f} W/kg | {sign}{abs(perc_err):.1f}%")
        else:
            hover_lines.append(f"🚵‍♂️ {vam:.0f} m/h")
        hover_lines.append(f"🔋 {kj:.0f} kJ | {kj_over_cp:.0f} kJ > CP")
        hover_lines.append(f"💪 {kj_kg:.1f} kJ/kg | {kj_kg_over_cp:.1f} kJ/kg > CP")
        hover_lines.append(f"🔥 {kj_h_kg:.1f} kJ/h/kg | {kj_h_kg_over_cp:.1f} kJ/h/kg > CP")
        hover_text = "<br>".join(hover_lines)
        
        fig.add_trace(go.Scatter(
            x=seg_dist_km,
            y=seg_alt,
            mode='lines',
            line=dict(color=color, width=3),
            name=f"E#{orig_idx+1} {avg_power:.0f}W",
            text=hover_text,
            hoverinfo="text",
            hoverlabel=dict(
                align='left', 
                bgcolor=color, 
                font=dict(color='white', size=12),
                bordercolor='white'
            )
        ))
        
        y_ann = global_max_alt + offsets[orig_idx % len(offsets)] * alt_range
        annotations.append(dict(
            x=(seg_dist_km[0] + seg_dist_km[-1]) / 2,
            y=y_ann,
            text=f"E#{orig_idx+1}<br>⚡ {avg_power:.0f}<br>⏱️ {int(duration)}s",
            showarrow=False,
            font=dict(family='Arial', size=12, color='white'),
            align='center',
            bgcolor=color,
            opacity=0.9
        ))
    
    sorted_sprints = sorted(enumerate(sprints), key=lambda x: x[1]['avg'], reverse=True)
    
    for legend_idx, (orig_idx, sprint) in enumerate(sorted_sprints):
        start = sprint['start']
        end = sprint['end']
        avg_power = sprint['avg']
        duration = end - start
        
        seg_power = power[start:end]
        seg_alt = alt[start:end]
        seg_dist_km = dist_km[start:end]
        seg_dist = distance[start:end]
        seg_hr = hr[start:end]
        seg_grade = grade[start:end]
        seg_cadence = cadence[start:end]
        
        color = '#000000'
        
        elevation_gain = seg_alt[-1] - seg_alt[0]
        dist_tot = seg_dist[-1] - seg_dist[0]
        avg_grade = (elevation_gain / dist_tot * 100) if dist_tot > 0 else 0
        
        valid_hr = seg_hr[seg_hr > 0]
        min_hr = valid_hr.min() if len(valid_hr) > 0 else 0
        max_hr = valid_hr.max() if len(valid_hr) > 0 else 0
        min_watt = seg_power.min() if len(seg_power) > 0 else 0
        max_watt = seg_power.max() if len(seg_power) > 0 else 0
        max_grade = seg_grade.max() if len(seg_grade) > 0 else 0
        
        v1 = v2 = 0
        if len(seg_dist_km) >= 2:
            v1 = (seg_dist_km[1] - seg_dist_km[0]) * 3600
            v2 = (seg_dist_km[-1] - seg_dist_km[-2]) * 3600
        
        avg_power_per_kg = avg_power / weight if weight > 0 else 0
        valid_cadence = seg_cadence[seg_cadence > 0]
        avg_cadence = valid_cadence.mean() if len(valid_cadence) > 0 else 0
        min_cadence = valid_cadence.min() if len(valid_cadence) > 0 else 0
        max_cadence = valid_cadence.max() if len(valid_cadence) > 0 else 0
        
        hover_lines = [
            f"S#{legend_idx+1}",
            f"⚡ {avg_power:.0f} W  ⚖️ {avg_power_per_kg:.2f} W/kg",
            f"⚡ 🔺{max_watt:.0f} W | 🔻{min_watt:.0f} W",
        ]
        if len(valid_hr) > 0:
            hover_lines.append(f"❤️ 🔻{min_hr:.0f} bpm | 🔺{max_hr:.0f} bpm")
        if avg_cadence > 0:
            hover_lines.append(f"🌀 ∅{avg_cadence:.0f} rpm | 🔻{min_cadence:.0f} rpm | 🔺{max_cadence:.0f} rpm")
        if v1 > 0 and v2 > 0:
            hover_lines.append(f"➡️ {v1:.1f} km/h | {v2:.1f} km/h")
        
        hover_lines.append(f"📏 ∅ {avg_grade:.1f}% max. {max_grade:.1f}%")
        hover_text = "<br>".join(hover_lines)
        
        fig.add_trace(go.Scatter(
            x=seg_dist_km,
            y=seg_alt,
            mode='lines',
            line=dict(color=color, width=3),
            name=f"S#{legend_idx+1} {avg_power:.0f}W",
            text=hover_text,
            hoverinfo="text",
            hoverlabel=dict(
                align='left', 
                bgcolor=color, 
                font=dict(color='white', size=12),
                bordercolor='white'
            )
        ))
        
        offset_x = (-1 if legend_idx % 2 == 0 else 1) * legend_idx * 0.003
        y_ann = seg_alt.max() + 50 + legend_idx * 25
        
        annotations.append(dict(
            x=(seg_dist_km[0] + seg_dist_km[-1]) / 2 + offset_x,
            y=y_ann,
            text=f"S#{legend_idx+1}<br>⚡ {avg_power:.0f}<br>⏱️ {int(duration)}s",
            showarrow=False,
            font=dict(family='Arial', size=12, color='white'),
            align='center',
            bgcolor=color,
            opacity=0.9
        ))
    
    config_title = (
        f"<b>UNIFIED ANALYSIS</b> | "
        f"<span style='color:#000000'>EFFORTS: MRG [{merge_pct}%] WIN [{window_sec}s] MIN [{min_cp_pct}%CP]</span> | "
        f"<span style='color:#ff0000'>TRIM [{trim_win}s, {trim_low}%]</span> "
        f"<span style='color:#1901f5'>EXT [{extend_win}s, {extend_low}%]</span> | "
        f"<span style='color:#000000'>SPRINTS: WIN [{sprint_window_sec}s] MIN [{min_sprint_power:.0f}W]</span>"
    )
    
    fig.update_layout(
        title=dict(text=config_title, font=dict(color='#222', size=16), y=0.98),
        xaxis_title="Distance (km)",
        yaxis_title="Altitude (m)",
        hovermode="x",
        hoverdistance=10,
        showlegend=True,
        margin=dict(t=40, l=10, r=10, b=30),
        autosize=True,
        updatemenus=[dict(type="buttons", showactive=False, buttons=[])]
    )
    
    for ann in annotations:
        fig.add_annotation(ann)
    
    logger.info(f"Grafico generato con {len(efforts)} efforts e {len(sprints)} sprints")
    html_str = pio.to_html(fig, full_html=True)
    if "<!DOCTYPE html>" not in html_str[:200]:
        html_str = "<!DOCTYPE html>\n" + html_str
    
    style_fix = """
    <style>
        html, body { 
            margin: 0 !important; 
            padding: 0 !important; 
            height: 100vh !important; 
            width: 100vw !important; 
            overflow: hidden !important; 
        }
        .plotly-graph-div { 
            height: 100vh !important; 
            width: 100vw !important; 
        }
    </style>
    """
    html_str = html_str.replace('<head>', '<head>' + style_fix)

    custom_js = """
    <script>
    document.addEventListener('DOMContentLoaded', function() {
        var plot = document.getElementsByClassName('plotly-graph-div')[0];
        plot.on('plotly_restyle', function(data) {
            var layout = plot.layout;
            var plotData = plot.data;
            var newAnnotations = [];
            layout.annotations.forEach(function(ann, idx) {
                if (!ann.text.includes('#')) { newAnnotations.push(ann); return; }
                var match = ann.text.match(/([ES])#(\\d+)/);
                if (!match) { newAnnotations.push(ann); return; }
                var type = match[1]; 
                var num = match[2];
                var traceFound = false;
                var traceVisible = false;
                for (var i = 0; i < plotData.length; i++) {
                    var traceName = plotData[i].name || '';
                    var traceMatch = traceName.match(/([ES])#(\\d+)/);
                    if (traceMatch && traceMatch[1] === type && traceMatch[2] === num) {
                        traceFound = true;
                        traceVisible = plotData[i].visible !== 'legendonly' && plotData[i].visible !== false;
                        break;
                    }
                }
                if (traceVisible || !traceFound) { newAnnotations.push(ann); }
            });
            Plotly.relayout(plot, {'annotations': newAnnotations});
        });
    });
    </script>
    """
    html_str = html_str.replace('</body>', custom_js + '</body>')
    logger.info("HTML generato con successo")
    return html_str
