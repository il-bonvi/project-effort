/* ==============================================================================
   Copyright (c) 2026 Andrea Bonvicin - bFactor Project
   PROPRIETARY LICENSE - TUTTI I DIRITTI RISERVATI
   ============================================================================== */

const styles = [
    { key: 'outdoor', name: 'Outdoor', url: `https://api.maptiler.com/maps/outdoor-v2/style.json?key=${maptiler_key}` },
    { key: 'streets', name: 'Streets', url: `https://api.maptiler.com/maps/streets-v2/style.json?key=${maptiler_key}` },
    { key: 'topo', name: 'Topo', url: `https://api.maptiler.com/maps/topo-v2/style.json?key=${maptiler_key}` },
    { key: 'bright', name: 'Bright', url: `https://api.maptiler.com/maps/bright-v2/style.json?key=${maptiler_key}` },
    { key: 'dark', name: 'Dark', url: `https://api.maptiler.com/maps/darkmatter/style.json?key=${maptiler_key}` },
    { key: 'winter', name: 'Winter', url: `https://api.maptiler.com/maps/winter/style.json?key=${maptiler_key}` },
    { key: 'satellite', name: 'Satellite', url: `https://api.maptiler.com/maps/satellite/style.json?key=${maptiler_key}` },
    { key: 'hybrid', name: 'Hybrid', url: `https://api.maptiler.com/maps/hybrid/style.json?key=${maptiler_key}` }
];
let currentStyleIndex = 0;

const map = new maplibregl.Map({
    container: 'map',
    style: styles[currentStyleIndex].url,
    center: [center_lon, center_lat],
    zoom: zoom,
    pitch: 45,
    bearing: 0
});
try { map.setProjection({ name: 'globe' }); } catch(e) { console.warn('Projection set failed:', e); }
map.addControl(new maplibregl.NavigationControl());

const tracceGeoJSON = geojson_str;
const elevationData = elevation_data_json;

let activeEffortLayer = null;
let activeEffortIdx = null;
let currentEfforts = efforts_data_json;

