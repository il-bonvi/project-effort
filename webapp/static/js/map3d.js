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
map.addControl(new maplibregl.NavigationControl());

const tracceGeoJSON = geojson_str;
const elevationData = elevation_data_json;

let activeEffortLayer = null;
let activeEffortIdx = null;
let currentEfforts = efforts_data_json;
let altimetryMarker = null;
let altimetrySelection = { start: null, end: null };
let isAltimetrySelecting = false;
let originalTracceGeoJSON = JSON.parse(JSON.stringify(geojson_str));
let lastAltimetryUpdate = 0;
let effortMarkers = [];  // Store effort marker references
let showEfforts = true;  // Toggle for efforts visibility
let showSprints = true;  // Toggle for sprints visibility

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

// ECharts elevation chart instance
let elevationChartInstance = null;

function drawFullElevationChart() {
    const container = document.getElementById('elevation-chart');
    if (!elevationChartInstance) {
        elevationChartInstance = echarts.init(container);
    }

    // Calculate min/max with fixed aspect ratio (professional cycling software approach)
    const elevations = elevationData.altitude;
    const minAlt = Math.min(...elevations);
    const maxAlt = Math.max(...elevations);
    const distances = elevationData.distance;
    const maxDist = Math.max(...distances);
    
    // INTERVALS.ICU APPROACH: elevation gain driven, not aspect ratio
    const elevationGain = maxAlt - minAlt;
    
    // PADDING: fixed values, but smart about going negative
    const paddingTop = 300;    // fisso +300m
    // paddingBottom: max 100m, but don't go below 0 unless altitude is actually negative
    const paddingBottom = minAlt >= 100 ? 100 : Math.max(0, minAlt * 0.5);
    
    // Y RANGE: based on actual elevation gain
    // rangeY ≈ max(elevGain × 1.5, elevGain + 200), capped at 3000m
    const rangeY_base = Math.max(elevationGain * 1.5, elevationGain + 200);
    const rangeY_final = Math.min(rangeY_base + paddingBottom + paddingTop, 3000);
    
    // ROUND values to nice numbers (no 137m nonsense)
    const roundTo = 50; // arrotonda a multipli di 50m
    const yMin = Math.floor((minAlt - paddingBottom) / roundTo) * roundTo;
    const yMax = Math.ceil((yMin + rangeY_final) / roundTo) * roundTo;

    // Prepare series data
    const seriesData = [
        {
            name: 'Altitudine',
            data: elevationData.distance.map((dist, idx) => [dist, elevationData.altitude[idx]]),
            type: 'line',
            smooth: false,
            stroke: 'none',
            symbolSize: 0,
            lineStyle: { color: '#9ca3af', width: 1 },
            areaStyle: { color: 'rgba(156, 163, 175, 0.3)' },
            markArea: { data: [] },
            markLine: { data: [], symbol: 'none', label: { show: false } },
            z: 1
        }
    ];

    // Add effort lines
    elevationData.efforts.forEach((effort, idx) => {
        seriesData.push({
            name: `Effort #${idx + 1}`,
            data: effort.distance.map((dist, i) => [dist, effort.altitude[i]]),
            type: 'line',
            smooth: false,
            symbolSize: 0,
            lineStyle: { color: effort.color, width: 3 },
            itemStyle: { opacity: 1 },
            z: 2
        });
    });

    const option = {
        tooltip: {
            trigger: 'axis',
            backgroundColor: 'rgba(15, 23, 42, 0.9)',
            borderColor: 'rgba(255, 255, 255, 0.2)',
            textStyle: { color: '#9ca3af', fontSize: 11 },
            formatter: function(params) {
                if (params.length === 0) return '';
                // Find the closest non-altitude series (effort line)
                let relevantParam = null;
                for (let p of params) {
                    if (p.seriesType === 'line' && p.seriesName !== 'Altitudine') {
                        relevantParam = p;
                        break;
                    }
                }
                // If no effort found, use altitude
                if (!relevantParam) {
                    relevantParam = params[0];
                }
                
                if (relevantParam.seriesType === 'line') {
                    const dist = relevantParam.value[0].toFixed(2);
                    const alt = relevantParam.value[1].toFixed(0);
                    const seriesName = relevantParam.seriesName;
                    
                    // Format based on series type
                    if (seriesName === 'Altitudine') {
                        return `Distanza: ${dist} km<br>Altitudine: ${alt} m`;
                    } else {
                        return `<b>⚡ ${seriesName}</b><br>Distanza: ${dist} km<br>Altitudine: ${alt} m`;
                    }
                }
                return '';
            }
        },
        grid: {
            left: 60,
            right: 20,
            top: 20,
            bottom: 30,
            containLabel: true
        },
        xAxis: {
            type: 'value',
            name: 'Distanza (km)',
            nameLocation: 'middle',
            nameGap: 25,
            nameTextStyle: { color: '#9ca3af', fontSize: 10 },
            min: 0,
            max: maxDist,
            axisLabel: { 
                color: '#9ca3af', 
                fontSize: 10,
                formatter: function(value) { return value.toFixed(1); }
            },
            axisLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.1)' } },
            splitLine: { show: false },
            boundaryGap: false
        },
        yAxis: {
            type: 'value',
            name: 'Altitudine (m)',
            nameLocation: 'middle',
            nameGap: 40,
            nameTextStyle: { color: '#9ca3af', fontSize: 10 },
            min: yMin,
            max: yMax,
            axisLabel: { color: '#9ca3af', fontSize: 10 },
            axisLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.1)' } },
            splitLine: { show: false },
            boundaryGap: false
        },
        backgroundColor: 'rgba(15, 23, 42, 0.95)',
        hoverLayerThreshold: Infinity,
        series: seriesData
    };

    elevationChartInstance.setOption(option);
    
    // Always clean up old listeners
    const chartContainer = document.getElementById('elevation-chart');
    if (chartContainer._handleMouseMove) {
        chartContainer.removeEventListener('mousemove', chartContainer._handleMouseMove);
    }
    if (chartContainer._handleMouseDown) {
        chartContainer.removeEventListener('mousedown', chartContainer._handleMouseDown);
    }
    if (chartContainer._handleMouseLeave) {
        chartContainer.removeEventListener('mouseleave', chartContainer._handleMouseLeave);
    }
    if (chartContainer._handleMouseUp) {
        document.removeEventListener('mouseup', chartContainer._handleMouseUp);
    }
    if (chartContainer._handleDoubleClick) {
        chartContainer.removeEventListener('dblclick', chartContainer._handleDoubleClick);
    }
    
    // Add fresh listeners - simplified to avoid marker errors
    const handleMouseMove = (e) => {
        if (!elevationChartInstance) return;
        
        // Only handle selection feedback, not hover marker
        if (!isAltimetrySelecting) return;
        
        const rect = chartContainer.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        if (x < 0 || y < 0 || x > rect.width || y > rect.height) return;
        
        try {
            const pointInGrid = elevationChartInstance.convertFromPixel('grid', [x, y]);
            if (pointInGrid && pointInGrid[0] !== undefined) {
                altimetrySelection.end = pointInGrid[0];
            }
        } catch(err) {
            // Silently ignore
        }
    };
    
    const handleMouseDown = (e) => {
        if (!elevationChartInstance || !map.loaded()) return;
        
        const rect = chartContainer.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        if (x < 0 || y < 0 || x > rect.width || y > rect.height) return;
        
        try {
            const pointInGrid = elevationChartInstance.convertFromPixel('grid', [x, y]);
            if (pointInGrid && pointInGrid[0] !== undefined) {
                isAltimetrySelecting = true;
                altimetrySelection.start = pointInGrid[0];
                altimetrySelection.end = pointInGrid[0];
                
                // Hide hover marker when starting selection
                if (altimetryMarker) {
                    altimetryMarker.remove();
                    altimetryMarker = null;
                }
            }
        } catch(err) {
            console.warn('Error in altimetry mousedown:', err);
        }
    };
    
    const handleMouseLeave = () => {
        if (!isAltimetrySelecting && altimetryMarker) {
            altimetryMarker.remove();
            altimetryMarker = null;
        }
        if (elevationChartInstance) {
            elevationChartInstance.dispatchAction({ type: 'hideTip' });
        }
        isAltimetrySelecting = false;
    };
    
    const handleMouseUp = (e) => {
        if (!isAltimetrySelecting) return;
        
        const rect = chartContainer.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        try {
            if (x >= 0 && y >= 0 && x <= rect.width && y <= rect.height) {
                const pointInGrid = elevationChartInstance.convertFromPixel('grid', [x, y]);
                if (pointInGrid && pointInGrid[0] !== undefined) {
                    altimetrySelection.end = pointInGrid[0];
                }
            }
        } catch(err) {
            console.warn('Error in altimetry mouseup:', err);
        }
        
        isAltimetrySelecting = false;
        
        if (Math.abs(altimetrySelection.start - altimetrySelection.end) > 0.5) {
            const start = Math.min(altimetrySelection.start, altimetrySelection.end);
            const end = Math.max(altimetrySelection.start, altimetrySelection.end);
            
            // Show selection area after drag completes
            if (elevationChartInstance) {
                const option = elevationChartInstance.getOption();
                if (option.series && option.series[0]) {
                    option.series[0].markArea.data = [
                        [
                            { xAxis: start, itemStyle: { color: 'rgba(59, 130, 246, 0.2)', borderColor: 'rgba(59, 130, 246, 0.5)', borderWidth: 1 } },
                            { xAxis: end }
                        ]
                    ];
                    option.series[0].markLine.data = [];
                    
                    elevationChartInstance.setOption(option, { lazyUpdate: true });
                }
            }
            
            filterTraceByDistance(start, end);
        } else {
            // Clear all marks if selection is too small
            if (elevationChartInstance) {
                const option = elevationChartInstance.getOption();
                if (option.series && option.series[0]) {
                    option.series[0].markArea.data = [];
                    option.series[0].markLine.data = [];
                    elevationChartInstance.setOption(option, { lazyUpdate: true });
                }
            }
        }
    };
    
    const handleDoubleClick = () => {
        resetTraceFilter();
    };
    
    // Update mousemove during selection to show range
    const originalHandleMouseMove = handleMouseMove;
    const enhancedHandleMouseMove = (e) => {
        originalHandleMouseMove(e);
        
        if (!isAltimetrySelecting || !elevationChartInstance) return;
        
        const rect = chartContainer.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        try {
            const pointInGrid = elevationChartInstance.convertFromPixel('grid', [x, y]);
            if (pointInGrid && pointInGrid[0] !== undefined) {
                altimetrySelection.end = pointInGrid[0];
                
                // Very aggressive throttling (200ms) to prevent lag while showing area highlight
                const now = Date.now();
                if (now - lastAltimetryUpdate > 10) {
                    lastAltimetryUpdate = now;
                    
                    const start = Math.min(altimetrySelection.start, altimetrySelection.end);
                    const end = Math.max(altimetrySelection.start, altimetrySelection.end);
                    
                    const option = elevationChartInstance.getOption();
                    
                    // Show area highlight during drag (same as static state)
                    if (option.series && option.series[0]) {
                        option.series[0].markArea.data = [
                            [
                                { xAxis: start, itemStyle: { color: 'rgba(59, 130, 246, 0.2)', borderColor: 'rgba(59, 130, 246, 0.5)', borderWidth: 1 } },
                                { xAxis: end }
                            ]
                        ];
                        option.series[0].markLine.data = [];
                        
                        elevationChartInstance.setOption(option, { lazyUpdate: true, silent: true });
                    }
                }
            }
        } catch(err) {
            // Silently ignore
        }
    };
    
    chartContainer.addEventListener('mousemove', enhancedHandleMouseMove);
    chartContainer.addEventListener('mouseleave', handleMouseLeave);
    chartContainer.addEventListener('mousedown', handleMouseDown);
    document.addEventListener('mouseup', handleMouseUp);
    chartContainer.addEventListener('dblclick', handleDoubleClick);
    
    // Store for cleanup
    chartContainer._handleMouseMove = enhancedHandleMouseMove;
    chartContainer._handleMouseDown = handleMouseDown;
    chartContainer._handleMouseLeave = handleMouseLeave;
    chartContainer._handleMouseUp = handleMouseUp;
    chartContainer._handleDoubleClick = handleDoubleClick;
}

