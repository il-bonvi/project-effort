# PEFFORT - Inspection Tab: Feature Complete (Frontend + Backend)

## 1. Scopo della tab Inspection
La tab Inspection e un editor interattivo di intervalli (efforts e sprints) sopra la traccia di potenza.
Obiettivo principale:
- visualizzare il segnale di potenza su 3 livelli (raw + medie mobili)
- permettere editing manuale preciso degli intervalli
- salvare modifiche lato server senza rilanciare detection automatica
- mantenere coerenza con le altre tab (dashboard, map3d, altimetria/export)

Entry point UI:
- dashboard iframe: `/inspection/{session_id}`

File principali coinvolti:
- `webapp/routes/inspection.py`
- `webapp/templates/inspection.html`
- `webapp/routes/api.py`
- `webapp/templates/dashboard.html`
- `webapp/templates/map3d.html` (sync cross-tab)

---

## 2. Architettura funzionale

### 2.1 Livello backend (rendering + API)
1. Route server-rendered Inspection:
- GET `/inspection/{session_id}`
- prepara dati e renderizza `inspection.html` con Jinja2

2. API per manipolazione/salvataggio:
- GET `/api/{session_id}/export-modifications`
- POST `/api/{session_id}/apply-local-modifications`
- POST `/api/{session_id}/update-cp-weight`
- endpoint effort/sprint management aggiuntivi (merge/extend/split/trim/redetect)

3. Session state condiviso:
- tutto ruota su `sessions[session_id]`
- mutate principali: `efforts`, `sprints`, `cp`, `weight`, `stats`
- invalidazione cache derivate quando i dati cambiano

### 2.2 Livello frontend (single-page embedded)
1. Rendering client-side su ECharts con 3 pannelli verticali sincronizzati.
2. Editing intervalli via drag endpoint START/END.
3. Gestione zone intensita locale (localStorage, session-scoped key).
4. Persistenza:
- export JSON modifiche (download file)
- apply su backend (persistenza sessione in memoria)
5. Sync cross-tab tramite BroadcastChannel.

---

## 3. Librerie, dipendenze e tecnologie

### 3.1 Libreria grafica principale
- ECharts 5.5.0 (CDN):
  - line chart multi-grid
  - scatter points per endpoint drag
  - markArea per evidenziare intervalli e bande zona
  - dataZoom slider + inside
  - tooltip custom formatter

### 3.2 Framework/UI stack
- HTML + CSS inline
- JavaScript vanilla (nessun framework SPA)
- Jinja2 per iniezione dati server-side
- FastAPI + Pydantic lato backend
- NumPy backend per statistiche segmenti

### 3.3 Comunicazione e storage
- Fetch API (REST JSON)
- localStorage (preferenze grafiche + zone)
- BroadcastChannel per notifiche tra tab/iframe

---

## 4. Backend Inspection: dettaglio completo

## 4.1 Route e rendering template
In `webapp/routes/inspection.py`:
- `setup_inspection_router(...)`
  - configura `Jinja2Templates`
- `inspection_view(session_id, request, sessions)`
  - valida sessione
  - invoca `generate_inspection_data(...)`
  - renderizza `inspection.html`

## 4.2 Preparazione dati per frontend
Funzione `generate_inspection_data(...)`:
1. legge `time_sec` e `power` dal DataFrame sessione.
2. converte efforts da indici a tempo reale:
- input interno: `(start_idx, end_idx, avg_power)`
- output template: `start`, `end` in secondi (end calcolato su `end_idx - 1`).
3. converte sprints in formato visuale:
- ordinamento per avg potenza desc
- calcola `max_power`, `avg_power`, `duration`, colore e label.
4. genera blocco stats HTML (cards riassuntive).
5. serializza in JSON per JS:
- `time_axis_json`
- `power_data_json`
- `efforts_data_json`
- `sprints_data_json`
- `cp_json`

## 4.3 Ordine canonico e coerenza
In `webapp/routes/api.py`:
- `_normalize_efforts`: ordina cronologicamente (start/end index)
- `_normalize_sprints`: ordina per avg power desc
- `_normalize_session_intervals`: applica entrambi

Questo stabilizza numerazione label e coerenza cross-tab.

## 4.4 Applicazione modifiche locali (core editing persistence)
Endpoint:
- POST `/api/{session_id}/apply-local-modifications`

Payload validato da `LocalModificationsRequest`:
- efforts: start/end/label/color
- sprints: start/end/label/color
- deleted_effort_indices
- deleted_sprint_indices