function openEffortSidebar(idx) {
    const effort = currentEfforts[idx];
    const sidebar = document.getElementById('sidebar');
    
    let hrHtml = effort.max_hr > 0 ? `
        <div class="sidebar-section">
            <div class="sidebar-title">❤️ FREQUENZA CARDIACA</div>
            <div class="sidebar-row">
                <span class="sidebar-label">Media</span>
                <span class="sidebar-value">${effort.avg_hr.toFixed(0)} bpm</span>
            </div>
            <div class="sidebar-row">
                <span class="sidebar-label">Massima</span>
                <span class="sidebar-value">${effort.max_hr.toFixed(0)} bpm</span>
            </div>
        </div>
    ` : '';
    
    let vamHtml = effort.avg_grade >= 4.5 ? `
        <div class="sidebar-row">
            <span class="sidebar-label">Teorico</span>
            <span class="sidebar-value">${effort.vam_teorico.toFixed(0)} m/h</span>
        </div>
    ` : '';
    
    const html = `
        <div class="sidebar-section">
            <div class="sidebar-title">⚡ POTENZA & RELATIVA & CADENZA & HR - Effort #${idx + 1}</div>
            <div style="color: #60a5fa; font-size: 11px; margin-bottom: 8px; font-weight: 600;">Potenza</div>
            <div class="sidebar-row">
                <span class="sidebar-label">Media</span>
                <span class="sidebar-value">${effort.avg.toFixed(0)} W</span>
            </div>
            <div class="sidebar-row">
                <span class="sidebar-label">Best 5s</span>
                <span class="sidebar-value">${effort.best_5s} W</span>
            </div>
            <div class="sidebar-row">
                <span class="sidebar-label">1ª metà</span>
                <span class="sidebar-value">${effort.watts_first.toFixed(0)} W</span>
            </div>
            <div class="sidebar-row">
                <span class="sidebar-label">2ª metà</span>
                <span class="sidebar-value">${effort.watts_second.toFixed(0)} W</span>
            </div>
            <div class="sidebar-row">
                <span class="sidebar-label">Rapporto</span>
                <span class="sidebar-value">${effort.watts_ratio.toFixed(2)}</span>
            </div>
            
            <div style="color: #60a5fa; font-size: 11px; margin-top: 12px; margin-bottom: 8px; font-weight: 600;">Potenza Relativa</div>
            <div class="sidebar-row">
                <span class="sidebar-label">Media</span>
                <span class="sidebar-value">${effort.w_kg.toFixed(2)} W/kg</span>
            </div>
            <div class="sidebar-row">
                <span class="sidebar-label">Best 5s</span>
                <span class="sidebar-value">${effort.best_5s_watt_kg.toFixed(2)} W/kg</span>
            </div>
            
            <div style="color: #60a5fa; font-size: 11px; margin-top: 12px; margin-bottom: 8px; font-weight: 600;">Cadenza & HR</div>
            <div class="sidebar-row">
                <span class="sidebar-label">🌀 Cadenza</span>
                <span class="sidebar-value">${effort.avg_cadence.toFixed(0)} rpm</span>
            </div>
            ${hrHtml}
        </div>
        
        <div class="sidebar-section">
            <div class="sidebar-title">⏱️ TEMPO & DISTANZA & ALTIMETRIA & VAM</div>
            <div style="color: #60a5fa; font-size: 11px; margin-bottom: 8px; font-weight: 600;">Tempo & Distanza</div>
            <div class="sidebar-row">
                <span class="sidebar-label">Durata</span>
                <span class="sidebar-value">${effort.duration}s</span>
            </div>
            <div class="sidebar-row">
                <span class="sidebar-label">Distanza</span>
                <span class="sidebar-value">${effort.distance_km.toFixed(2)} km</span>
            </div>
            <div class="sidebar-row">
                <span class="sidebar-label">Velocità</span>
                <span class="sidebar-value">${effort.avg_speed.toFixed(1)} km/h</span>
            </div>
            
            <div style="color: #60a5fa; font-size: 11px; margin-top: 12px; margin-bottom: 8px; font-weight: 600;">Altimetria</div>
            <div class="sidebar-row">
                <span class="sidebar-label">Guadagno</span>
                <span class="sidebar-value">${effort.elevation.toFixed(0)} m</span>
            </div>
            <div class="sidebar-row">
                <span class="sidebar-label">Media</span>
                <span class="sidebar-value">${effort.avg_grade.toFixed(1)}%</span>
            </div>
            <div class="sidebar-row">
                <span class="sidebar-label">Massima</span>
                <span class="sidebar-value">${effort.max_grade.toFixed(1)}%</span>
            </div>
            
            <div style="color: #60a5fa; font-size: 11px; margin-top: 12px; margin-bottom: 8px; font-weight: 600;">VAM</div>
            <div class="sidebar-row">
                <span class="sidebar-label">Effettivo</span>
                <span class="sidebar-value">${effort.vam.toFixed(0)} m/h</span>
            </div>
            ${vamHtml}
        </div>
        
        <div class="sidebar-section">
            <div class="sidebar-title">🔋 LAVORO & 🔥 DENSITÀ ORARIA</div>
            <div style="color: #60a5fa; font-size: 11px; margin-bottom: 8px; font-weight: 600;">Lavoro (kJ)</div>
            <div class="sidebar-row">
                <span class="sidebar-label">Totale</span>
                <span class="sidebar-value">${effort.kj.toFixed(0)} kJ</span>
            </div>
            <div class="sidebar-row">
                <span class="sidebar-label">Sopra CP</span>
                <span class="sidebar-value">${effort.kj_over_cp.toFixed(0)} kJ</span>
            </div>
            <div class="sidebar-row">
                <span class="sidebar-label">Per kg</span>
                <span class="sidebar-value">${effort.kj_kg.toFixed(1)} kJ/kg</span>
            </div>
            <div class="sidebar-row">
                <span class="sidebar-label">Per kg > CP</span>
                <span class="sidebar-value">${effort.kj_kg_over_cp.toFixed(1)} kJ/kg</span>
            </div>
            
            <div style="color: #60a5fa; font-size: 11px; margin-top: 12px; margin-bottom: 8px; font-weight: 600;">Densità Oraria (kJ/h/kg)</div>
            <div class="sidebar-row">
                <span class="sidebar-label">Totale</span>
                <span class="sidebar-value">${effort.kj_h_kg.toFixed(1)} kJ/h/kg</span>
            </div>
            <div class="sidebar-row">
                <span class="sidebar-label">Sopra CP</span>
                <span class="sidebar-value">${effort.kj_h_kg_over_cp.toFixed(1)} kJ/h/kg</span>
            </div>
        </div>
    `;
    
    document.getElementById('sidebar-content').innerHTML = html;
    
    highlightEffortInChart(idx);
    removeActiveEffortLayer();
    activeEffortIdx = idx;
    const layerId = `effort-${idx}`;
    activeEffortLayer = layerId;
    
    const effort_data = currentEfforts[idx];
    const segmentGeoJSON = {
        'type': 'Feature',
        'geometry': {
            'type': 'LineString',
            'coordinates': effort_data.segment
        }
    };
    
    map.addSource(layerId, { 'type': 'geojson', 'data': segmentGeoJSON });
    map.addLayer({
        'id': layerId,
        'type': 'line',
        'source': layerId,
        'paint': {
            'line-color': effort_data.color,
            'line-width': 6,
            'line-opacity': 0.8
        }
    });
}