function filterTraceByDistance(startDist, endDist) {
    if (!map || !originalTracceGeoJSON || !originalTracceGeoJSON.features[0]) return;
    
    const originalCoords = originalTracceGeoJSON.features[0].geometry.coordinates;
    const distances = elevationData.distance;
    
    // Find indices for the distance range
    let startIdx = 0, endIdx = distances.length - 1;
    
    for (let i = 0; i < distances.length; i++) {
        if (distances[i] >= startDist) {
            startIdx = i;
            break;
        }
    }
    
    for (let i = distances.length - 1; i >= 0; i--) {
        if (distances[i] <= endDist) {
            endIdx = i;
            break;
        }
    }
    
    // Create filtered GeoJSON with only selected segment
    const filteredCoords = originalCoords.slice(startIdx, endIdx + 1);
    const filteredGeoJSON = {
        type: 'FeatureCollection',
        features: [{
            type: 'Feature',
            geometry: {
                type: 'LineString',
                coordinates: filteredCoords
            }
        }]
    };
    
    // Update map source
    if (map.getSource('traccia')) {
        map.getSource('traccia').setData(filteredGeoJSON);
    }
    
    // Hide/show effort markers based on their distance range
    effortMarkers.forEach(({ marker, effortData, startDist: effortStart, endDist: effortEnd }) => {
        // Check if effort overlaps with selected range
        const effortOverlaps = !(effortEnd < startDist || effortStart > endDist);
        const markerElement = marker.getElement();
        markerElement.style.display = effortOverlaps ? 'flex' : 'none';
    });
    
    // Fit view to filtered segment
    const bounds = filteredCoords.reduce((bounds, coord) => {
        return bounds.extend(coord);
    }, new maplibregl.LngLatBounds(filteredCoords[0], filteredCoords[0]));
    
    map.fitBounds(bounds, { padding: 50, duration: 600 });
}

