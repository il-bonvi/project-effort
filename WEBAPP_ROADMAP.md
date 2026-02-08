# 📋 ROADMAP WEBAPP - PEFFORT Web Interface

**Status**: � Phase 1 ✅ + Altimetria Tab ✅  
**Ultima modifica**: Feb 8, 2026  
**Tempo totale stimato**: 4-5 ore

---

## 📊 STATO ATTUALE

### ✅ GIÀ IMPLEMENTATO in `app.py`
- [x] FastAPI setup di base
- [x] Home route GET `/` con form di upload HTML/CSS
- [x] Session storage (in-memory)
- [x] Upload directory
- [x] Import PEFFORT modules (peffort_engine, peffort_config)
- [x] Logging configuration
- [x] **Phase 1 COMPLETATA** - Upload endpoint funzionante
- [x] **Tab Altimetria COMPLETATA** - Visualizzazione Plotly identica all'app originale

## 🎯 PHASE 1: SETUP BASE (30 min)
**Obiettivo**: Far funzionare lo skeleton e il primo upload FATTO
tutto. Colo
### ❌ DA FARE

---

### Task 1.1: Upload Endpoint
- [ ] Implementare `POST /upload` endpoint
- [ ] Validare file .fit
- [ ] Salvare file in uploads/
- [ ] Generare session_id
- [ ] Ritornare session_id e lista file caricati
- **Moduli PEFFORT**: `peffort_engine.parse_fit()`
- **Output**: JSON `{"session_id": "...", "files": [...]}`

### Task 1.2: Session Management
- [ ] Struttura dati session: `{file_path, fit_data, efforts, sprints}`
- [ ] Funzione `load_session(session_id)` 
- [ ] Funzione `save_session(session_id, data)`
- [ ] Cleanup automatico session vecchie (> 24h)
- **Tempo**: 20 min

### Task 1.3: Testing Phase 1
- [ ] Start server: `uvicorn webapp.app:app --reload`
- [ ] Test upload file .fit
- [ ] Verificare session storage
- **Tempo**: 10 min

---

## 🎨 PHASE 2: INSPECTION TAB (1h 30 min)
**Obiettivo**: Mostrare analisi FIT completa nel browser

### Task 2.1: Parse + Detect Flow
- [ ] `POST /api/analyze/{session_id}`
- [ ] Importare `inspection_core.process()` o usare `parse_fit() → detect_sprints()`
- [ ] Calcolare:
  - Merge/Extend per sforzi
  - Detected sprints
  - Statistiche base (durata, distanza, HR, potenza)
- [ ] Salvare risultati in session
- **Moduli PEFFORT**: 
  - `peffort_engine.parse_fit()`
  - `peffort_engine.detect_sprints()`
  - `peffort_engine.create_efforts()`
  - `inspection_core.process()` (se usa GUI helpers)
- **Output**: JSON con efforts, sprints, stats

### Task 2.2: Inspection HTML Generation
- [ ] `GET /inspection/{session_id}` → HTMLResponse
- [ ] Estrarre logica dal `inspection_web_gui.py` → `_generate_html()`
- [ ] Embedded CSS + JS (come in inspection_web_gui.py)
- [ ] Tabelle:
  - Efforts (merge, extend, split)
  - Sprints (detected, with stats)
- **Tempo**: 40 min

### Task 2.3: API Edit Endpoints (InPlace)
- [ ] `POST /api/{session_id}/merge` - merge 2 efforts
- [ ] `POST /api/{session_id}/extend` - estendi effort
- [ ] `POST /api/{session_id}/split` - split effort
- [ ] `DELETE /api/{session_id}/effort/{effort_id}` - cancella effort
- [ ] Update session, rigenera HTML
- **Moduli PEFFORT**: 
  - `peffort_engine.merge_extend()`
  - `peffort_engine.split_included()`
- **Tempo**: 30 min

### Task 2.4: Testing Phase 2
- [ ] Upload FIT
- [ ] Analyze → mostra inspection HTML
- [ ] Test merge/extend/split/delete
- [ ] Reload page → dati persistono
- **Tempo**: 20 min

---

## 🗺️ PHASE 3: MAP3D TAB (1h)
**Obiettivo**: Mostrare mappa 3D con elevazione