function removeActiveEffortLayer() {
    if (activeEffortLayer && map.getLayer(activeEffortLayer)) {
        map.removeLayer(activeEffortLayer);
    }
    if (activeEffortLayer && map.getSource(activeEffortLayer)) {
        map.removeSource(activeEffortLayer);
    }
    activeEffortLayer = null;
}

function drawFullElevationChart() {
    const baseTrace = {
        x: elevationData.distance,
        y: elevationData.altitude,
        fill: 'tozeroy',
        type: 'scatter',
        name: 'Altitudine',
        line: { color: '#9ca3af', width: 1 },
        fillcolor: 'rgba(156,163,175,0.3)',
        hovertemplate: '<b>Distanza:</b> %{x:.2f} km<br><b>Altitudine:</b> %{y:.0f} m<extra></extra>'
    };
    
    const traces = [baseTrace];
    elevationData.efforts.forEach((effort, idx) => {
        const effortTrace = {
            x: effort.distance,
            y: effort.altitude,
            type: 'scatter',
            name: `Effort #${idx + 1}`,
            line: { color: effort.color, width: 3 },
            mode: 'lines',
            hovertemplate: '<b>Effort #' + (idx + 1) + '</b><br><b>Distanza:</b> %{x:.2f} km<br><b>Altitudine:</b> %{y:.0f} m<extra></extra>',
            opacity: 1,
            marker: { opacity: 0 }
        };
        traces.push(effortTrace);
    });
    
    const layout = {
        title: { text: '' },
        xaxis: {
            title: '',
            color: '#9ca3af',
            gridcolor: 'rgba(255,255,255,0.1)',
            showgrid: false
        },
        yaxis: {
            title: '',
            color: '#9ca3af',
            gridcolor: 'rgba(255,255,255,0.1)',
            showgrid: false
        },
        plot_bgcolor: 'rgba(15,23,42,0)',
        paper_bgcolor: 'rgba(15,23,42,.95)',
        font: { family: 'Segoe UI', color: '#9ca3af', size: 11 },
        margin: { l: 30, r: 10, t: 5, b: 20 },
        hovermode: 'x unified',
        showlegend: false
    };
    
    const config = { responsive: true, displayModeBar: false };
    Plotly.newPlot('elevation-chart', traces, layout, config);
}

function highlightEffortInChart(idx) {
    const update = {
        opacity: elevationData.efforts.map((_, i) => i === idx ? 1 : 0.2),
        'line.width': elevationData.efforts.map((_, i) => i === idx ? 4 : 3)
    };
    Plotly.restyle('elevation-chart', update, elevationData.efforts.map((_, i) => i + 1));
    
    const effort = elevationData.efforts[idx];
    const startDist = effort.distance[0];
    const endDist = effort.distance[effort.distance.length - 1];
    const maxAlt = Math.max(...effort.altitude);
    
    const infoBox = {
        x: (startDist + endDist) / 2,
        y: maxAlt * 0.9,
        text: `<b>Effort #${idx + 1}</b><br>${effort.avg.toFixed(0)} W`,
        showarrow: false,
        bgcolor: effort.color,
        bordercolor: '#fff',
        borderwidth: 1,
        font: { color: '#fff', size: 11 },
        align: 'center'
    };
    
    Plotly.relayout('elevation-chart', {
        annotations: [infoBox],
        'shapes[0]': {
            type: 'line',
            x0: startDist,
            x1: startDist,
            y0: 0,
            y1: maxAlt,
            xref: 'x',
            yref: 'y',
            line: { color: effort.color, width: 2, dash: 'dash' }
        },
        'shapes[1]': {
            type: 'line',
            x0: endDist,
            x1: endDist,
            y0: 0,
            y1: maxAlt,
            xref: 'x',
            yref: 'y',
            line: { color: effort.color, width: 2, dash: 'dash' }
        }
    });
}

function resetChartHighlight() {
    const update = {
        opacity: elevationData.efforts.map(() => 1),
        'line.width': elevationData.efforts.map(() => 3)
    };
    Plotly.restyle('elevation-chart', update, elevationData.efforts.map((_, i) => i + 1));
    
    Plotly.relayout('elevation-chart', {
        annotations: [],
        shapes: []
    });
}

let isResizing = false;
const resizeHandle = document.getElementById('resize-handle');
const elevationChart = document.getElementById('elevation-chart');
const mapDiv = document.getElementById('map');

resizeHandle.addEventListener('mousedown', (e) => {
    isResizing = true;
    e.preventDefault();
});

document.addEventListener('mousemove', (e) => {
    if (!isResizing) return;
    
    const newHeight = Math.max(100, Math.min(400, window.innerHeight - e.clientY));
    
    elevationChart.style.height = newHeight + 'px';
    mapDiv.style.bottom = newHeight + 'px';
    mapDiv.style.height = 'calc(100% - ' + newHeight + 'px)';
    
    Plotly.Plots.resize('elevation-chart');
});