Logica server:
1. identifica colonna tempo (`time_sec`, fallback `time`/`timestamp`).
2. converte timestamp frontend -> indice dataframe via `searchsorted` (nearest).
3. mantiene `end_idx` esclusivo (`+1`), con clamp su limiti validi.
4. ricalcola avg power per ogni segmento.
5. per sprints aggiorna dizionario con start/end/label/avg.
6. salva in sessione, normalizza ordine, invalida cache.

Output:
- esito success con conteggi finali efforts/sprints.

## 4.5 Export modifiche
Endpoint:
- GET `/api/{session_id}/export-modifications`

Comportamento:
- produce JSON round-trip friendly
- mantiene indici (`new_start`, `new_end`) per riallineamento esatto
- include timestamp export e conteggi originali/attivi

## 4.6 Update CP/Weight
Endpoint:
- POST `/api/{session_id}/update-cp-weight`

Vincoli:
- CP tra 50 e 500 W
- peso tra 40 e 150 kg

Effetti:
- aggiorna sessione
- ricalcola metriche ride stats
- invalida cache derivate

Nota: la UI Inspection aggiorna CP localmente in tempo reale; questo endpoint serve per persistenza lato sessione quando richiamato da altre viste/controlli.

---

## 5. Frontend Inspection: dettaglio completo

## 5.1 Struttura UI principale
1. Stats cards (render backend HTML):
- duration, avg power, NP, IF, TSS, VI, avg HR, distance, elevation.

2. Main chart area:
- container `#mainChart`
- altezza 800px
- 3 grafici stacked sincronizzati sull asse tempo.

3. Legende editing:
- blocco Efforts con add/delete toggle
- blocco Sprints con add/delete toggle

4. Control panel zone/intensita:
- CP input
- slider media Chart2 e Chart3
- toggle colorazione per zone
- opacity controls
- color picker per linee quando zone color OFF
- tabella zone editabile (min/max %, nome, colore, delete/add/reset)

5. Save controls:
- Export Modifiche (download JSON)
- Salva Modifiche (apply su backend)

## 5.2 Modello dati frontend
Dati iniettati da Jinja2:
- `timeAxis`
- `powerData`
- `effortsData`
- `sprintsData`
- `cp`

Stato runtime:
- slider windows (`avg30sSeconds`, `avg60sSeconds`)
- style flags (`zoneColorEnabled`, opacity values, line colors)
- set di cancellazione logica (`deletedEfforts`, `deletedSprints`)
- definizione zone locali (`localZones`)

## 5.3 Logica grafica (livello visual)

### 5.3.1 Triplo layer chart
Chart 1:
- Potenza istantanea (raw)

Chart 2:
- Media mobile centrata configurabile 1-60s (default 30)

Chart 3:
- Media mobile centrata configurabile 60-360s (default 60)

Ogni chart usa asse tempo condiviso, con dataZoom comune.

### 5.3.2 Colorazione per zone
Funzione chiave: `makeZoneSeries(...)`

Comportamento:
- converte zona percentuale CP in range Watt
- segmenta la curva solo nei tratti appartenenti alla zona
- calcola punti di crossing con interpolazione lineare
- spezza con `null` dove la serie esce dalla zona
- genera una serie line dedicata per ogni zona

Risultato:
- curva colorata per zona con transizioni precise ai confini.

### 5.3.3 Bande orizzontali di zona
Per ogni zona, su ogni grid viene aggiunto un `markArea`:
- range verticale [minW, maxW]
- colore zona
- opacita regolabile (`zoneBandsOpacity`)

### 5.3.4 Overlay intervalli effort/sprint
Efforts:
- markArea su tutti e 3 i grafici
- scatter START/END su chart 1
- label effort in alto

Sprints:
- markArea solo chart 1 (opacita piu alta)
- scatter START/END su chart 1
- label sprint inside top

### 5.3.5 Tooltip custom
Mostra:
- tempo formattato (m/s)
- valore potenza
- colore testuale coerente con zona attiva rispetto a CP

## 5.4 Logica interattiva (livello comportamento)

### 5.4.1 Add Effort / Add Sprint
- usa finestra visibile corrente (dataZoom)
- piazza nuovo intervallo nel terzo centrale della vista
- calcola metriche iniziali dal segmento selezionato
- aggiorna legend e chart

### 5.4.2 Delete logico
- click su bottone x in card legenda
- non rimuove subito da array base: marca in Set deleted
- rebuild chart escludendo elementi deleted

### 5.4.3 Drag endpoint (right-click workflow)
- drag attivato con tasto destro vicino a START/END
- tolerance temporale: ~1% durata totale attività
- mentre trascina:
  - aggiorna start/end
  - ricalcola avg (e max per sprint)
  - aggiorna card legenda live
- su mouseup:
  - normalizza labels
  - rebuild finale

