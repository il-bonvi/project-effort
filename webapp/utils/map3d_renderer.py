# ==============================================================================
# Copyright (c) 2026 Andrea Bonvicin - bFactor Project
# PROPRIETARY LICENSE - TUTTI I DIRITTI RISERVATI
# Sharing, distribution or reproduction is strictly prohibited.
# La condivisione, distribuzione o riproduzione è severamente vietata.
# ==============================================================================

"""
map3d_renderer.py - Rendering templates for 3D Map visualization

Handles HTML template rendering by loading from templates/ folder.
Separated from business logic (map3d_core.py) and orchestration (map3d_generator.py).
"""

import json
from pathlib import Path
from jinja2 import Environment, FileSystemLoader


def generate_3d_map_html(efforts_data_json: str, elevation_data_json: str, geojson_str: str,
                         maptiler_key: str, center_lat: float, center_lon: float, zoom: int,
                         distance_km: float) -> str:
    """
    Generate the complete HTML document for the 3D map visualization.
    
    Args:
        efforts_data_json: JSON string of efforts data
        elevation_data_json: JSON string of elevation profile data
        geojson_str: JSON string of the GeoJSON traccia
        maptiler_key: MapTiler API key
        center_lat: Map center latitude
        center_lon: Map center longitude
        zoom: Initial zoom level
        distance_km: Total track distance in km
        
    Returns:
        str: Complete HTML document
    """
    # Load template from templates/ folder
    templates_dir = Path(__file__).parent.parent / 'templates'
    env = Environment(loader=FileSystemLoader(str(templates_dir)))
    template = env.get_template('map3d.html')
    
    html = template.render(
        distance_km=distance_km,
        geojson_str=geojson_str,
        elevation_data_json=elevation_data_json,
        efforts_data_json=efforts_data_json,
        maptiler_key=maptiler_key,
        center_lat=center_lat,
        center_lon=center_lon,
        zoom=zoom
    )
    
    return html