### Task 3.1: Map3D Generation
- [ ] `GET /map3d/{session_id}` → HTMLResponse
- [ ] Estrarre da `map3d_gui.py` → logica generazione 3D
- [ ] Usare `map3d_core.py` e `map3d_builder.py` per dati
- [ ] Embedded Leaflet/THREE.js visualization
- [ ] Integrazione con session data
- **Moduli PEFFORT**: 
  - `map3d_core.create_3d_map()`
  - `map3d_builder.build_profile()`
  - `map3d_renderer.generate_html()`
- **Legame**: Elevazione derivata da FIT data
- **Tempo**: 45 min

### Task 3.2: Navigation + Tab Styling
- [ ] Aggiungere tab navigation (Inspection, Map3D, ...)
- [ ] CSS per tab switching
- [ ] Active tab highlighting
- **Tempo**: 15 min

---ALTIMETRIA TAB ✅ COMPLETATA
**Obiettivo**: Grafico altimetrico con efforts e sprints (Plotly)

### Task 4.1: Altimetria Route ✅
- [x] Creato `routes/altimetria.py` con endpoint `GET /altimetria/{session_id}`
- [x] Regibis.1: Planimetria Graph (opzionale).py`
- [x] Integrato nel dashboard come nuovo tab
- [x] Usa `peffort_exporter.plot_unified_html()` - identico all'app originale
- [x] Plotly installato e configurato
- [x] Fix import relativi in peffort_exporter.py
- **Moduli PEFFORT**: 
  - `peffort_exporter.plot_unified_html()`
- **Tempo effettivo**: 30 min

### 🎨 Caratteristiche implementate:
- ✅ Grafico Plotly interattivo distanza/altitudine
- ✅ Efforts colorati per zona (colori identici all'originale)
- ✅ Sprints evidenziati in nero
- ✅ Hover dettagliato con tutte le metriche (W, W/kg, VAM, HR, cadenza, ecc.)
- ✅ Annotations con label efforts e sprints
- ✅ Legend interattiva per mostrare/nascondere segmenti
- ✅ Toolbar Plotly completo (zoom, pan, reset)
- ✅ Responsive e fullscreen

---

## 📉 PHASE 4 BIS: PLANIMETRIA TAB (opzionale, da fare)
**Obiettivo**: Mappa planimetrica vista dall'alto (GPS)
## 📉 PHASE 4: PLANIMETRIA & ALTIMETRIA TABS (1h)
**Obiettivo**: Grafici di altimetria e planimetria

### Task 4.1: Planimetria Graph
- [ ] `GET /planimetria/{session_id}` → HTMLResponse
- [ ] Estrarre da `pplan_gui.py`
- [ ] Disegnare:
  - Profilo altimetrico (elevation vs distance)
  - Slope indicators
- [ ] Embedded Chart.js o simile
- **Moduli PEFFORT**: 
  - `pplan_core.calculate_profile()` oppure da map3d
  - `pplan_exporter.export_profile()`
- **Tempo**: 30 min

### Task 4bis.2: Planimetria Details (opzionale)
- [ ] Mostrare climbs detected, descents
- [ ] Statistiche: max elevation, min elevation, total ascent/descent
- [ ] Interattivo con mouse hover
- **Tempo**: 30 min

---

## 📤 PHASE 5: EXPORT TAB (45 min)
**Obiettivo**: Esportare i dati in vari formati

### Task 5.1: Export Endpoints
- [ ] `GET /export/{session_id}/fit` → scarica FIT modificato
- [ ] `GET /export/{session_id}/json` → scarica JSON efforts+sprints
- [ ] `GET /export/{session_id}/gpx` → scarica GPX (opzionale)
- [ ] `GET /export/{session_id}/csv` → scarica CSV efforts
- **Moduli PEFFORT**: 
  - `peffort_exporter.export_fit()`
  - `peffort_exporter.export_json()`
  - `stream_exporter.export_stream()`
- **Tempo**: 30 min

### Task 5.2: Export UI
- [ ] Tab "Export" con bottoni per download
- [ ] Mostrare format disponibili
- [ ] Timestamp di export
- **Tempo**: 15 min

---

## 🎯 PHASE 6: STREAM TAB (30 min)
**Obiettivo**: Visualizzare dati in real-time stream (se applicabile)

### Task 6.1: Stream Integration
- [ ] `GET /stream/{session_id}` → HTMLResponse
- [ ] Integrare da `stream_gui.py`
- [ ] Mostrare dati FIT record-by-record
- [ ] Filtri opzionali
- **Moduli PEFFORT**: 
  - `stream_gui.display_stream()`
  - Stream data from parse_fit result
- **Tempo**: 30 min

---

## ✨ PHASE 7: POLISH & ERROR HANDLING (45 min)
**Obiettivo**: Rendere stabile e user-friendly

### Task 7.1: Error Handling
- [ ] Try/catch negli endpoint
- [ ] Validare file upload (estensione, size)
- [ ] Gestire parse errors
- [ ] HTTP exceptions coerenti (400, 404, 500)
- [ ] Error messages nel frontend
- **Tempo**: 20 min

### Task 7.2: Session Cleanup
- [ ] Implementare pulizia file vecchi
- [ ] Timeout session (default 24h)
- [ ] Delete endpoint per manual cleanup
- [ ] Log cleanup operations
- **Tempo**: 15 min

### Task 7.3: Frontend Polish
- [ ] Loading spinners durante analyze
- [ ] Toast notifications per successo/errore
- [ ] Responsive design (mobile-friendly)
- [ ] Migliorare UI (colori, fonts, spacing)
- **Tempo**: 10 min

---

## 🔒 PHASE 8: DEPLOYMENT & DOCS (30 min)
**Obiettivo**: Pronto per production

### Task 8.1: Configuration
- [ ] Aggiungere `.env` support
- [ ] Config per upload dir, timeout, max file size
- [ ] Production vs Development settings
- **Tempo**: 10 min

### Task 8.2: Docker (opzionale)
- [ ] Dockerfile
- [ ] docker-compose.yml
- [ ] Build e test container
- **Tempo**: 15 min

### Task 8.3: Documentation
- [ ] README con setup instructions
- [ ] API endpoint documentation
- [ ] Troubleshooting guide
- **Tempo**: 5 min

---

## 📝 MODULI PEFFORT DA USARE

| Fase | Modulo | Funzione | Utilizzo |
|------|--------|----------|----------|
| 2 | peffort_engine.py | `parse_fit()`, `detect_sprints()`, `create_efforts()` | Parse FIT, analizzare sforzi |
| 2 | inspection_core.py | `process()` | Logica detection, supporto |
| 2 | inspection_web_gui.py | `_generate_html()` | Template HTML inspection |
| 2 | peffort_engine.py | `merge_extend()`, `split_included()` | Edit efforts in-place |
| 3 | map3d_core.py | Funzioni 3D | Calcoli geometrici |
| 3 | map3d_builder.py | `build_profile()` | Dati per mappa |
| 3 | map3d_gui.py | HTML generation | Template 3D |
| 4 | pplan_gui.py | `_generate_html()` | Planimetria graph |
| 5 | peffort_exporter.py | `export_fit()`, `export_json()` | Export formati |
| 6 | stream_gui.py | `display_stream()` | Stream visualization |

---

## 🚀 TIMELINE SEMPLIFICATA

| Fase | Complessità | Tempo | Note |
|------|-------------|-------|------|
| 1. Setup Base | ⭐ Bassa | 30 min | ✅ In parte fatto |
| 2. Inspection | ⭐⭐⭐ Alta | 100 min | Core della webapp |
| 3. Map3D | ⭐⭐⭐ Alta | 60 min | Riuso peffort |
| 4. Planimetria | ⭐⭐ Media | 60 min | Grafici |
| 5. Export | ⭐⭐ Media | 45 min | Downloader |
| 6. Stream | ⭐ Bassa | 30 min | Optional |
| 7. Polish | ⭐⭐ Media | 45 min | Stabilità |
| 8. Deploy | ⭐ Bassa | 30 min | Optional |
| **TOTALE** | | **400 min** | **~6.5 ore** |

---

## 🔄 DIPENDENZE TRA FASI

```
Phase 1 (Setup) 
    ↓
Phase 2 (Inspection) ← CORE
    ↓
Phase 3 (Map3D)
    ↓
Phase 4 (Planimetria)
    ↓
Phase 5 (Export)
    ↓
Phase 6 (Stream) - Parallelo a 3-5
    ↓
Phase 7 (Polish)
    ↓
Phase 8 (Deploy)
```

---

## ✅ NEXT STEPS (SUBITO)

1. **Completare Phase 1** → Upload endpoint funzionante
2. **Testare** → Far funzionare upload + session save
3. **Collegare Phase 2** → Parse + primo HTML inspection

**File da editare**: 
- `webapp/app.py` (estendere con endpoints)
- `requirements.txt` (aggiungere dipendenze se necessite)

---

**Created**: 2026-02-08  
**Version**: 1.0