### 5.4.4 Pan/Zoom
- slider esterno + inside zoom
- preservazione stato zoom durante rebuild

### 5.4.5 Aggiornamento medie mobili
- `calculateCenteredMovingAverage(...)`
- aggiornamento realtime al movimento slider
- debounce leggerissimo con timeout

## 5.5 Gestione zone locali

Default zone (7):
- Z1 0-60
- Z2 60-80
- Z3 80-90
- Z4 90-105
- Z5 105-135
- Z6 135-300
- Z7 300-999

Funzioni:
- edit min/max, nome, colore
- propagazione adiacente (modifica min aggiorna max precedente e viceversa)
- add zone (finche ultimo max non e 999)
- reset default
- display watt dinamico in base a CP
- persist locale immediata

Chiavi localStorage rilevanti:
- `inspection_zones_v2_{session_id}`
- fallback legacy: `inspection_zones_v2`, `inspection_zones`
- `inspection_zone_color_enabled`
- `inspection_zone_fill_opacity`
- `inspection_zone_bands_opacity`
- `inspection_power_color`
- `inspection_avg30s_color`
- `inspection_avg60s_color`
- `inspection_cp`

## 5.6 Salvataggio e export

### 5.6.1 Export JSON modifiche (download)
Bottone: Esporta Modifiche
- GET `/api/{session_id}/export-modifications`
- crea Blob client-side
- scarica `effort_modifications.json`

### 5.6.2 Salvataggio locale su server
Bottone: Salva Modifiche
- normalizza labels
- invia payload con efforts/sprints + deleted indices
- POST `/api/{session_id}/apply-local-modifications`
- mostra stato visuale e conteggi finali

### 5.6.3 Sync altre tab
Dopo salvataggio:
- BroadcastChannel `peffort_{session_id}`
- messaggio type `efforts_updated`

In `map3d.html`:
- listener su stesso canale
- al messaggio, reload mappa 3D per riflettere modifiche

---

## 6. Livello grafico: design system reale della tab

Tipografia e base:
- font stack system sans-serif
- tema chiaro
- cards e pannelli con gradient leggeri

Palette funzionale:
- power line default blu
- avg30s arancio
- avg60s rosso
- efforts palette multipla ciclica
- sprints palette dedicata + background card rosato
- zone palette customizzabile utente

Pattern visuali:
- bordi sottili + shadow leggere
- card legenda con left border colorato
- markArea semitrasparenti per contesto temporale
- endpoint START/END enfatizzati con scatter marker + label

Usabilita:
- informazioni dense ma separazione per blocchi
- tabella zone compatta per edit rapido
- feedback stato salvataggio con testo e colore

---

## 7. Contratti dati principali

Effort interno backend:
- tuple `(start_idx, end_idx, avg_power)`

Sprint interno backend:
- dict con chiavi almeno `start`, `end`, `label`, `avg`
- opzionali: `max_power`, `color`

Payload apply-local-modifications:
- efforts[]: start/end/label/color
- sprints[]: start/end/label/color
- deleted_effort_indices[]
- deleted_sprint_indices[]

Output export-modifications:
- efforts con `new_start/new_end` (indici)
- sprints con `start/end` (indici)
- metadati conteggi e timestamp

---

## 8. Comportamenti avanzati/edge case gestiti

1. Sessione mancante -> 404.
2. Dati FIT assenti o vuoti -> errore API.
3. Drag che invertirebbe start/end -> bloccato (delta minimo).
4. Clamp indici ai limiti dataframe durante conversione timestamp.
5. Compatibilita zone legacy localStorage.
6. Ordinamento canonico per evitare drift di label tra salvataggi.
7. Invalidazione cache derivate dopo modifiche.
8. Fallback robusti su browser senza BroadcastChannel (warning console).

---

## 9. Relazione con altre tab/moduli

1. Dashboard:
- ospita Inspection in iframe dedicato.

2. Settings tab/API:
- puo rilanciare redetect efforts/sprints con parametri diversi.

3. Map3D:
- riceve segnale aggiornamento intervalli via BroadcastChannel.

4. Export HTML report:
- puo ricevere zone custom dal browser per coerenza visuale con Inspection.

---

## 10. Sintesi tecnica
Inspection e un editor visuale ad alta interattivita che combina:
- rendering server-side iniziale (Jinja2)
- analisi e modifica client-side in tempo reale (ECharts + vanilla JS)
- persistenza sessione su API FastAPI
- coerenza cross-tab tramite ordinamento canonico + canale broadcast

In pratica copre sia livello logico (segment editing, conversioni tempo/indice, normalizzazione, persistenza) sia livello grafico (triplo chart, zone dinamiche, overlay intervalli, tooltip contestuale, controlli visuali avanzati).