function resetTraceFilter() {
    if (!map) return;
    
    // Clean up marker
    if (altimetryMarker) {
        altimetryMarker.remove();
        altimetryMarker = null;
    }
    
    // Restore original trace
    if (map.getSource('traccia')) {
        map.getSource('traccia').setData(originalTracceGeoJSON);
    }
    
    // Show all effort markers again
    effortMarkers.forEach(({ marker }) => {
        const markerElement = marker.getElement();
        markerElement.style.display = 'flex';
    });
    
    // Reset selection
    altimetrySelection = { start: null, end: null };
    isAltimetrySelecting = false;
    
    // Clear selection highlights from chart
    if (elevationChartInstance) {
        const option = elevationChartInstance.getOption();
        if (option.series && option.series[0]) {
            option.series[0].markArea.data = [];
            option.series[0].markLine.data = [];
            elevationChartInstance.setOption(option, { lazyUpdate: true });
        }
    }
    
    // Restore original view
    map.flyTo({
        center: [center_lon, center_lat],
        zoom: zoom,
        pitch: 45,
        bearing: 0,
        duration: 1000
    });
}

function highlightEffortInChart(idx) {
    if (!elevationChartInstance) return;
    
    // Get current option and update series opacity/width
    const option = elevationChartInstance.getOption();
    
    option.series.forEach((series, i) => {
        if (i === 0) {
            // Base altitude line - always visible
            series.lineStyle.width = 1;
            series.lineStyle.opacity = 1;
        } else {
            // Effort lines
            const effortIdx = i - 1;
            if (effortIdx === idx) {
                // Selected effort - make it thicker but not too much
                series.lineStyle.width = 4;
                series.lineStyle.opacity = 1;
            } else {
                // Other efforts - keep them visible but slightly faded
                series.lineStyle.width = 2;
                series.lineStyle.opacity = 0.6;
            }
        }
    });
    
    elevationChartInstance.setOption(option);
}

