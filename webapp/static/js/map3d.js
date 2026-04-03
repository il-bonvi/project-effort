const styles = [
    { key: 'topo', name: 'Topo', url: `https://api.maptiler.com/maps/topo-v2/style.json?key=${maptiler_key}` },
    { key: 'streets', name: 'Streets', url: `https://api.maptiler.com/maps/streets-v2/style.json?key=${maptiler_key}` },
    { key: 'bright', name: 'Bright', url: `https://api.maptiler.com/maps/bright-v2/style.json?key=${maptiler_key}` },
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
const elevationTimes = elevationData.time || [];

const emptyFeatureCollection = { type: 'FeatureCollection', features: [] };
let power5sCache = null;

let activeEffortLayer = null;
let activeEffortIdx = null;
let activeSelectionType = null;
let currentSelectionRange = null;
let currentEfforts = efforts_data_json;
let altimetryMarker = null;
let altimetrySelection = { start: null, end: null };
let isAltimetrySelecting = false;
let altimetryDragEdge = null;
let altimetrySelectionBeforeDrag = null;
let originalTracceGeoJSON = JSON.parse(JSON.stringify(geojson_str));
let lastAltimetryUpdate = 0;
let effortMarkers = [];  // Store effort marker references
let showEfforts = true;  // Toggle for efforts visibility
let showSprints = true;  // Toggle for sprints visibility
const chartData = chart_data_json || { efforts: [], sprints: [], cp: 0, weight: 0, intensity_zones: [], torque_available: false };
let d3AltimetryState = null;
let currentSelectionMetrics = null;  // Store metrics for current manual selection
let isShowingEffortDetail = false;  // True when effort is shown (covers selection metrics)
let currentFullRideMetrics = null;   // Store metrics for full ride fallback in sidebar

function segmentStartsWithinSelection(segmentStartDist) {
    if (!currentSelectionRange) return true;
    const selStart = Math.min(Number(currentSelectionRange.startDist || 0), Number(currentSelectionRange.endDist || 0));
    const selEnd = Math.max(Number(currentSelectionRange.startDist || 0), Number(currentSelectionRange.endDist || 0));
    const start = Number(segmentStartDist);
    return Number.isFinite(start) && start >= selStart && start <= selEnd;
}

function applyChartVisibilityFilters() {
    if (!d3AltimetryState || !d3AltimetryState.root) return;

    d3AltimetryState.root.selectAll('.effort-segment').each(function(d) {
        const segment = elevationData.efforts[d.idx];
        const isSprint = segment && segment.type === 'sprint';
        const segStart = Array.isArray(segment?.distance) && segment.distance.length ? segment.distance[0] : NaN;
        const startsInsideSelection = segmentStartsWithinSelection(segStart);
        const shouldShow = (isSprint ? showSprints : showEfforts) && startsInsideSelection;
        const isSelected = activeEffortIdx === d.idx;
        d3.select(this)
            .style('display', shouldShow ? null : 'none')
            .attr('stroke-width', isSelected ? 4 : 3)
            .attr('stroke-opacity', isSelected ? 1 : 1);
    });
}

function setSelectionZonesDimmed(isDimmed) {
    if (!map || !map.getLayer('traccia-selected-zones-line')) return;

    if (isDimmed) {
        map.setPaintProperty('traccia-selected-zones-line', 'line-width', 4);
        map.setPaintProperty('traccia-selected-zones-line', 'line-opacity', 0.28);
    } else {
        map.setPaintProperty('traccia-selected-zones-line', 'line-width', 7);
        map.setPaintProperty('traccia-selected-zones-line', 'line-opacity', 1);
    }
}

function clearAltimetryMarker() {
    if (altimetryMarker) {
        altimetryMarker.remove();
        altimetryMarker = null;
    }
}

function ensureAltimetryMarker() {
    if (altimetryMarker) return altimetryMarker;

    const markerEl = document.createElement('div');
    markerEl.style.width = '14px';
    markerEl.style.height = '14px';
    markerEl.style.borderRadius = '50%';
    markerEl.style.background = '#f8fafc';
    markerEl.style.border = '3px solid #ef4444';
    markerEl.style.boxShadow = '0 0 0 3px rgba(239,68,68,0.25), 0 2px 8px rgba(0,0,0,0.35)';
    markerEl.style.pointerEvents = 'none';

    altimetryMarker = new maplibregl.Marker({ element: markerEl, anchor: 'center' })
        .setLngLat([center_lon, center_lat])
        .addTo(map);

    return altimetryMarker;
}

function findNearestDistanceIndex(distanceKm) {
    const distances = elevationData.distance || [];
    if (!distances.length) return -1;

    let low = 0;
    let high = distances.length - 1;
    while (low < high) {
        const mid = Math.floor((low + high) / 2);
        if (distances[mid] < distanceKm) low = mid + 1;
        else high = mid;
    }

    const idx = low;
    if (idx <= 0) return 0;
    if (idx >= distances.length) return distances.length - 1;

    const prev = idx - 1;
    return Math.abs(distances[idx] - distanceKm) < Math.abs(distances[prev] - distanceKm) ? idx : prev;
}

function updateAltimetryMarkerByDistance(distanceKm) {
    if (!map || !map.loaded()) return;

    const idx = findNearestDistanceIndex(distanceKm);
    if (idx < 0) return;

    const coords = originalTracceGeoJSON?.features?.[0]?.geometry?.coordinates;
    if (!coords || !coords[idx]) return;

    ensureAltimetryMarker().setLngLat([coords[idx][0], coords[idx][1]]);
}

function updateSelectionStreamButton() {
    const btn = document.getElementById('streamSelectionBtn');
    if (!btn) return;
    const hasSelection = !!(currentSelectionRange && currentSelectionRange.endIdx > currentSelectionRange.startIdx);
    btn.style.display = hasSelection ? 'block' : 'none';
    btn.disabled = !hasSelection;
}

function computePower5sProfile() {
    if (power5sCache) return power5sCache;

    const power = Array.isArray(elevationData.power) ? elevationData.power : [];
    const timeSec = Array.isArray(elevationData.time_sec) ? elevationData.time_sec : [];

    if (!power.length || power.length !== timeSec.length) {
        power5sCache = [];
        return power5sCache;
    }

    // Time-based 5s moving average to handle non-uniform FIT sampling.
    power5sCache = calculateTimeBasedMovingAverage(power, timeSec, 5);
    return power5sCache;
}

function zoneColorForPower(watts) {
    const cp = Number(chartData.cp || 0);
    if (!cp || cp <= 0) return '#6b7280';
    const pct = watts / cp * 100;
    const zones = getIntensityZones();
    for (const z of zones) {
        if (pct >= z.min && (z.max === 999 || pct < z.max)) return z.color;
    }
    return '#6b7280';
}

function buildZoneColoredSelectionGeoJSON(startIdx, endIdx) {
    const coords = originalTracceGeoJSON?.features?.[0]?.geometry?.coordinates || [];
    const power5s = computePower5sProfile();
    const features = [];

    if (!coords.length || !power5s.length) {
        return emptyFeatureCollection;
    }

    const first = Math.max(1, startIdx);
    const last = Math.min(endIdx, Math.min(coords.length, power5s.length) - 1);

    for (let i = first; i <= last; i++) {
        const c0 = coords[i - 1];
        const c1 = coords[i];
        if (!c0 || !c1) continue;
        features.push({
            type: 'Feature',
            properties: {
                color: zoneColorForPower(Number(power5s[i] || 0)),
                p5s: Number(power5s[i] || 0),
            },
            geometry: {
                type: 'LineString',
                coordinates: [c0, c1],
            },
        });
    }

    return { type: 'FeatureCollection', features };
}

function getDistanceRangeIndices(startDist, endDist) {
    const distances = elevationData.distance || [];
    let startIdx = 0;
    let endIdx = Math.max(0, distances.length - 1);

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

    return { startIdx, endIdx };
}

function buildSelectionStreamPayload() {
    if (!currentSelectionRange) return null;

    const timeSec = Array.isArray(elevationData.time_sec) ? elevationData.time_sec : [];
    const power = Array.isArray(elevationData.power) ? elevationData.power : [];
    const hr = Array.isArray(elevationData.heartrate) ? elevationData.heartrate : [];
    const distances = Array.isArray(elevationData.distance) ? elevationData.distance : [];

    const n = Math.min(timeSec.length, power.length);
    if (!n) return null;

    const s = Math.max(0, Math.min(currentSelectionRange.startIdx, n - 1));
    const e = Math.max(s, Math.min(currentSelectionRange.endIdx, n - 1));

    // Keep same context as effort stream charts: +/-120s around selected section.
    const bufferSeconds = 120;
    let sExt = s;
    let eExt = Math.min(n, e + 1);
    while (sExt > 0 && (timeSec[s] - timeSec[sExt - 1]) < bufferSeconds) sExt -= 1;
    while (eExt < n && (timeSec[eExt] - timeSec[e]) < bufferSeconds) eExt += 1;

    const t0 = timeSec[s];
    const timeStream = timeSec.slice(sExt, eExt).map((t) => Number((t - t0).toFixed(2)));
    const powerStream = power.slice(sExt, eExt).map((p) => Number(p || 0));
    const hrStream = hr.length ? hr.slice(sExt, eExt).map((h) => (h > 0 ? Number(h) : null)) : null;
    const w = Number(chartData.weight || 0);
    const wkgStream = powerStream.map((p) => (w > 0 ? p / w : 0));

    const effortEnd = Math.max(0, Number(timeSec[e] - timeSec[s]));
    const effortDuration = Math.round(effortEnd);
    const d0 = Number(distances[s] || currentSelectionRange.startDist || 0);
    const d1 = Number(distances[e] || currentSelectionRange.endDist || d0);

    return {
        data: {},
        type: 'effort',
        label: `SEL ${d0.toFixed(2)}-${d1.toFixed(2)} km`,
        timeStream,
        powerStream,
        hrStream,
        wkgStream,
        cadenceStream: null,
        torqueStream: null,
        speedStream: null,
        effortStart: 0,
        effortEnd,
        effortDuration,
    };
}

function calculateMetricsForRange(s, e) {

    const timeSec = Array.isArray(elevationData.time_sec) ? elevationData.time_sec : [];
    const power = Array.isArray(elevationData.power) ? elevationData.power : [];
    const hr = Array.isArray(elevationData.heartrate) ? elevationData.heartrate : [];
    const cadence = Array.isArray(elevationData.cadence) ? elevationData.cadence : [];
    const distances = Array.isArray(elevationData.distance) ? elevationData.distance : [];
    const altitudes = Array.isArray(elevationData.altitude) ? elevationData.altitude : [];

    if (e <= s || e >= power.length) return null;

    // Duration
    const durationSec = Math.max(0, timeSec[e] - timeSec[s]);
    const durationDisplay = fmtDur(durationSec);

    // Distance
    const distStart = distances[s] || 0;
    const distEnd = distances[e] || distStart;
    const distTot = Math.abs(distEnd - distStart);
    const distDisplay = distTot.toFixed(2);

    // Elevation
    const altStart = altitudes[s] || 0;
    const altEnd = altitudes[e] || altStart;
    const elevationGain = Math.max(0, altEnd - altStart);
    const elevationDisplay = Math.round(elevationGain);

    // Power metrics
    const powerSlice = power.slice(s, e + 1);
    const avgPower = powerSlice.length ? Math.round(powerSlice.reduce((a, b) => a + b, 0) / powerSlice.length) : 0;
    
    // 5s peak power (same strategy used for effort metrics)
    let peak5s = 0;
    if (powerSlice.length >= 5) {
        let maxAvg = 0;
        for (let i = 0; i <= powerSlice.length - 5; i++) {
            const avg5 = (powerSlice[i] + powerSlice[i+1] + powerSlice[i+2] + powerSlice[i+3] + powerSlice[i+4]) / 5;
            if (avg5 > maxAvg) maxAvg = avg5;
        }
        peak5s = Math.round(maxAvg);
    } else if (powerSlice.length > 0) {
        peak5s = Math.max(...powerSlice);
    }

    // HR metrics
    const hrSlice = hr.slice(s, e + 1).filter(h => h > 0 && !isNaN(h));
    const avgHr = hrSlice.length ? Math.round(hrSlice.reduce((a, b) => a + b, 0) / hrSlice.length) : 0;
    const maxHr = hrSlice.length ? Math.max(...hrSlice) : 0;

    // Weight and W/kg
    const weight = Number(chartData.weight || 0);
    const avgWkg = weight > 0 ? (avgPower / weight).toFixed(2) : 0;
    const peak5sWkg = weight > 0 ? (peak5s / weight).toFixed(2) : 0;

    // Speed: keep average from distance/time, derive max from smoothed point-to-point speed
    const avgSpeed = durationSec > 0 ? (distTot / (durationSec / 3600)).toFixed(1) : 0;
    const rawSpeed = [0];
    for (let i = s + 1; i <= e; i++) {
        const dt = Number(timeSec[i] || 0) - Number(timeSec[i - 1] || 0);
        const dd = Number(distances[i] || 0) - Number(distances[i - 1] || 0);
        if (dt > 0 && dd >= 0) {
            const speedKmh = dd / (dt / 3600);
            // Drop impossible spikes caused by timestamp/GPS noise.
            rawSpeed.push(Number.isFinite(speedKmh) && speedKmh <= 110 ? speedKmh : 0);
        } else {
            rawSpeed.push(0);
        }
    }

    const win = Math.min(3, rawSpeed.length);
    const smoothSpeed = rawSpeed.map((_, i) => {
        const start = Math.max(0, i - Math.floor(win / 2));
        const end = Math.min(rawSpeed.length, i + Math.floor(win / 2) + 1);
        const slice = rawSpeed.slice(start, end);
        return slice.length ? (slice.reduce((a, b) => a + b, 0) / slice.length) : 0;
    });
    const maxSpeed = Number((smoothSpeed.length ? Math.max(...smoothSpeed) : 0).toFixed(1));

    // Grade
    const avgGrade = distTot > 0 ? ((elevationGain / (distTot * 1000)) * 100).toFixed(1) : 0;
    let maxGrade = 0;
    for (let i = s + 1; i <= e; i++) {
        const dDistKm = Number(distances[i] || 0) - Number(distances[i - 1] || 0);
        const dAlt = Number(altitudes[i] || 0) - Number(altitudes[i - 1] || 0);
        if (dDistKm > 0) {
            const g = (dAlt / (dDistKm * 1000)) * 100;
            if (Number.isFinite(g) && g > maxGrade) maxGrade = g;
        }
    }
    maxGrade = Number(maxGrade.toFixed(1));

    // VAM (vertical ascent rate in m/h)
    const vam = durationSec > 0 ? Math.round((elevationGain / (durationSec / 3600))) : 0;

    // Energy (kJ) - total
    const totalPowerSum = powerSlice.reduce((a, b) => a + b, 0);
    const kJ = Math.round(totalPowerSum * durationSec / powerSlice.length / 1000);
    
    // Energy > CP (same semantics used in backend: counts full power when p > CP)
    const cp = Number(chartData.cp || 0);
    let kJOverCp = 0;
    if (cp > 0) {
        const powerAboveCpSum = powerSlice.reduce((sum, p) => (p > cp ? sum + p : sum), 0);
        kJOverCp = Math.round(powerAboveCpSum * durationSec / powerSlice.length / 1000);
    }

    const kJkg = weight > 0 ? (kJ / weight).toFixed(1) : 0;
    const kJkgOverCp = weight > 0 ? (kJOverCp / weight).toFixed(1) : 0;
    const hours = durationSec / 3600;
    const kJhKg = weight > 0 && hours > 0 ? ((kJ / weight) / hours).toFixed(1) : 0;
    const kJhKgOverCp = weight > 0 && hours > 0 ? ((kJOverCp / weight) / hours).toFixed(1) : 0;
    
    // Cadence and pacing split (same fields shown in effort card)
    const cadSlice = cadence.slice(s, e + 1).filter((c) => Number(c) > 0);
    const avgCadence = cadSlice.length ? Math.round(cadSlice.reduce((a, b) => a + Number(b), 0) / cadSlice.length) : 0;
    const half = Math.floor(powerSlice.length / 2);
    const firstHalf = half > 0 ? powerSlice.slice(0, half) : [];
    const secondHalf = half > 0 ? powerSlice.slice(half) : [];
    const avgWattsFirst = firstHalf.length ? Math.round(firstHalf.reduce((a, b) => a + b, 0) / firstHalf.length) : 0;
    const avgWattsSecond = secondHalf.length ? Math.round(secondHalf.reduce((a, b) => a + b, 0) / secondHalf.length) : 0;
    const wattsRatio = avgWattsSecond > 0 ? (avgWattsFirst / avgWattsSecond).toFixed(2) : '0.00';
    
    // Theoretical values aligned with effort formulas
    const avgGradeNum = Number(avgGrade);
    const avgWkgNum = Number(avgWkg);
    const gradientFactor = 2 + (avgGradeNum / 10);
    const vamTeorico = weight > 0 ? Math.round(avgWkgNum * (gradientFactor * 100)) : 0;
    const wkgTeoricoNum = gradientFactor > 0 ? (vam / (gradientFactor * 100)) : 0;
    const diffWkgNum = Math.abs(avgWkgNum - wkgTeoricoNum);
    const percErrNum = avgWkgNum !== 0 ? (((wkgTeoricoNum - avgWkgNum) / avgWkgNum) * 100) : 0;
    const vamArrow = (vamTeorico - vam) > 0 ? '⬆️' : ((vamTeorico - vam) < 0 ? '⬇️' : '');
    const diffVam = Math.round(Math.abs(vamTeorico - vam));
    const wkgTeorico = wkgTeoricoNum.toFixed(2);
    const diffWkg = diffWkgNum.toFixed(2);
    const percErr = (percErrNum >= 0 ? '+' : '-') + Math.abs(percErrNum).toFixed(1);

    return {
        label: `SEL ${distStart.toFixed(2)}-${distEnd.toFixed(2)} km`,
        startDist: distStart,
        endDist: distEnd,
        durationSec,
        durationDisplay,
        distTot,
        distDisplay,
        elevationGain,
        elevationDisplay,
        avgPower,
        avgWkg,
        peak5s,
        peak5sWkg,
        avgHr,
        maxHr,
        avgSpeed,
        maxSpeed,
        avgGrade,
        maxGrade,
        vam,
        vamTeorico,
        vamArrow,
        diffVam,
        kJ,
        kJOverCp,
        kJkg,
        kJkgOverCp,
        kJhKg,
        kJhKgOverCp,
        avgCadence,
        avgWattsFirst,
        avgWattsSecond,
        wattsRatio,
        wkgTeorico,
        diffWkg,
        percErr,
    };
}

function calculateSelectionMetrics() {
    if (!currentSelectionRange) return null;
    return calculateMetricsForRange(currentSelectionRange.startIdx, currentSelectionRange.endIdx);
}

function format_time_mmss(seconds) {
    if (!seconds || seconds < 0) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function fmtDur(seconds) {
    const s = Math.round(seconds || 0);
    const m = Math.floor(s / 60);
    const r = s % 60;
    return m > 0 ? `${m}m${r}s` : `${s}s`;
}

function findSelectedSegment(markerItem) {
    if (!markerItem) return null;

    if (markerItem.type === 'sprint') {
        const sprint = chartData.sprints.find((s) => String(s.id) === String(markerItem.id));
        return sprint ? { data: sprint, type: 'sprint' } : null;
    }

    const effort = chartData.efforts.find((e) => String(e.id) === String(markerItem.id));
    if (effort) return { data: effort, type: 'effort' };

    const sprintFallback = chartData.sprints.find((s) => String(s.id) === String(markerItem.id));
    if (sprintFallback) return { data: sprintFallback, type: 'sprint' };

    // Last fallback: if payload lacks type but keeps sprint color convention.
    if (markerItem.color === '#000000') {
        const byDistance = chartData.sprints.find((s) => {
            const start = Number(markerItem.distance?.[0] ?? markerItem.start ?? 0);
            const end = Number(markerItem.distance?.[markerItem.distance.length - 1] ?? markerItem.end ?? start);
            const sStart = Number(s.line_data?.[0]?.[0] ?? 0);
            const sEnd = Number(s.line_data?.[s.line_data.length - 1]?.[0] ?? sStart);
            return Math.abs(start - sStart) < 0.05 && Math.abs(end - sEnd) < 0.05;
        });
        if (byDistance) return { data: byDistance, type: 'sprint' };
    }

    return null;
}

function buildSelectionMetricsCard(metrics) {
    if (!metrics) return '';
    const m = metrics;
    const showVamTeor = Number(m.avgGrade) >= 4.5;
    const signDwkg = Number(m.diffWkg) > 0 ? '+' : '';
    const theoreticalRows = showVamTeor
        ? `
        <div class="metric-row"><span class="metric-label">🧮 VAM Teor.</span><span class="metric-value">${m.vamTeorico} m/h</span></div>
        <div class="metric-row"><span class="metric-label">🧮 W/kg Teor.</span><span class="metric-value">${m.wkgTeorico} · Δ${signDwkg}${m.diffWkg}</span></div>
        <div class="metric-row"><span class="metric-label">Err %</span><span class="metric-value">${m.percErr}%</span></div>
    `
        : '';
    
    const vamSection = `
        <div class="metric-row"><span class="metric-label">🚵 VAM</span><span class="metric-value">${showVamTeor ? `${m.vam} m/h ${m.vamArrow} ${m.diffVam} m/h` : `${m.vam} m/h`}</span></div>
        ${theoreticalRows}
    `;

    return `
        <div class="selected-header">
            <div>
                <div class="selected-title">${m.cardTitle || '🔍 Selection'}</div>
                <div class="selected-subtitle-line">${m.distDisplay} km · ${m.elevationDisplay}m ↑</div>
                <div class="selected-subtitle-line">${m.durationDisplay}</div>
                <div class="selected-power">${m.avgPower}W <span>(${m.avgWkg} W/kg)</span></div>
            </div>
            <button class="stream-btn" id="selectionStreamBtn" onclick="openSelectionStreamModal()">📊 Stream</button>
        </div>
        <div class="selected-grid">
            <div class="metric-col">
                <div class="metric-row"><span class="metric-label">⚡ Avg</span><span class="metric-value">${m.avgPower}W</span></div>
                <div class="metric-row"><span class="metric-label">⚖️ W/kg</span><span class="metric-value">${m.avgWkg}</span></div>
                <div class="metric-row"><span class="metric-label">5″🔺 Peak</span><span class="metric-value">${m.peak5s}W · ${m.peak5sWkg} W/kg</span></div>
                <div class="metric-row"><span class="metric-label">🌀 Cadence</span><span class="metric-value">${m.avgCadence > 0 ? `${m.avgCadence} rpm` : '-'}</span></div>
                <div class="metric-row"><span class="metric-label">🔀 1st/2nd</span><span class="metric-value">${m.avgWattsFirst}/${m.avgWattsSecond} · ${m.wattsRatio}</span></div>
            </div>
            <div class="metric-col">
                <div class="metric-row"><span class="metric-label">❤️ HR</span><span class="metric-value">${m.avgHr > 0 ? `${m.avgHr} bpm · 🔺${m.maxHr} bpm` : '-'}</span></div>
                <div class="metric-row"><span class="metric-label">🚴 Speed</span><span class="metric-value">${m.avgSpeed} km/h · 🔺${m.maxSpeed} km/h</span></div>
                <div class="metric-row"><span class="metric-label">📏 Grade</span><span class="metric-value">${m.avgGrade}% · 🔺${m.maxGrade}%</span></div>
                ${vamSection}
            </div>
            <div class="metric-col">
                <div class="metric-row"><span class="metric-label">🔋 kJ Total</span><span class="metric-value">${m.kJ} kJ</span></div>
                <div class="metric-row"><span class="metric-label">kJ &gt; CP</span><span class="metric-value">${m.kJOverCp} kJ</span></div>
                <div class="metric-row"><span class="metric-label">💪 kJ/kg</span><span class="metric-value">${m.kJkg}</span></div>
                <div class="metric-row"><span class="metric-label">kJ/kg &gt; CP</span><span class="metric-value">${m.kJkgOverCp}</span></div>
                <div class="metric-row"><span class="metric-label">🔥 kJ/h/kg</span><span class="metric-value">${m.kJhKg}</span></div>
                <div class="metric-row"><span class="metric-label">kJ/h/kg &gt; CP</span><span class="metric-value">${m.kJhKgOverCp}</span></div>
            </div>
        </div>
    `;
}

function buildEffortSidebarCard(e) {
    const signErr = e.perc_err > 0 ? '+' : (e.perc_err < 0 ? '-' : '');
    const signDwkg = e.diff_wkg > 0 ? '+' : '';
    const showVamTeor = e.avg_grade >= 4.5;
    const vamSection = `
        <div class="metric-row"><span class="metric-label">🚵 VAM</span><span class="metric-value">${showVamTeor ? `${e.vam} m/h ${e.vam_arrow} ${e.diff_vam} m/h` : `${e.vam} m/h`}</span></div>
        <div class="metric-row"><span class="metric-label">🧮 VAM Teor.</span><span class="metric-value">${showVamTeor ? `${e.vam_teorico} m/h` : '-'}</span></div>
        <div class="metric-row"><span class="metric-label">🧮 W/kg Teor.</span><span class="metric-value">${showVamTeor ? `${e.wkg_teoric} · Δ${signDwkg}${e.diff_wkg}` : '-'}</span></div>
        <div class="metric-row"><span class="metric-label">Err %</span><span class="metric-value">${showVamTeor ? `${signErr}${Math.abs(e.perc_err)}%` : '-'}</span></div>
    `;

    return `
        <div class="selected-header">
            <div>
                <div class="selected-title">E#${e.id + 1} · Rank #${e.rank}</div>
                <div class="selected-subtitle-line">${e.start_time}</div>
                <div class="selected-subtitle-line">${fmtDur(e.duration)} · ${e.distance_tot} km · ${e.elevation_gain}m ↑</div>
                <div class="selected-power" style="color:${e.color}">${e.avg_power}W <span>(${e.cp_pct}%)</span></div>
            </div>
            <div style="display: flex; gap: 8px; align-items: center;">
                <button class="stream-btn" onclick="openStreamModal('e-${e.id}','${e.id}','effort')">📊 Stream</button>
                <button class="sidebar-close-btn" onclick="closeEffortDetailAndShowSelection()">✕</button>
            </div>
        </div>
        <div class="selected-grid">
            <div class="metric-col">
                <div class="metric-row"><span class="metric-label">⚡ Avg</span><span class="metric-value">${e.avg_power}W</span></div>
                <div class="metric-row"><span class="metric-label">⚖️ W/kg</span><span class="metric-value">${e.avg_power_per_kg}</span></div>
                <div class="metric-row"><span class="metric-label">5″🔺 Peak</span><span class="metric-value">${e.best_5s_watt}W · ${e.best_5s_watt_kg} W/kg</span></div>
                <div class="metric-row"><span class="metric-label">🌀 Cadence</span><span class="metric-value">${e.avg_cadence} rpm</span></div>
                <div class="metric-row"><span class="metric-label">🔀 1st/2nd</span><span class="metric-value">${e.avg_watts_first}/${e.avg_watts_second} · ${e.watts_ratio}</span></div>
            </div>
            <div class="metric-col">
                <div class="metric-row"><span class="metric-label">❤️ HR</span><span class="metric-value">${e.avg_hr > 0 ? `${e.avg_hr} bpm · 🔺${e.max_hr > 0 ? e.max_hr : '-'} bpm` : '-'}</span></div>
                <div class="metric-row"><span class="metric-label">🚴 Speed</span><span class="metric-value">${e.avg_speed} km/h</span></div>
                <div class="metric-row"><span class="metric-label">📏 Grade</span><span class="metric-value">${e.avg_grade}% · 🔺${e.max_grade}%</span></div>
                ${vamSection}
            </div>
            <div class="metric-col">
                <div class="metric-row"><span class="metric-label">🔋 kJ Total</span><span class="metric-value">${e.kj} kJ</span></div>
                <div class="metric-row"><span class="metric-label">kJ &gt; CP</span><span class="metric-value">${e.kj_over_cp} kJ</span></div>
                <div class="metric-row"><span class="metric-label">💪 kJ/kg</span><span class="metric-value">${e.kj_kg}</span></div>
                <div class="metric-row"><span class="metric-label">kJ/kg &gt; CP</span><span class="metric-value">${e.kj_kg_over_cp}</span></div>
                <div class="metric-row"><span class="metric-label">🔥 kJ/h/kg</span><span class="metric-value">${e.kj_h_kg}</span></div>
                <div class="metric-row"><span class="metric-label">kJ/h/kg &gt; CP</span><span class="metric-value">${e.kj_h_kg_over_cp}</span></div>
            </div>
        </div>
    `;
}

function buildSprintSidebarCard(s) {
    const torqAvail = chartData.torque_available;
    const torqRows = torqAvail
        ? `
            <div class="metric-row"><span class="metric-label">⚙️ Avg Torque</span><span class="metric-value">${s.avg_torque > 0 ? `${s.avg_torque} Nm` : '-'}</span></div>
            <div class="metric-row"><span class="metric-label">⚙️ Min/Max Torque</span><span class="metric-value">${s.min_torque > 0 ? s.min_torque : '-'} / ${s.max_torque > 0 ? s.max_torque : '-'} Nm</span></div>
        `
        : '';

    return `
        <div class="selected-header">
            <div>
                <div class="selected-title">S#${s.rank}</div>
                <div class="selected-subtitle-line">${s.start_time}</div>
                <div class="selected-subtitle-line">${fmtDur(s.duration)} · ${s.distance_tot} km · ${s.elevation_gain}m ↑</div>
                <div class="selected-power">${s.avg_power}W</div>
            </div>
            <div style="display: flex; gap: 8px; align-items: center;">
                <button class="stream-btn" onclick="openStreamModal('s-${s.id}','${s.id}','sprint')">📊 Stream</button>
                <button class="sidebar-close-btn" onclick="closeEffortDetailAndShowSelection()">✕</button>
            </div>
        </div>
        <div class="selected-grid">
            <div class="metric-col">
                <div class="metric-row"><span class="metric-label">⚡ Avg Power</span><span class="metric-value">${s.avg_power}W</span></div>
                <div class="metric-row"><span class="metric-label">⚖️ W/kg</span><span class="metric-value">${s.avg_power_per_kg}</span></div>
                <div class="metric-row"><span class="metric-label">⚡ Max</span><span class="metric-value">${s.max_watt}W${s.rpm_at_max > 0 ? ` @ ${s.rpm_at_max} rpm` : ''}</span></div>
                <div class="metric-row"><span class="metric-label">⚡ Min</span><span class="metric-value">${s.min_watt}W${s.rpm_at_min > 0 ? ` @ ${s.rpm_at_min} rpm` : ''}</span></div>
            </div>
            <div class="metric-col">
                <div class="metric-row"><span class="metric-label">🌀 Avg Cad.</span><span class="metric-value">${s.avg_cadence > 0 ? `${s.avg_cadence} rpm` : '-'}</span></div>
                <div class="metric-row"><span class="metric-label">🌀 Min/Max</span><span class="metric-value">${s.min_cadence > 0 ? s.min_cadence : '-'} / ${s.max_cadence > 0 ? s.max_cadence : '-'} rpm</span></div>
                ${torqRows}
                <div class="metric-row"><span class="metric-label">❤️ HR</span><span class="metric-value">${s.max_hr > 0 ? `${s.min_hr > 0 ? s.min_hr : '-'} bpm · 🔺${s.max_hr} bpm` : '-'}</span></div>
                <div class="metric-row"><span class="metric-label">📏 Grade</span><span class="metric-value">${s.avg_grade}% · 🔺${s.max_grade}%</span></div>
            </div>
            <div class="metric-col">
                <div class="metric-row"><span class="metric-label">➡️ Speed Start</span><span class="metric-value">${s.v1 > 0 ? `${s.v1} km/h` : '-'}</span></div>
                <div class="metric-row"><span class="metric-label">➡️ Speed End</span><span class="metric-value">${s.v2 > 0 ? `${s.v2} km/h` : '-'}</span></div>
                <div class="metric-row"><span class="metric-label">🔋 kJ Total</span><span class="metric-value">${s.kj} kJ</span></div>
                <div class="metric-row"><span class="metric-label">kJ &gt; CP</span><span class="metric-value">${s.kj_over_cp} kJ</span></div>
                <div class="metric-row"><span class="metric-label">💪 kJ/kg</span><span class="metric-value">${s.kj_kg}</span></div>
                <div class="metric-row"><span class="metric-label">kJ/kg &gt; CP</span><span class="metric-value">${s.kj_kg_over_cp}</span></div>
                <div class="metric-row"><span class="metric-label">🔥 kJ/h/kg</span><span class="metric-value">${s.kj_h_kg}</span></div>
                <div class="metric-row"><span class="metric-label">kJ/h/kg &gt; CP</span><span class="metric-value">${s.kj_h_kg_over_cp}</span></div>
            </div>
        </div>
    `;
}

function openEffortSidebar(idx) {
    const markerItem = currentEfforts[idx];
    const selected = findSelectedSegment(markerItem);

    if (!selected) {
        document.getElementById('sidebar-content').innerHTML = '<div class="sidebar-empty">Nessun dettaglio disponibile per il segmento selezionato.</div>';
        return;
    }

    const html = selected.type === 'effort'
        ? buildEffortSidebarCard(selected.data)
        : buildSprintSidebarCard(selected.data);

    activeSelectionType = selected.type;
    setSelectionZonesDimmed(selected.type === 'effort' || selected.type === 'sprint');

    document.getElementById('sidebar-content').innerHTML = html;
    isShowingEffortDetail = true;
    
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
            'line-width': 8,
            'line-opacity': 1
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

function showSelectionMetricsCard() {
    if (!currentSelectionMetrics) return;
    currentSelectionMetrics.cardTitle = '🔍 Selection';
    const html = buildSelectionMetricsCard(currentSelectionMetrics);
    document.getElementById('sidebar-content').innerHTML = html;
    isShowingEffortDetail = false;
}

function showFullRideMetricsCard() {
    const distances = Array.isArray(elevationData.distance) ? elevationData.distance : [];
    if (distances.length < 2) {
        document.getElementById('sidebar-content').innerHTML = '';
        return;
    }

    currentFullRideMetrics = calculateMetricsForRange(0, distances.length - 1);
    if (!currentFullRideMetrics) {
        document.getElementById('sidebar-content').innerHTML = '';
        return;
    }

    currentFullRideMetrics.cardTitle = '🚴 Full Ride';
    document.getElementById('sidebar-content').innerHTML = buildSelectionMetricsCard(currentFullRideMetrics);
    isShowingEffortDetail = false;
}

function closeEffortDetailAndShowSelection() {
    removeActiveEffortLayer();
    activeEffortIdx = null;
    activeSelectionType = null;
    setSelectionZonesDimmed(false);
    resetChartHighlight();
    if (currentSelectionMetrics) showSelectionMetricsCard();
    else showFullRideMetricsCard();
}

// D3 altimetry chart state holder
let elevationChartInstance = null;

function drawFullElevationChart() {
    const container = document.getElementById('elevation-chart');
    const resizeHandle = document.getElementById('resize-handle');
    if (!container || !resizeHandle) return;

    if (d3AltimetryState && d3AltimetryState.cleanup) d3AltimetryState.cleanup();

    container.querySelectorAll('svg').forEach((n) => n.remove());
    const hoverTip = container.querySelector('.altimetry-hover-tip');
    if (hoverTip) hoverTip.remove();
    container.appendChild(resizeHandle);

    const rect = container.getBoundingClientRect();
    const width = Math.max(320, Math.floor(rect.width));
    const height = Math.max(120, Math.floor(rect.height));
    const margin = { top: 16, right: 16, bottom: 26, left: 56 };
    const innerW = Math.max(10, width - margin.left - margin.right);
    const innerH = Math.max(10, height - margin.top - margin.bottom);

    const distances = elevationData.distance || [];
    const altitudes = elevationData.altitude || [];
    if (!distances.length || !altitudes.length) return;

    const minAlt = Math.min(...altitudes);
    const maxAlt = Math.max(...altitudes);
    const elevationGain = maxAlt - minAlt;
    const paddingTop = 300;
    const paddingBottom = minAlt >= 100 ? 100 : Math.max(0, minAlt * 0.5);
    const rangeYBase = Math.max(elevationGain * 1.5, elevationGain + 200);
    const rangeYFinal = Math.min(rangeYBase + paddingBottom + paddingTop, 3000);
    const roundTo = 50;
    const yMin = Math.floor((minAlt - paddingBottom) / roundTo) * roundTo;
    const yMax = Math.ceil((yMin + rangeYFinal) / roundTo) * roundTo;
    const xMax = Math.max(...distances);

    const xScale = d3.scaleLinear().domain([0, xMax]).range([0, innerW]);
    const yScale = d3.scaleLinear().domain([yMin, yMax]).range([innerH, 0]);

    const svg = d3.select(container)
        .append('svg')
        .attr('width', width)
        .attr('height', height)
        .style('display', 'block')
        .style('background', 'rgba(15, 23, 42, 0.95)');

    const root = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    root.append('path')
        .datum(distances.map((d, i) => ({ d, a: altitudes[i] })))
        .attr('fill', 'rgba(156, 163, 175, 0.3)')
        .attr('stroke', 'none')
        .attr('d', d3.area().x((p) => xScale(p.d)).y0(innerH).y1((p) => yScale(p.a)));

    root.append('path')
        .datum(distances.map((d, i) => ({ d, a: altitudes[i] })))
        .attr('fill', 'none')
        .attr('stroke', '#9ca3af')
        .attr('stroke-width', 1)
        .attr('d', d3.line().x((p) => xScale(p.d)).y((p) => yScale(p.a)));

    const segmentLayer = root.append('g').attr('class', 'segment-layer');
    elevationData.efforts.forEach((effort, idx) => {
        const pts = (effort.distance || []).map((d, i) => ({ d, a: (effort.altitude || [])[i] }));
        segmentLayer.append('path')
            .datum({ idx, type: effort.type || 'effort' })
            .attr('class', 'effort-segment')
            .attr('data-idx', String(idx))
            .attr('fill', 'none')
            .attr('stroke', effort.color || '#60a5fa')
            .attr('stroke-width', 3)
            .attr('stroke-opacity', 1)
            .attr('d', d3.line().x((p) => xScale(p.d)).y((p) => yScale(p.a))(pts));
    });

    const selLayer = root.append('g').attr('class', 'selection-layer');
    const selRect = selLayer.append('rect')
        .attr('y', 0)
        .attr('height', innerH)
        .attr('fill', 'rgba(59, 130, 246, 0.2)')
        .attr('stroke', 'rgba(59, 130, 246, 0.5)')
        .attr('stroke-width', 1)
        .style('display', 'none');

    const xAxis = d3.axisBottom(xScale).ticks(8).tickFormat((v) => Number(v).toFixed(1));
    const yAxis = d3.axisLeft(yScale).ticks(5);
    root.append('g').attr('transform', `translate(0,${innerH})`).call(xAxis)
        .call((g) => g.selectAll('text').attr('fill', '#9ca3af').attr('font-size', 10))
        .call((g) => g.selectAll('line,path').attr('stroke', 'rgba(255,255,255,0.1)'));
    root.append('g').call(yAxis)
        .call((g) => g.selectAll('text').attr('fill', '#9ca3af').attr('font-size', 10))
        .call((g) => g.selectAll('line,path').attr('stroke', 'rgba(255,255,255,0.1)'));

    const hoverLine = root.append('line')
        .attr('y1', 0).attr('y2', innerH)
        .attr('stroke', 'rgba(203,213,225,0.6)')
        .attr('stroke-width', 1)
        .attr('stroke-dasharray', '3,3')
        .style('display', 'none');

    const hoverTipEl = document.createElement('div');
    hoverTipEl.className = 'altimetry-hover-tip';
    hoverTipEl.style.position = 'absolute';
    hoverTipEl.style.pointerEvents = 'none';
    hoverTipEl.style.display = 'none';
    hoverTipEl.style.background = 'rgba(15,23,42,0.92)';
    hoverTipEl.style.border = '1px solid rgba(255,255,255,0.15)';
    hoverTipEl.style.color = '#cbd5e1';
    hoverTipEl.style.fontSize = '11px';
    hoverTipEl.style.padding = '4px 6px';
    hoverTipEl.style.borderRadius = '6px';
    container.appendChild(hoverTipEl);

    function getDistanceAtPixel(clientX) {
        const cRect = container.getBoundingClientRect();
        const xLocal = clientX - cRect.left - margin.left;
        const xClamped = Math.max(0, Math.min(innerW, xLocal));
        return { distanceKm: xScale.invert(xClamped), xClamped };
    }

    function detectSelectionEdgeAtPixel(clientX) {
        if (altimetrySelection.start == null || altimetrySelection.end == null) return null;
        const cRect = container.getBoundingClientRect();
        const xLocal = clientX - cRect.left - margin.left;
        const sPx = xScale(Math.min(altimetrySelection.start, altimetrySelection.end));
        const ePx = xScale(Math.max(altimetrySelection.start, altimetrySelection.end));
        const ds = Math.abs(xLocal - sPx);
        const de = Math.abs(xLocal - ePx);
        const thr = 16;
        if (ds > thr && de > thr) return null;
        return ds <= de ? 'start' : 'end';
    }

    function getHoveredSegmentInfo(distanceKm) {
        let best = null;
        let bestSegment = null;
        let bestDelta = Number.POSITIVE_INFINITY;

        (currentEfforts || []).forEach((segment, idx) => {
            const distArr = Array.isArray(segment.distance) ? segment.distance : [];
            if (!distArr.length) return;

            const segStart = Number(distArr[0]);
            const segEnd = Number(distArr[distArr.length - 1]);
            const s = Math.min(segStart, segEnd);
            const e = Math.max(segStart, segEnd);
            if (distanceKm < s || distanceKm > e) return;

            const selected = findSelectedSegment(segment);
            if (!selected) return;

            const isSprint = selected.type === 'sprint';
            const shouldShow = isSprint ? showSprints : showEfforts;
            if (!shouldShow) return;

            const center = (s + e) * 0.5;
            const delta = Math.abs(distanceKm - center);
            if (delta < bestDelta) {
                bestDelta = delta;
                best = selected;
                bestSegment = segment;
            }
        });

        if (!best) return null;
        const label = best.type === 'sprint'
            ? `S#${best.data.rank}`
            : `E#${best.data.id + 1}`;
        const color = bestSegment?.color || '#60a5fa';
        return { label, color };
    }

    function drawSelectionVisual() {
        if (altimetrySelection.start == null || altimetrySelection.end == null) {
            selRect.style('display', 'none');
            return;
        }
        const s = Math.min(altimetrySelection.start, altimetrySelection.end);
        const e = Math.max(altimetrySelection.start, altimetrySelection.end);
        const sx = xScale(s);
        const ex = xScale(e);
        const w = Math.max(0, ex - sx);
        if (w <= 0.5) {
            selRect.style('display', 'none');
            return;
        }
        selRect
            .style('display', null)
            .attr('x', sx)
            .attr('width', w);
    }

    function commitSelectionOrRestore(dragEdgeAtRelease) {
        const span = Math.abs((altimetrySelection.end ?? 0) - (altimetrySelection.start ?? 0));
        if (span > 0.5) {
            const start = Math.min(altimetrySelection.start, altimetrySelection.end);
            const end = Math.max(altimetrySelection.start, altimetrySelection.end);
            const { startIdx, endIdx } = getDistanceRangeIndices(start, end);
            currentSelectionRange = { startDist: start, endDist: end, startIdx, endIdx };
            currentSelectionMetrics = calculateSelectionMetrics();
            updateSelectionStreamButton();
            showSelectionMetricsCard();
            drawSelectionVisual();
            filterTraceByDistance(start, end);
            return;
        }

        if (dragEdgeAtRelease && altimetrySelectionBeforeDrag) {
            altimetrySelection.start = altimetrySelectionBeforeDrag.start;
            altimetrySelection.end = altimetrySelectionBeforeDrag.end;
            drawSelectionVisual();
            const start = Math.min(altimetrySelection.start, altimetrySelection.end);
            const end = Math.max(altimetrySelection.start, altimetrySelection.end);
            const { startIdx, endIdx } = getDistanceRangeIndices(start, end);
            currentSelectionRange = { startDist: start, endDist: end, startIdx, endIdx };
            currentSelectionMetrics = calculateSelectionMetrics();
            updateSelectionStreamButton();
            showSelectionMetricsCard();
            filterTraceByDistance(start, end);
            return;
        }

        altimetrySelection = { start: null, end: null };
        drawSelectionVisual();
        if (map.getSource('traccia-selected-zones')) {
            map.getSource('traccia-selected-zones').setData(emptyFeatureCollection);
        }
        currentSelectionRange = null;
        updateSelectionStreamButton();
    }

    const dragOverlay = root.append('rect')
        .attr('x', 0)
        .attr('y', 0)
        .attr('width', innerW)
        .attr('height', innerH)
        .attr('fill', 'transparent')
        .style('cursor', 'crosshair');

    const handleMouseMove = (ev) => {
        const point = getDistanceAtPixel(ev.clientX);
        const idx = findNearestDistanceIndex(point.distanceKm);

        if (isAltimetrySelecting) {
            if (altimetryDragEdge === 'start') altimetrySelection.start = point.distanceKm;
            else altimetrySelection.end = point.distanceKm;

            drawSelectionVisual();
            const now = Date.now();
            if (now - lastAltimetryUpdate > 30) {
                lastAltimetryUpdate = now;
                const start = Math.min(altimetrySelection.start, altimetrySelection.end);
                const end = Math.max(altimetrySelection.start, altimetrySelection.end);
                const { startIdx, endIdx } = getDistanceRangeIndices(start, end);
                
                // Update selection range and metrics in real-time during drag
                currentSelectionRange = { startDist: start, endDist: end, startIdx, endIdx };
                currentSelectionMetrics = calculateSelectionMetrics();
                showSelectionMetricsCard();
                
                if (map.getSource('traccia-selected-zones')) {
                    map.getSource('traccia-selected-zones').setData(buildZoneColoredSelectionGeoJSON(startIdx, endIdx));
                }
            }
            return;
        }

        const edge = detectSelectionEdgeAtPixel(ev.clientX);
        dragOverlay.style('cursor', edge ? 'ew-resize' : 'crosshair');

        if (idx >= 0) {
            hoverLine.style('display', null).attr('x1', xScale(elevationData.distance[idx])).attr('x2', xScale(elevationData.distance[idx]));
            hoverTipEl.style.display = 'block';
            const segInfo = getHoveredSegmentInfo(point.distanceKm);
            const time = elevationTimes && elevationTimes[idx] ? elevationTimes[idx] : '—';
            const distText = `${elevationData.distance[idx].toFixed(2)} km · ${Math.round(elevationData.altitude[idx])} m · ${time}`;
            hoverTipEl.style.color = '#cbd5e1';
            if (segInfo) {
                hoverTipEl.innerHTML = `<span style="color: ${segInfo.color}">${segInfo.label}</span> · ${distText}`;
            } else {
                hoverTipEl.textContent = distText;
            }

            const tipW = Math.ceil(hoverTipEl.getBoundingClientRect().width || 120);
            const chartW = Math.ceil(container.getBoundingClientRect().width || width);
            const rawLeft = margin.left + point.xClamped + 10;
            const clampedLeft = Math.max(6, Math.min(chartW - tipW - 6, rawLeft));
            hoverTipEl.style.left = `${clampedLeft}px`;
            hoverTipEl.style.top = `${margin.top + 4}px`;
            updateAltimetryMarkerByDistance(point.distanceKm);
        }
    };

    const handleMouseDown = (ev) => {
        const point = getDistanceAtPixel(ev.clientX);
        const edge = detectSelectionEdgeAtPixel(ev.clientX);
        isAltimetrySelecting = true;
        altimetryDragEdge = edge || 'end';
        altimetrySelectionBeforeDrag = edge ? { start: altimetrySelection.start, end: altimetrySelection.end } : null;

        if (edge === 'start') altimetrySelection.start = point.distanceKm;
        else if (edge === 'end') altimetrySelection.end = point.distanceKm;
        else {
            altimetrySelection.start = point.distanceKm;
            altimetrySelection.end = point.distanceKm;
        }
        clearAltimetryMarker();
        drawSelectionVisual();
    };

    const handleMouseLeave = () => {
        if (isAltimetrySelecting) return;
        hoverLine.style('display', 'none');
        hoverTipEl.style.display = 'none';
        clearAltimetryMarker();
    };

    const handleMouseUp = (ev) => {
        if (!isAltimetrySelecting) return;
        const point = getDistanceAtPixel(ev.clientX);
        if (altimetryDragEdge === 'start') altimetrySelection.start = point.distanceKm;
        else altimetrySelection.end = point.distanceKm;

        isAltimetrySelecting = false;
        const dragEdgeAtRelease = altimetryDragEdge;
        altimetryDragEdge = null;
        altimetrySelectionBeforeDrag = altimetrySelectionBeforeDrag || null;
        commitSelectionOrRestore(dragEdgeAtRelease);
        altimetrySelectionBeforeDrag = null;
    };

    const handleDoubleClick = () => resetTraceFilter();

    dragOverlay.on('mousemove', handleMouseMove)
        .on('mousedown', handleMouseDown)
        .on('mouseleave', handleMouseLeave)
        .on('dblclick', handleDoubleClick);

    const onDocMouseUp = (ev) => handleMouseUp(ev);
    document.addEventListener('mouseup', onDocMouseUp);

    drawSelectionVisual();
    d3AltimetryState = {
        root,
        xScale,
        drawSelectionVisual,
        cleanup: () => {
            document.removeEventListener('mouseup', onDocMouseUp);
        }
    };

    applyChartVisibilityFilters();
}

function filterTraceByDistance(startDist, endDist) {
    if (!map || !originalTracceGeoJSON || !originalTracceGeoJSON.features[0]) return;
    
    const originalCoords = originalTracceGeoJSON.features[0].geometry.coordinates;
    const { startIdx, endIdx } = getDistanceRangeIndices(startDist, endDist);
    
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

    // Overlay selected section with zone colors based on 5s power.
    if (map.getSource('traccia-selected-zones')) {
        map.getSource('traccia-selected-zones').setData(
            buildZoneColoredSelectionGeoJSON(startIdx, endIdx)
        );
    }
    
    // Hide/show effort markers: show only if the segment START is inside selected range
    effortMarkers.forEach(({ marker, startDist: effortStart }) => {
        const startsInsideSelection = Number(effortStart) >= Number(startDist) && Number(effortStart) <= Number(endDist);
        const markerElement = marker.getElement();
        markerElement.style.display = startsInsideSelection ? 'flex' : 'none';
    });

    applyChartVisibilityFilters();
    
    // Fit view to filtered segment
    const bounds = filteredCoords.reduce((bounds, coord) => {
        return bounds.extend(coord);
    }, new maplibregl.LngLatBounds(filteredCoords[0], filteredCoords[0]));
    
    map.fitBounds(bounds, { padding: 50, duration: 600 });
}

function resetTraceFilter() {
    if (!map) return;
    
    // Clean up marker
    clearAltimetryMarker();
    
    // Restore original trace
    if (map.getSource('traccia')) {
        map.getSource('traccia').setData(originalTracceGeoJSON);
    }

    if (map.getSource('traccia-selected-zones')) {
        map.getSource('traccia-selected-zones').setData(emptyFeatureCollection);
    }
    
    // Show all effort markers again
    effortMarkers.forEach(({ marker }) => {
        const markerElement = marker.getElement();
        markerElement.style.display = 'flex';
    });
    
    // Reset selection
    altimetrySelection = { start: null, end: null };
    isAltimetrySelecting = false;
    altimetryDragEdge = null;
    activeSelectionType = null;
    currentSelectionRange = null;
    currentSelectionMetrics = null;
    isShowingEffortDetail = false;
    setSelectionZonesDimmed(false);
    updateSelectionStreamButton();
    showFullRideMetricsCard();
    applyChartVisibilityFilters();
    
    // Clear selection highlights from chart
    if (d3AltimetryState && d3AltimetryState.drawSelectionVisual) {
        d3AltimetryState.drawSelectionVisual();
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
    if (!d3AltimetryState || !d3AltimetryState.root) return;

    d3AltimetryState.root.selectAll('.effort-segment').each(function(d) {
        const segment = elevationData.efforts[d.idx];
        const isSprint = segment && segment.type === 'sprint';
        const shouldShow = isSprint ? showSprints : showEfforts;
        const selected = d.idx === idx;
        d3.select(this)
            .style('display', shouldShow ? null : 'none')
            .attr('stroke-width', selected ? 4 : 2)
            .attr('stroke-opacity', selected ? 1 : 0.6);
    });
}

function resetChartHighlight() {
    if (!d3AltimetryState || !d3AltimetryState.root) return;

    d3AltimetryState.root.selectAll('.effort-segment').each(function(d) {
        const segment = elevationData.efforts[d.idx];
        const isSprint = segment && segment.type === 'sprint';
        const shouldShow = isSprint ? showSprints : showEfforts;
        d3.select(this)
            .style('display', shouldShow ? null : 'none')
            .attr('stroke-width', shouldShow ? 3 : 0)
            .attr('stroke-opacity', shouldShow ? 1 : 0);
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
    
    drawFullElevationChart();
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
    if (!map.getLayer('traccia-line-casing')) {
        map.addLayer({
            'id': 'traccia-line-casing',
            'type': 'line',
            'source': 'traccia',
            'paint': {
                'line-color': 'rgba(15, 23, 42, 0.95)',
                'line-width': 10,
                'line-opacity': 0.9
            }
        });
    }
    if (!map.getLayer('traccia-line')) {
        map.addLayer({
            'id': 'traccia-line',
            'type': 'line',
            'source': 'traccia',
            'paint': {
                'line-color': '#ffd54a',
                'line-width': 5,
                'line-opacity': 0.98
            }
        });
    }
    if (!map.getLayer('traccia-line-glow')) {
        map.addLayer({
            'id': 'traccia-line-glow',
            'type': 'line',
            'source': 'traccia',
            'paint': {
                'line-color': '#fff2a8',
                'line-width': 8,
                'line-opacity': 0.3,
                'line-blur': 1.2
            }
        });
    }

    if (!map.getSource('traccia-selected-zones')) {
        map.addSource('traccia-selected-zones', {
            'type': 'geojson',
            'data': emptyFeatureCollection
        });
    }

    if (!map.getLayer('traccia-selected-zones-line')) {
        map.addLayer({
            'id': 'traccia-selected-zones-line',
            'type': 'line',
            'source': 'traccia-selected-zones',
            'paint': {
                'line-color': ['get', 'color'],
                'line-width': 7,
                'line-opacity': 1
            }
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
        setSelectionZonesDimmed(activeSelectionType === 'effort' || activeSelectionType === 'sprint');
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
        // Check visibility based on resolved segment type
        const selected = findSelectedSegment(effort);
        const isSprint = selected ? selected.type === 'sprint' : effort.type === 'sprint';
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
        el.innerHTML = String(isSprint
            ? (selected?.data?.rank ?? (idx + 1))
            : ((selected?.data?.id ?? effort.id ?? idx) + 1));

        const popupTitle = isSprint
            ? `Sprint #${selected?.data?.rank ?? (idx + 1)}`
            : `Effort #${(selected?.data?.id ?? effort.id ?? idx) + 1}`;
        const popupPower = Number(selected?.data?.avg_power ?? effort.avg ?? 0);
        const popupCad = Number(selected?.data?.avg_cadence ?? effort.avg_cadence ?? 0);
        const popupDur = Number(selected?.data?.duration ?? effort.duration ?? 0);
        const popupSpeed = Number(selected?.data?.avg_speed ?? effort.avg_speed ?? 0);
        
        const marker = new maplibregl.Marker({ element: el })
            .setLngLat([coordStart[0], coordStart[1]])
            .setPopup(new maplibregl.Popup({ anchor: 'top', offset: [0, 15], maxWidth: 250 }).setHTML(`
                <div style="padding: 10px; font-size: 12px; color: #9ca3af; background: rgba(15,23,42,.95);">
                    <b style="color: #60a5fa;">${popupTitle}</b><br>
                    <div style="border-top: 1px solid rgba(255,255,255,.2); margin: 6px 0; padding-top: 6px;">
                        <div><b>⚡ ${popupPower.toFixed(0)} W</b> | 🌀 ${popupCad.toFixed(0)} rpm</div>
                        <div>⏱️ ${popupDur}s | 🚴‍♂️ ${popupSpeed.toFixed(1)} km/h</div>
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

    applyChartVisibilityFilters();
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

let streamModalData = null;
let avg30sSeconds = 30;
let avg60sSeconds = 60;

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

const storedAvg30s = localStorage.getItem('stream_avg30s');
const storedAvg60s = localStorage.getItem('stream_avg60s');
if (storedAvg30s) avg30sSeconds = parseInt(storedAvg30s, 10);
if (storedAvg60s) avg60sSeconds = parseInt(storedAvg60s, 10);

function getIntensityZones() {
    const stored = localStorage.getItem('inspection_zones');
    if (stored) {
        try {
            return JSON.parse(stored);
        } catch (e) {
            console.log('Failed to parse stored zones');
        }
    }
    if (chartData.intensity_zones && chartData.intensity_zones.length > 0) {
        return chartData.intensity_zones;
    }
    return [
        { min: 0, max: 60, color: '#009e80', name: 'Z1' },
        { min: 60, max: 80, color: '#009e00', name: 'Z2' },
        { min: 80, max: 90, color: '#ffcb0e', name: 'Z3' },
        { min: 90, max: 105, color: '#ff7f0e', name: 'Z4' },
        { min: 105, max: 135, color: '#dd0447', name: 'Z5' },
        { min: 135, max: 300, color: '#6633cc', name: 'Z6' },
        { min: 300, max: 999, color: '#504861', name: 'Z7' },
    ];
}

function openStreamModal(elemId, dataId, type) {
    const data = type === 'effort'
        ? chartData.efforts.find((e) => e.id == dataId)
        : chartData.sprints.find((s) => s.id == dataId);

    if (!data) return;
    if (!data.time_stream || !data.power_stream) return;

    streamModalData = {
        data: data,
        type: type,
        label: type === 'effort' ? `E#${data.id + 1}` : `S#${data.rank}`,
        timeStream: data.time_stream,
        powerStream: data.power_stream,
        hrStream: data.hr_stream,
        wkgStream: data.wkg_stream,
        cadenceStream: data.cadence_stream || null,
        torqueStream: data.torque_stream || null,
        speedStream: data.speed_stream || null,
        effortStart: (data.stream_effort_start != null) ? data.stream_effort_start : 0,
        effortEnd: (data.stream_effort_end != null) ? data.stream_effort_end : data.time_stream[data.time_stream.length - 1],
        effortDuration: (data.stream_effort_end != null)
            ? Math.round(data.stream_effort_end - data.stream_effort_start)
            : (data.stream_effort_duration || 0),
    };

    const titleEl = document.getElementById('streamModalTitle');
    if (!titleEl) return;
    titleEl.textContent = `${streamModalData.label} - Duration: ${format_time_mmss(streamModalData.effortDuration)}s`;

    const modal = document.getElementById('streamModal');
    const modalOverlay = document.getElementById('streamModalOverlay');

    if (!modal || !modalOverlay) return;

    modal.classList.add('active');
    modalOverlay.classList.add('active');

    const ctrlPanel = document.getElementById('streamControlPanel');
    if (ctrlPanel) ctrlPanel.style.display = (type === 'sprint') ? 'none' : '';

    setTimeout(() => {
        buildStreamChartsD3();
    }, 50);
}

window.openStreamModal = openStreamModal;

function openSelectionStreamModal() {
    const prepared = buildSelectionStreamPayload();
    if (!prepared) return;

    streamModalData = prepared;

    const titleEl = document.getElementById('streamModalTitle');
    if (!titleEl) return;
    titleEl.textContent = `${streamModalData.label} - Duration: ${format_time_mmss(streamModalData.effortDuration)}s`;

    const modal = document.getElementById('streamModal');
    const modalOverlay = document.getElementById('streamModalOverlay');
    if (!modal || !modalOverlay) return;

    modal.classList.add('active');
    modalOverlay.classList.add('active');

    const ctrlPanel = document.getElementById('streamControlPanel');
    if (ctrlPanel) ctrlPanel.style.display = '';

    setTimeout(() => {
        buildStreamChartsD3();
    }, 50);
}

window.openSelectionStreamModal = openSelectionStreamModal;

function closeStreamModal() {
    const modal = document.getElementById('streamModal');
    const modalOverlay = document.getElementById('streamModalOverlay');
    modal.classList.remove('active');
    modalOverlay.classList.remove('active');

    document.getElementById('streamChart1').innerHTML = '';
    document.getElementById('streamChart2').innerHTML = '';
    document.getElementById('streamChart3').innerHTML = '';
    document.getElementById('streamUnifiedChart').innerHTML = '';

    streamModalData = null;
}

window.closeStreamModal = closeStreamModal;

function calculateTimeBasedMovingAverage(powerData, timeData, windowSeconds) {
    const result = [];
    for (let i = 0; i < timeData.length; i++) {
        const c = timeData[i];
        const lo = c - windowSeconds / 2;
        const hi = c + windowSeconds / 2;
        let sum = 0;
        let cnt = 0;
        for (let j = 0; j < timeData.length; j++) {
            if (timeData[j] >= lo && timeData[j] <= hi) {
                sum += powerData[j];
                cnt++;
            }
        }
        result.push(cnt ? sum / cnt : powerData[i]);
    }
    return result;
}

function buildStreamChartsD3() {
    if (!streamModalData) return;

    if (streamModalData.type === 'sprint') {
        buildSprintStreamCharts();
        return;
    }

    const cp = chartData.cp;
    const zones = getIntensityZones();
    const timeS = streamModalData.timeStream;
    const powS = streamModalData.powerStream;
    const hrS = streamModalData.hrStream || null;
    const avg30 = calculateTimeBasedMovingAverage(powS, timeS, avg30sSeconds);
    const avg60 = calculateTimeBasedMovingAverage(powS, timeS, avg60sSeconds);

    const container = document.getElementById('streamUnifiedChart');
    if (!container) return;
    container.innerHTML = '';
    container.style.position = 'relative';

    const W = container.offsetWidth || 900;
    const H = container.offsetHeight || 560;
    const ML = 60;
    const MR = 60;
    const MT = 10;
    const MB = 44;
    const GAP = 8;
    const innerW = W - ML - MR;
    const panelH = Math.floor((H - MT - MB - GAP * 4) / 3);
    const maxT = d3.max(timeS);
    const maxP = d3.max(powS) * 1.1;

    const effortStartTime = streamModalData.effortStart || 0;
    const effortEndTime = streamModalData.effortEnd || maxT;

    function zoneColor(w) {
        const pct = w / cp * 100;
        for (const z of zones) if (pct >= z.min && (z.max === 999 || pct < z.max)) return z.color;
        return '#6b7280';
    }

    const panelDefs = [
        { title: 'Raw Power', vals: powS, showHR: true },
        { title: `Avg ${avg30sSeconds}s`, vals: avg30, showHR: false },
        { title: `Avg ${avg60sSeconds}s`, vals: avg60, showHR: false },
    ];

    let curDomain = [effortStartTime, effortEndTime];

    const svg = d3.select(container).append('svg')
        .attr('width', W).attr('height', H)
        .style('font-family', '-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif');

    svg.append('defs').append('clipPath').attr('id', 'sc-clip3')
        .append('rect').attr('width', innerW + 2).attr('height', panelH + 4).attr('x', -1).attr('y', -2);

    const root = svg.append('g').attr('transform', `translate(${ML},${MT})`);

    let hrYS = null;
    if (hrS) {
        const valid = hrS.filter((h) => h && h > 0);
        if (valid.length) hrYS = d3.scaleLinear().domain([d3.min(valid) * 0.95, d3.max(valid) * 1.05]).range([panelH, 0]);
    }

    const dataGroups = [];
    const crossVLines = [];
    const crossDots = [];
    const yScales = [];
    const pg_refs = [];

    panelDefs.forEach((panel, pi) => {
        const ty = (panelH + GAP) * pi;
        const pg = root.append('g').attr('transform', `translate(0,${ty})`);
        pg_refs.push(pg);
        const panelMax = d3.max(panel.vals) * 1.1;
        const yS = d3.scaleLinear().domain([0, panelMax]).range([panelH, 0]);
        panel._yS = yS;
        yScales.push(yS);

        pg.append('rect').attr('width', innerW).attr('height', panelH)
            .attr('fill', '#ffffff').attr('rx', 3)
            .attr('stroke', '#e5e7eb').attr('stroke-width', 0.5);

        const yAx = pg.append('g').attr('class', 'y-ax-panel');
        function redrawYAx(ys) {
            yAx.call(d3.axisLeft(ys).ticks(4).tickFormat((d) => d).tickSize(0));
            yAx.select('.domain').attr('stroke', '#d1d5db');
            yAx.selectAll('text').attr('fill', '#6b7280').attr('font-size', 9).attr('x', -4);
        }
        redrawYAx(yS);
        panel._redrawYAx = redrawYAx;
        pg.append('text').attr('transform', 'rotate(-90)').attr('x', -panelH / 2).attr('y', -46)
            .attr('text-anchor', 'middle').attr('fill', '#9ca3af').attr('font-size', 9).text('W');

        if (pi === 0 && hrYS) {
            const hrAx = pg.append('g').attr('transform', `translate(${innerW},0)`)
                .call(d3.axisRight(hrYS).ticks(4).tickFormat((d) => d).tickSize(0));
            hrAx.select('.domain').attr('stroke', '#fecaca');
            hrAx.selectAll('text').attr('fill', '#ef4444').attr('font-size', 9).attr('x', 4);
            pg.append('text').attr('transform', 'rotate(90)')
                .attr('x', panelH / 2).attr('y', -innerW - 46)
                .attr('text-anchor', 'middle').attr('fill', '#ef4444').attr('font-size', 9).text('bpm');
        }

        pg.append('line').attr('class', 'cp-line').attr('x1', 0).attr('x2', innerW)
            .attr('y1', yS(cp)).attr('y2', yS(cp))
            .attr('stroke', '#f59e0b').attr('stroke-width', 1)
            .attr('stroke-dasharray', '5,3').attr('opacity', 0.9);
        pg.append('text').attr('class', 'cp-label').attr('x', innerW - 3).attr('y', yS(cp) - 3)
            .attr('text-anchor', 'end').attr('fill', '#f59e0b').attr('font-size', 8.5)
            .text(`CP ${cp}W`);

        pg.append('text').attr('x', 6).attr('y', 13)
            .attr('fill', '#374151').attr('font-size', 10).attr('font-weight', 600)
            .text(panel.title);

        const dg = pg.append('g').attr('clip-path', 'url(#sc-clip3)');
        dataGroups.push({ dg, panel, yS, pi });

        const cv = pg.append('line').attr('y1', 0).attr('y2', panelH)
            .attr('stroke', '#374151').attr('stroke-width', 1)
            .attr('stroke-dasharray', '4,2').style('display', 'none').style('pointer-events', 'none');
        crossVLines.push(cv);
        const cd = pg.append('circle').attr('r', 3.5)
            .attr('fill', 'white').attr('stroke', '#374151').attr('stroke-width', 1.5)
            .style('display', 'none').style('pointer-events', 'none');
        crossDots.push(cd);
    });

    function drawAll(domain) {
        const xS = d3.scaleLinear().domain(domain).range([0, innerW]);

        dataGroups.forEach(({ dg, panel, yS, pi }) => {
            dg.selectAll('*').remove();
            const pts = timeS.map((t, i) => ({ t, p: panel.vals[i] }))
                .filter((d) => d.t >= domain[0] && d.t <= domain[1]);
            if (pts.length < 2) return;

            const visMax = d3.max(pts, (d) => d.p) * 1.1;
            yS.domain([0, visMax]);
            if (panel._redrawYAx) panel._redrawYAx(yS);
            const pg = pg_refs[pi];

            pg.select('line.cp-line').attr('y1', yS(cp)).attr('y2', yS(cp));
            pg.select('text.cp-label').attr('y', yS(cp) - 3);

            const svgDefs = d3.select(dg.node().closest('svg')).select('defs');

            const fullAreaPath = d3.area()
                .x((d) => xS(d.t)).y0(panelH).y1((d) => yS(d.p)).curve(d3.curveMonotoneX)(pts);

            const curveClipId = `curve-clip-${pi}-${Math.round(domain[0] * 100)}`;
            svgDefs.selectAll(`#${curveClipId}`).remove();
            const curveClip = svgDefs.append('clipPath').attr('id', curveClipId);
            curveClip.append('path').attr('d', fullAreaPath);

            zones.forEach((z) => {
                const minW = (z.min / 100) * cp;
                const maxW = z.max === 999 ? maxP * 1.5 : (z.max / 100) * cp;
                dg.append('rect')
                    .attr('x', 0).attr('width', innerW)
                    .attr('y', yS(maxW))
                    .attr('height', Math.max(0, yS(minW) - yS(maxW)))
                    .attr('fill', z.color)
                    .attr('opacity', 0.82)
                    .attr('clip-path', `url(#${curveClipId})`);
            });

            dg.append('path').datum(pts)
                .attr('fill', 'white')
                .attr('d', d3.area().x((d) => xS(d.t)).y0(-2).y1((d) => yS(d.p)).curve(d3.curveMonotoneX));

            d3.range(0, visMax + 100, 100).forEach((w) => {
                const yy = yS(w);
                if (yy < 0 || yy > panelH) return;
                dg.append('line')
                    .attr('x1', 0).attr('x2', innerW)
                    .attr('y1', yy).attr('y2', yy)
                    .attr('stroke', '#94a3b8').attr('stroke-width', 0.5).attr('opacity', 0.35);
            });

            const minStep = Math.ceil(domain[0] / 60) * 60;
            for (let t60 = minStep; t60 <= domain[1]; t60 += 60) {
                dg.append('line')
                    .attr('x1', xS(t60)).attr('x2', xS(t60))
                    .attr('y1', 0).attr('y2', panelH)
                    .attr('stroke', '#94a3b8').attr('stroke-width', 0.5).attr('opacity', 0.35);
            }

            const segG = dg.append('g');
            for (let i = 0; i < pts.length - 1; i++) {
                const d0 = pts[i];
                const d1 = pts[i + 1];
                segG.append('line')
                    .attr('x1', xS(d0.t)).attr('y1', yS(d0.p))
                    .attr('x2', xS(d1.t)).attr('y2', yS(d1.p))
                    .attr('stroke', zoneColor((d0.p + d1.p) / 2))
                    .attr('stroke-width', 0)
                    .attr('stroke-linecap', 'round');
            }

            if (pi === 0 && hrS && hrYS) {
                const hrPts = timeS.map((t, i) => ({ t, h: hrS[i] }))
                    .filter((d) => d.t >= domain[0] && d.t <= domain[1] && d.h > 0);
                if (hrPts.length > 1) {
                    dg.append('path').datum(hrPts)
                        .attr('fill', 'none').attr('stroke', '#1e3a5f').attr('stroke-width', 2.2)
                        .attr('opacity', 1)
                        .attr('d', d3.line().x((d) => xS(d.t)).y((d) => hrYS(d.h)).curve(d3.curveMonotoneX));
                    dg.append('path').datum(hrPts)
                        .attr('fill', 'none').attr('stroke', '#60a5fa').attr('stroke-width', 1.2)
                        .attr('opacity', 1)
                        .attr('d', d3.line().x((d) => xS(d.t)).y((d) => hrYS(d.h)).curve(d3.curveMonotoneX));
                }
            }
        });
    }
    drawAll(curDomain);

    const xAxG = root.append('g').attr('transform', `translate(0,${(panelH + GAP) * 3 - GAP})`);
    function updateXAxis(dom) {
        xAxG.call(d3.axisBottom(d3.scaleLinear().domain(dom).range([0, innerW])).ticks(8)
            .tickFormat((d) => {
                const m = Math.floor(d / 60);
                const s = Math.round(d % 60);
                return m > 0 ? `${m}m${s}s` : `${Math.round(d)}s`;
            })
            .tickSize(0));
        xAxG.select('.domain').attr('stroke', '#d1d5db');
        xAxG.selectAll('text').attr('fill', '#6b7280').attr('font-size', 9);
    }
    updateXAxis(curDomain);

    const ttEl = document.createElement('div');
    ttEl.style.cssText = 'position:absolute;pointer-events:none;display:none;z-index:999;'
        + 'background:rgba(17,24,39,0.95);color:#fff;border-radius:6px;padding:8px 12px;'
        + 'font-size:11px;line-height:1.7;white-space:nowrap;box-shadow:0 4px 16px rgba(0,0,0,0.35);';
    container.appendChild(ttEl);

    function updateEffortPointer(mx) {
        const xS = d3.scaleLinear().domain(curDomain).range([0, innerW]);
        const t = xS.invert(Math.max(0, Math.min(innerW, mx)));
        let ci = 0;
        let md = Infinity;
        timeS.forEach((ts, i) => {
            const d = Math.abs(ts - t);
            if (d < md) {
                md = d;
                ci = i;
            }
        });

        panelDefs.forEach((_, pi) => {
            const yv = yScales[pi](panelDefs[pi].vals[ci] ?? 0);
            crossVLines[pi].style('display', null).attr('x1', mx).attr('x2', mx);
            crossDots[pi].style('display', null).attr('cx', mx).attr('cy', yv);
        });

        const ts = timeS[ci];
        const m = Math.floor(ts / 60);
        const s = Math.round(ts % 60);
        const tStr = m > 0 ? `${m}m${s}s` : `${Math.round(ts)}s`;
        let html = `<span style="color:#f9fafb;font-weight:700">${tStr}</span><br/>`;
        html += `<span style="color:#fbbf24">⚡ ${Math.round(powS[ci])}W</span>`;
        html += ` <span style="color:#a78bfa"> ∅${avg30sSeconds}s ${Math.round(avg30[ci])}W</span>`;
        html += ` <span style="color:#6ee7b7"> ∅${avg60sSeconds}s ${Math.round(avg60[ci])}W</span>`;
        if (hrS && hrS[ci] > 0) html += `<br/><span style="color:#fca5a5">❤️ ${Math.round(hrS[ci])} bpm</span>`;
        ttEl.innerHTML = html;
        ttEl.style.display = 'block';

        const isTouchE = window.matchMedia('(pointer: coarse)').matches;
        if (isTouchE) {
            ttEl.style.left = '50%';
            ttEl.style.transform = 'translateX(-50%)';
            ttEl.style.top = '4px';
        } else {
            ttEl.style.transform = '';
            let lx = ML + mx + 14;
            if (lx + 240 > W - MR) lx = ML + mx - 250;
            ttEl.style.left = `${lx}px`;
            ttEl.style.top = `${Math.max(4, MT + 20)}px`;
        }
    }

    const totalPH = (panelH + GAP) * 3 - GAP;
    const effortOverlay = root.append('rect').attr('width', innerW).attr('height', totalPH)
        .attr('fill', 'transparent').style('cursor', 'crosshair')
        .on('mousemove', function(ev) {
            const [mx] = d3.pointer(ev);
            updateEffortPointer(mx);
        })
        .on('mouseleave', function() {
            if (!window.matchMedia('(pointer: coarse)').matches) {
                crossVLines.forEach((c) => c.style('display', 'none'));
                crossDots.forEach((c) => c.style('display', 'none'));
                ttEl.style.display = 'none';
            }
        });

    effortOverlay.node().addEventListener('touchstart', function(ev) {
        ev.preventDefault();
        const r = container.getBoundingClientRect();
        const mx = ev.touches[0].clientX - r.left - ML;
        updateEffortPointer(mx);
    }, { passive: false });
    effortOverlay.node().addEventListener('touchmove', function(ev) {
        ev.preventDefault();
        const r = container.getBoundingClientRect();
        const mx = ev.touches[0].clientX - r.left - ML;
        updateEffortPointer(mx);
    }, { passive: false });
    effortOverlay.node().addEventListener('touchend', function(ev) {
        ev.preventDefault();
        crossVLines.forEach((c) => c.style('display', 'none'));
        crossDots.forEach((c) => c.style('display', 'none'));
        ttEl.style.display = 'none';
    }, { passive: false });

    if (!window.matchMedia('(pointer: coarse)').matches) {
        requestAnimationFrame(() => {
            const midTime = (effortStartTime + effortEndTime) / 2;
            const xS0 = d3.scaleLinear().domain(curDomain).range([0, innerW]);
            updateEffortPointer(xS0(midTime));
        });
    }
}

function buildSprintStreamCharts() {
    const timeS = streamModalData.timeStream;
    const powS = streamModalData.powerStream;
    const cadS = streamModalData.cadenceStream;
    const torS = streamModalData.torqueStream;

    const container = document.getElementById('streamUnifiedChart');
    if (!container) return;
    container.innerHTML = '';
    container.style.position = 'relative';

    const W = container.offsetWidth || 900;
    const H = container.offsetHeight || 560;
    const ML = 64;
    const MR = 64;
    const MT = 14;
    const MB = 48;
    const GAP = 14;
    const innerW = W - ML - MR;
    const panelH = Math.floor((H - MT - MB - GAP * 3) / 2);
    const maxT = d3.max(timeS);
    const maxP = d3.max(powS) * 1.12;

    const spdS = streamModalData.speedStream;
    const validCad = cadS ? cadS.filter((v) => v && v > 0) : [];
    const validTor = torS ? torS.filter((v) => v && v > 0) : [];
    const maxCad = validCad.length ? d3.max(validCad) * 1.1 : 200;
    const maxTor = validTor.length ? d3.max(validTor) * 1.1 : 50;
    const minCad = validCad.length ? d3.min(validCad) * 0.92 : 0;
    const minTor = validTor.length ? d3.min(validTor) * 0.92 : 0;

    const effortStartTime = streamModalData.effortStart || 0;
    const effortEndTime = streamModalData.effortEnd || maxT;
    const curDomain = [effortStartTime, effortEndTime];

    const svg = d3.select(container).append('svg')
        .attr('width', W).attr('height', H)
        .style('font-family', '-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif');

    const defs = svg.append('defs');
    const powGrad = defs.append('linearGradient').attr('id', 'sp-pow-grad')
        .attr('x1', 0).attr('y1', 0).attr('x2', 0).attr('y2', 1);
    powGrad.append('stop').attr('offset', '0%').attr('stop-color', '#3b82f6').attr('stop-opacity', 0.35);
    powGrad.append('stop').attr('offset', '100%').attr('stop-color', '#3b82f6').attr('stop-opacity', 0.02);

    const cadGrad = defs.append('linearGradient').attr('id', 'sp-cad-grad')
        .attr('x1', 0).attr('y1', 0).attr('x2', 0).attr('y2', 1);
    cadGrad.append('stop').attr('offset', '0%').attr('stop-color', '#10b981').attr('stop-opacity', 0.25);
    cadGrad.append('stop').attr('offset', '100%').attr('stop-color', '#10b981').attr('stop-opacity', 0.02);

    defs.append('clipPath').attr('id', 'sp-clip2')
        .append('rect').attr('width', innerW + 2).attr('height', panelH + 4).attr('x', -1).attr('y', -2);

    const root = svg.append('g').attr('transform', `translate(${ML},${MT})`);
    const yPow = d3.scaleLinear().domain([0, maxP]).range([panelH, 0]);
    const yCad = d3.scaleLinear().domain([minCad, maxCad]).range([panelH, 0]);
    const yTor = validTor.length ? d3.scaleLinear().domain([minTor, maxTor]).range([panelH, 0]) : null;

    const pg0 = root.append('g');
    pg0.append('rect').attr('width', innerW).attr('height', panelH)
        .attr('rx', 6).attr('fill', '#1e3a5f').attr('opacity', 0.04).attr('transform', 'translate(2,2)');
    pg0.append('rect').attr('width', innerW).attr('height', panelH)
        .attr('rx', 6).attr('fill', '#f8faff').attr('stroke', '#e2e8f0').attr('stroke-width', 1);

    yPow.ticks(5).forEach((t) => {
        pg0.append('line').attr('x1', 0).attr('x2', innerW)
            .attr('y1', yPow(t)).attr('y2', yPow(t))
            .attr('stroke', '#e2e8f0').attr('stroke-width', 0.8);
    });

    const yAx0 = pg0.append('g').call(d3.axisLeft(yPow).ticks(5).tickFormat((d) => d).tickSize(0));
    yAx0.select('.domain').attr('stroke', '#cbd5e1');
    yAx0.selectAll('text').attr('fill', '#64748b').attr('font-size', 9).attr('x', -5);
    pg0.append('text').attr('transform', 'rotate(-90)').attr('x', -panelH / 2).attr('y', -50)
        .attr('text-anchor', 'middle').attr('fill', '#3b82f6').attr('font-size', 10).attr('font-weight', 600).text('W');

    pg0.append('rect').attr('x', 8).attr('y', 6).attr('width', 68).attr('height', 18)
        .attr('rx', 4).attr('fill', '#3b82f6').attr('opacity', 0.12);
    pg0.append('text').attr('x', 42).attr('y', 19).attr('text-anchor', 'middle')
        .attr('fill', '#1d4ed8').attr('font-size', 10).attr('font-weight', 700).text('Power (W)');

    const dg0 = pg0.append('g').attr('clip-path', 'url(#sp-clip2)');
    const cv0 = pg0.append('line').attr('y1', 0).attr('y2', panelH)
        .attr('stroke', '#94a3b8').attr('stroke-width', 1).attr('stroke-dasharray', '4,2').style('display', 'none');
    const cd0 = pg0.append('circle').attr('r', 4)
        .attr('fill', '#3b82f6').attr('stroke', 'white').attr('stroke-width', 2).style('display', 'none');
    const cd0spd = pg0.append('circle').attr('r', 4)
        .attr('fill', '#a855f7').attr('stroke', 'white').attr('stroke-width', 2).style('display', 'none');

    const ty1 = panelH + GAP;
    const pg1 = root.append('g').attr('transform', `translate(0,${ty1})`);
    pg1.append('rect').attr('width', innerW).attr('height', panelH)
        .attr('rx', 6).attr('fill', '#f8faff').attr('stroke', '#e2e8f0').attr('stroke-width', 1).attr('opacity', 0.04)
        .attr('transform', 'translate(2,2)');
    pg1.append('rect').attr('width', innerW).attr('height', panelH)
        .attr('rx', 6).attr('fill', '#f8faff').attr('stroke', '#e2e8f0').attr('stroke-width', 1);

    yCad.ticks(5).forEach((t) => {
        pg1.append('line').attr('x1', 0).attr('x2', innerW)
            .attr('y1', yCad(t)).attr('y2', yCad(t))
            .attr('stroke', '#e2e8f0').attr('stroke-width', 0.8);
    });

    const yAx1L = pg1.append('g').call(d3.axisLeft(yCad).ticks(5).tickFormat((d) => d).tickSize(0));
    yAx1L.select('.domain').attr('stroke', '#cbd5e1');
    yAx1L.selectAll('text').attr('fill', '#10b981').attr('font-size', 9).attr('x', -5);
    pg1.append('text').attr('transform', 'rotate(-90)').attr('x', -panelH / 2).attr('y', -50)
        .attr('text-anchor', 'middle').attr('fill', '#10b981').attr('font-size', 10).attr('font-weight', 600).text('rpm');

    if (yTor) {
        const yAx1R = pg1.append('g').attr('transform', `translate(${innerW},0)`)
            .call(d3.axisRight(yTor).ticks(5).tickFormat((d) => d).tickSize(0));
        yAx1R.select('.domain').attr('stroke', '#cbd5e1');
        yAx1R.selectAll('text').attr('fill', '#f59e0b').attr('font-size', 9).attr('x', 5);
        pg1.append('text').attr('transform', 'rotate(90)').attr('x', panelH / 2).attr('y', -innerW - 50)
            .attr('text-anchor', 'middle').attr('fill', '#f59e0b').attr('font-size', 10).attr('font-weight', 600).text('Nm');
    }

    const validSpd = spdS ? spdS.filter((v) => v > 0) : [];
    const maxSpd = validSpd.length ? d3.max(validSpd) * 1.1 : 60;
    const minSpd = validSpd.length ? d3.min(validSpd) * 0.92 : 0;
    const ySpd = validSpd.length ? d3.scaleLinear().domain([minSpd, maxSpd]).range([panelH, 0]) : null;
    if (ySpd) {
        const yAx0R = pg0.append('g').attr('transform', `translate(${innerW},0)`)
            .call(d3.axisRight(ySpd).ticks(5).tickFormat((d) => d).tickSize(0));
        yAx0R.select('.domain').attr('stroke', '#cbd5e1');
        yAx0R.selectAll('text').attr('fill', '#a855f7').attr('font-size', 9).attr('x', 5);
        pg0.append('text').attr('transform', 'rotate(90)').attr('x', panelH / 2).attr('y', -innerW - 50)
            .attr('text-anchor', 'middle').attr('fill', '#a855f7').attr('font-size', 10).attr('font-weight', 600).text('km/h');
    }

    const badgeW = yTor ? 148 : 88;
    pg1.append('rect').attr('x', 8).attr('y', 6).attr('width', badgeW).attr('height', 18)
        .attr('rx', 4).attr('fill', '#10b981').attr('opacity', 0.12);
    pg1.append('text').attr('x', 8 + badgeW / 2).attr('y', 19).attr('text-anchor', 'middle')
        .attr('fill', '#059669').attr('font-size', 10).attr('font-weight', 700)
        .text(yTor ? 'Cadence (rpm)  ·  Torque (Nm)' : 'Cadence (rpm)');

    const dg1 = pg1.append('g').attr('clip-path', 'url(#sp-clip2)');
    const cv1 = pg1.append('line').attr('y1', 0).attr('y2', panelH)
        .attr('stroke', '#94a3b8').attr('stroke-width', 1).attr('stroke-dasharray', '4,2').style('display', 'none');
    const cd1cad = pg1.append('circle').attr('r', 4)
        .attr('fill', '#10b981').attr('stroke', 'white').attr('stroke-width', 2).style('display', 'none');
    const cd1tor = yTor ? pg1.append('circle').attr('r', 4)
        .attr('fill', '#f59e0b').attr('stroke', 'white').attr('stroke-width', 2).style('display', 'none') : null;

    function drawAll(domain) {
        const xS = d3.scaleLinear().domain(domain).range([0, innerW]);

        dg0.selectAll('*').remove();
        const powPts = timeS.map((t, i) => ({ t, p: powS[i] })).filter((d) => d.t >= domain[0] && d.t <= domain[1]);
        if (powPts.length > 1) {
            dg0.append('path').datum(powPts)
                .attr('fill', 'url(#sp-pow-grad)')
                .attr('d', d3.area().x((d) => xS(d.t)).y0(panelH).y1((d) => yPow(d.p)).curve(d3.curveMonotoneX));
            dg0.append('path').datum(powPts)
                .attr('fill', 'none').attr('stroke', '#3b82f6').attr('stroke-width', 2)
                .attr('d', d3.line().x((d) => xS(d.t)).y((d) => yPow(d.p)).curve(d3.curveMonotoneX));
        }
        if (spdS && ySpd) {
            const spdPts = timeS.map((t, i) => ({ t, p: spdS[i] })).filter((d) => d.t >= domain[0] && d.t <= domain[1] && d.p > 0);
            if (spdPts.length > 1) {
                dg0.append('path').datum(spdPts)
                    .attr('fill', 'none').attr('stroke', '#a855f7').attr('stroke-width', 1.8)
                    .attr('stroke-dasharray', '5,2')
                    .attr('d', d3.line().x((d) => xS(d.t)).y((d) => ySpd(d.p)).curve(d3.curveMonotoneX));
            }
        }

        dg1.selectAll('*').remove();
        if (cadS) {
            const cadPts = timeS.map((t, i) => ({ t, p: cadS[i] })).filter((d) => d.t >= domain[0] && d.t <= domain[1] && d.p > 0);
            if (cadPts.length > 1) {
                dg1.append('path').datum(cadPts)
                    .attr('fill', 'url(#sp-cad-grad)')
                    .attr('d', d3.area().x((d) => xS(d.t)).y0(panelH).y1((d) => yCad(d.p)).curve(d3.curveMonotoneX));
                dg1.append('path').datum(cadPts)
                    .attr('fill', 'none').attr('stroke', '#10b981').attr('stroke-width', 2)
                    .attr('d', d3.line().x((d) => xS(d.t)).y((d) => yCad(d.p)).curve(d3.curveMonotoneX));
            }
        }
        if (torS && yTor) {
            const torPts = timeS.map((t, i) => ({ t, p: torS[i] })).filter((d) => d.t >= domain[0] && d.t <= domain[1] && d.p > 0);
            if (torPts.length > 1) {
                dg1.append('path').datum(torPts)
                    .attr('fill', 'none').attr('stroke', '#f59e0b').attr('stroke-width', 2.2)
                    .attr('stroke-dasharray', '6,3')
                    .attr('d', d3.line().x((d) => xS(d.t)).y((d) => yTor(d.p)).curve(d3.curveMonotoneX));
            }
        }
    }
    drawAll(curDomain);

    const xAxG = root.append('g').attr('transform', `translate(0,${ty1 + panelH})`);
    xAxG.call(d3.axisBottom(d3.scaleLinear().domain(curDomain).range([0, innerW])).ticks(8)
        .tickFormat((d) => {
            const m = Math.floor(d / 60);
            const s = Math.round(d % 60);
            return m > 0 ? `${m}m${s}s` : `${Math.round(d)}s`;
        }).tickSize(3));
    xAxG.select('.domain').attr('stroke', '#cbd5e1');
    xAxG.selectAll('line').attr('stroke', '#cbd5e1');
    xAxG.selectAll('text').attr('fill', '#64748b').attr('font-size', 9);

    const ttEl = document.createElement('div');
    ttEl.style.cssText = 'position:absolute;pointer-events:none;display:none;z-index:999;'
        + 'background:rgba(15,23,42,0.96);color:#fff;border-radius:8px;padding:9px 13px;'
        + 'font-size:11.5px;line-height:1.8;white-space:nowrap;'
        + 'box-shadow:0 8px 24px rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.08);';
    container.appendChild(ttEl);

    function updateSprintPointer(mx) {
        mx = Math.max(0, Math.min(innerW, mx));
        const xS = d3.scaleLinear().domain(curDomain).range([0, innerW]);
        const t = xS.invert(mx);
        let ci = 0;
        let md = Infinity;
        timeS.forEach((ts, i) => {
            const d = Math.abs(ts - t);
            if (d < md) {
                md = d;
                ci = i;
            }
        });

        cv0.style('display', null).attr('x1', mx).attr('x2', mx);
        cd0.style('display', null).attr('cx', mx).attr('cy', yPow(powS[ci] || 0));
        if (ySpd && spdS && spdS[ci] > 0) cd0spd.style('display', null).attr('cx', mx).attr('cy', ySpd(spdS[ci]));
        else cd0spd.style('display', 'none');

        cv1.style('display', null).attr('x1', mx).attr('x2', mx);
        if (cadS && cadS[ci] > 0) cd1cad.style('display', null).attr('cx', mx).attr('cy', yCad(cadS[ci]));
        if (cd1tor && torS && torS[ci] > 0) cd1tor.style('display', null).attr('cx', mx).attr('cy', yTor(torS[ci]));

        const ts = timeS[ci];
        const m = Math.floor(ts / 60);
        const s = Math.round(ts % 60);
        const tStr = m > 0 ? `${m}m${s}s` : `${Math.round(ts)}s`;
        let html = `<span style="color:#e2e8f0;font-weight:700;font-size:12px">${tStr}</span><br/>`;
        html += `<span style="color:#93c5fd">⚡ ${Math.round(powS[ci] || 0)} W</span>`;
        if (spdS && spdS[ci] > 0) html += `  <span style="color:#d8b4fe">🚴 ${spdS[ci].toFixed(1)} km/h</span>`;
        if (cadS && cadS[ci] > 0) html += `  <span style="color:#6ee7b7">🌀 ${Math.round(cadS[ci])} rpm</span>`;
        if (torS && torS[ci] > 0) html += `<br/><span style="color:#fcd34d">⚙️ ${Math.round(torS[ci])} Nm</span>`;
        ttEl.innerHTML = html;
        ttEl.style.display = 'block';

        const isTouchS = window.matchMedia('(pointer: coarse)').matches;
        if (isTouchS) {
            ttEl.style.left = '50%';
            ttEl.style.transform = 'translateX(-50%)';
            ttEl.style.top = '4px';
        } else {
            ttEl.style.transform = '';
            let lx = ML + mx + 16;
            if (lx + 220 > W - MR) lx = ML + mx - 230;
            ttEl.style.left = `${lx}px`;
            ttEl.style.top = `${Math.max(8, MT + 20)}px`;
        }
    }

    const totalPH = ty1 + panelH;
    const sprintOverlay = root.append('rect').attr('width', innerW).attr('height', totalPH)
        .attr('fill', 'transparent').style('cursor', 'crosshair')
        .on('mousemove', function(ev) {
            const [mx] = d3.pointer(ev);
            updateSprintPointer(mx);
        })
        .on('mouseleave', function() {
            if (!window.matchMedia('(pointer: coarse)').matches) {
                [cv0, cv1, cd0, cd0spd, cd1cad].forEach((c) => c && c.style('display', 'none'));
                if (cd1tor) cd1tor.style('display', 'none');
                ttEl.style.display = 'none';
            }
        });

    sprintOverlay.node().addEventListener('touchstart', function(ev) {
        ev.preventDefault();
        const r = container.getBoundingClientRect();
        const mx = ev.touches[0].clientX - r.left - ML;
        updateSprintPointer(mx);
    }, { passive: false });
    sprintOverlay.node().addEventListener('touchmove', function(ev) {
        ev.preventDefault();
        const r = container.getBoundingClientRect();
        const mx = ev.touches[0].clientX - r.left - ML;
        updateSprintPointer(mx);
    }, { passive: false });
    sprintOverlay.node().addEventListener('touchend', function(ev) {
        ev.preventDefault();
        [cv0, cv1, cd0, cd0spd, cd1cad].forEach((c) => c && c.style('display', 'none'));
        if (cd1tor) cd1tor.style('display', 'none');
        ttEl.style.display = 'none';
    }, { passive: false });

    if (!window.matchMedia('(pointer: coarse)').matches) {
        requestAnimationFrame(() => {
            const midTime = (effortStartTime + effortEndTime) / 2;
            const xS0 = d3.scaleLinear().domain(curDomain).range([0, innerW]);
            updateSprintPointer(xS0(midTime));
        });
    }
}

function initializeModalListeners() {
    const closeBtn = document.getElementById('streamModalCloseBtn');
    const modalOverlay = document.getElementById('streamModalOverlay');
    const modal = document.getElementById('streamModal');
    const avg30sSlider = document.getElementById('avg30sStreamSlider');
    const avg60sSlider = document.getElementById('avg60sStreamSlider');
    const avg30sValue = document.getElementById('avg30sStreamValue');
    const avg60sValue = document.getElementById('avg60sStreamValue');

    if (!closeBtn || !modalOverlay || !modal) {
        setTimeout(initializeModalListeners, 100);
        return;
    }

    closeBtn.addEventListener('click', closeStreamModal);
    modalOverlay.addEventListener('click', closeStreamModal);

    const debouncedRebuild = debounce(() => {
        if (streamModalData) buildStreamChartsD3();
    }, 300);

    if (avg30sSlider) {
        avg30sSlider.addEventListener('input', function() {
            avg30sSeconds = parseInt(this.value, 10);
            if (avg30sValue) avg30sValue.textContent = `${avg30sSeconds}s`;
            localStorage.setItem('stream_avg30s', avg30sSeconds);
            debouncedRebuild();
        });
    }

    if (avg60sSlider) {
        avg60sSlider.addEventListener('input', function() {
            avg60sSeconds = parseInt(this.value, 10);
            if (avg60sValue) avg60sValue.textContent = `${avg60sSeconds}s`;
            localStorage.setItem('stream_avg60s', avg60sSeconds);
            debouncedRebuild();
        });
    }

    function addWheelToSlider(slider, valueEl, varSetter) {
        if (!slider) return;
        slider.addEventListener('wheel', function(e) {
            e.preventDefault();
            const delta = e.deltaY < 0 ? 1 : -1;
            const newVal = Math.min(parseInt(slider.max, 10), Math.max(parseInt(slider.min, 10), parseInt(slider.value, 10) + delta));
            slider.value = newVal;
            if (valueEl) valueEl.textContent = `${newVal}s`;
            varSetter(newVal);
            localStorage.setItem(slider.id === 'avg30sStreamSlider' ? 'stream_avg30s' : 'stream_avg60s', newVal);
            debouncedRebuild();
        }, { passive: false });
    }
    addWheelToSlider(avg30sSlider, avg30sValue, (v) => { avg30sSeconds = v; });
    addWheelToSlider(avg60sSlider, avg60sValue, (v) => { avg60sSeconds = v; });

    modal.addEventListener('click', function(e) {
        e.stopPropagation();
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeModalListeners);
} else {
    initializeModalListeners();
}

window.addEventListener('storage', function(e) {
    if (e.key === 'inspection_zones' && streamModalData) {
        buildStreamChartsD3();
    }
});

document.getElementById('sidebar-close').addEventListener('click', () => {
    if (isShowingEffortDetail && currentSelectionMetrics) {
        // If showing effort detail with valid selection metrics, restore the metrics
        closeEffortDetailAndShowSelection();
    } else {
        // Otherwise, clear everything
        removeActiveEffortLayer();
        activeEffortIdx = null;
        activeSelectionType = null;
        setSelectionZonesDimmed(false);
        resetChartHighlight();
        document.getElementById('sidebar-content').innerHTML = '';
        currentSelectionMetrics = null;
        isShowingEffortDetail = false;
    }
});

const streamSelectionBtn = document.getElementById('streamSelectionBtn');
if (streamSelectionBtn) {
    streamSelectionBtn.addEventListener('click', openSelectionStreamModal);
}

map.on('load', () => { updateStyleName(); });
showFullRideMetricsCard();