document.addEventListener('mouseup', () => {
    isResizing = false;
});

function addTerrain() {
    try {
        if (!map.getSource('terrain-dem')) {
            map.addSource('terrain-dem', {
                'type': 'raster-dem',
                'url': `https://api.maptiler.com/tiles/terrain-rgb/tiles.json?key=${maptiler_key}`,
                'tileSize': 256
            });
        }
        map.setTerrain({ 'source': 'terrain-dem', 'exaggeration': 1.5 });
        console.log('Terrain enabled');
    } catch(e) { console.warn('Terrain not available:', e); }
}

function addOverlays() {
    if (!map.getSource('traccia')) {
        map.addSource('traccia', { 'type': 'geojson', 'data': tracceGeoJSON });
    } else {
        map.getSource('traccia').setData(tracceGeoJSON);
    }
    if (!map.getLayer('traccia-line')) {
        map.addLayer({
            'id': 'traccia-line',
            'type': 'line',
            'source': 'traccia',
            'paint': { 'line-color': '#FFB500', 'line-width': 4, 'line-opacity': 0.9 }
        });
    }
}

map.on('load', () => {
    addTerrain();
    addOverlays();

    const efforts = currentEfforts;

    efforts.forEach(function(effort, idx) {
        const feature = tracceGeoJSON.features[0];
        if (!feature || !feature.geometry || !feature.geometry.coordinates) {
            console.error('Invalid feature or coordinates:', feature);
            return;
        }
        const coordStart = feature.geometry.coordinates[effort.pos];
        if (!coordStart) {
            console.warn(`No coordinate at pos index ${effort.pos}`);
            return;
        }
        
        const el = document.createElement('div');
        el.style.width = '30px';
        el.style.height = '30px';
        el.style.borderRadius = '50%';
        el.style.backgroundColor = effort.color;
        el.style.border = '3px solid white';
        el.style.boxShadow = `0 2px 8px rgba(0,0,0,.6), 0 0 0 2px ${effort.color}`;
        el.style.cursor = 'pointer';
        el.style.display = 'flex';
        el.style.alignItems = 'center';
        el.style.justifyContent = 'center';
        el.style.fontSize = '14px';
        el.style.fontWeight = 'bold';
        el.style.color = 'white';
        el.innerHTML = (idx + 1);
        
        const marker = new maplibregl.Marker({ element: el })
            .setLngLat([coordStart[0], coordStart[1]])
            .setPopup(new maplibregl.Popup({ anchor: 'top', offset: [0, 15], maxWidth: 250 }).setHTML(`
                <div style="padding: 10px; font-size: 12px; color: #9ca3af; background: rgba(15,23,42,.95);">
                    <b style="color: #60a5fa;">Effort #${idx + 1}</b><br>
                    <div style="border-top: 1px solid rgba(255,255,255,.2); margin: 6px 0; padding-top: 6px;">
                        <div><b>⚡ ${effort.avg.toFixed(0)} W</b> | 🌀 ${effort.avg_cadence.toFixed(0)} rpm</div>
                        <div>⏱️ ${effort.duration}s | 🚴‍♂️ ${effort.avg_speed.toFixed(1)} km/h</div>
                    </div>
                </div>
            `))
            .addTo(map);
        
        el.addEventListener('click', () => {
            openEffortSidebar(idx);
            marker.getPopup().addTo(map);
        });
    });
    console.log('Markers added');
    
    drawFullElevationChart();
});

map.on('error', (e) => { console.error('Map error:', e); });

function updateStyleName() {
    document.getElementById('styleSelect').value = currentStyleIndex;
}

function applyStyle(newIndex) {
    currentStyleIndex = (newIndex + styles.length) % styles.length;
    const url = styles[currentStyleIndex].url;
    map.setStyle(url);
    const onStyle = () => {
        addTerrain();
        addOverlays();
        updateStyleName();
        map.off('styledata', onStyle);
    };
    map.on('styledata', onStyle);
}

function nextStyle() { applyStyle(currentStyleIndex + 1); }
function prevStyle() { applyStyle(currentStyleIndex - 1); }

document.getElementById('styleSelect').addEventListener('change', (e) => {
    applyStyle(parseInt(e.target.value));
});

function resetView() {
    map.flyTo({ center: [center_lon, center_lat], zoom: zoom, pitch: 45, bearing: 0, duration: 1500 });
}

document.getElementById('sidebar-close').addEventListener('click', () => {
    removeActiveEffortLayer();
    activeEffortIdx = null;
    resetChartHighlight();
    document.getElementById('sidebar-content').innerHTML = '';
});

map.on('load', () => { updateStyleName(); });