function resetChartHighlight() {
    if (!elevationChartInstance) return;
    
    // Reset all series to default state
    const option = elevationChartInstance.getOption();
    
    option.series.forEach((series) => {
        if (series.name === 'Altitudine') {
            series.lineStyle.width = 1;
            series.lineStyle.opacity = 1;
        } else {
            series.lineStyle.width = 3;
            series.lineStyle.opacity = 1;
        }
    });
    
    elevationChartInstance.setOption(option);
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
    
    if (elevationChartInstance) {
        elevationChartInstance.resize();
    }
    if (map) {
        setTimeout(() => map.resize(), 0);
    }
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

    // Initialize effort markers with current visibility settings
    updateEffortVisibility();
    updateToggleButtons();
    
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
        updateEffortVisibility();
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

function toggleEfforts() {
    showEfforts = !showEfforts;
    updateEffortVisibility();
    updateToggleButtons();
}

function toggleSprints() {
    showSprints = !showSprints;
    updateEffortVisibility();
    updateToggleButtons();
}

function updateEffortVisibility() {
    // Remove all existing markers
    effortMarkers.forEach(({ marker }) => {
        marker.remove();
    });
    effortMarkers = [];
    
    // Re-add markers based on current visibility settings
    const efforts = currentEfforts;
    const feature = tracceGeoJSON.features[0];
    
    if (!feature || !feature.geometry || !feature.geometry.coordinates) {
        console.error('Invalid feature or coordinates:', feature);
        return;
    }
    
    efforts.forEach(function(effort, idx) {
        // Check visibility based on effort type
        const isSprint = effort.type === 'sprint';
        if ((isSprint && !showSprints) || (!isSprint && !showEfforts)) {
            return; // Skip this effort/sprint if not visible
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
                    <b style="color: #60a5fa;">${isSprint ? 'Sprint' : 'Effort'} #${idx + 1}</b><br>
                    <div style="border-top: 1px solid rgba(255,255,255,.2); margin: 6px 0; padding-top: 6px;">
                        <div><b>⚡ ${effort.avg.toFixed(0)} W</b> | 🌀 ${effort.avg_cadence.toFixed(0)} rpm</div>
                        <div>⏱️ ${effort.duration}s | 🚴‍♂️ ${effort.avg_speed.toFixed(1)} km/h</div>
                    </div>
                </div>
            `))
            .addTo(map);
        
        // Store marker with effort index and distance range
        effortMarkers.push({
            marker: marker,
            effortIdx: idx,
            effortData: effort,
            startDist: effort.distance[0],
            endDist: effort.distance[effort.distance.length - 1]
        });
        
        el.addEventListener('click', () => {
            openEffortSidebar(idx);
            marker.getPopup().addTo(map);
        });
    });
}

function updateToggleButtons() {
    const effortsBtn = document.getElementById('toggleEfforts');
    const sprintsBtn = document.getElementById('toggleSprints');
    
    if (effortsBtn) {
        effortsBtn.textContent = showEfforts ? '👊 Efforts: ON' : '👊 Efforts: OFF';
        effortsBtn.style.backgroundColor = showEfforts ? '#10b981' : '#ef4444';
    }
    
    if (sprintsBtn) {
        sprintsBtn.textContent = showSprints ? '🏃 Sprints: ON' : '🏃 Sprints: OFF';
        sprintsBtn.style.backgroundColor = showSprints ? '#10b981' : '#ef4444';
    }
}

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
