# PEFFORT Web — Code Review Completa

> Documento generato dopo analisi approfondita di tutto il codebase.  
> Struttura: prima i problemi critici/sicurezza, poi qualità del codice, poi migliorie architetturali, infine suggerimenti minori.

---

## Indice

1. [Problemi Critici / Sicurezza](#1-problemi-critici--sicurezza)
2. [Bug e Correttezza](#2-bug-e-correttezza)
3. [Architettura e Design](#3-architettura-e-design)
4. [Qualità del Codice](#4-qualità-del-codice)
5. [Performance](#5-performance)
6. [Frontend / JavaScript](#6-frontend--javascript)
7. [Deployment e Configurazione](#7-deployment-e-configurazione)
8. [Documentazione e README](#8-documentazione-e-readme)
9. [Quick Wins — Modifiche a Basso Rischio](#9-quick-wins--modifiche-a-basso-rischio)

---

## 1. Problemi Critici / Sicurezza

### 1.1 MapTiler API key esposta nella risposta HTTP

**File:** `webapp/utils/map3d_generator.py`, `webapp/templates/map3d.html`

La chiave MapTiler viene iniettata direttamente nel template HTML:

```python
# map3d_generator.py — la chiave arriva in chiaro nel JSON del template
html = render_html(
    maptiler_key=_get_maptiler_key(),
    ...
)
```

```html
<!-- map3d.html -->
const maptiler_key = '{{ maptiler_key }}';
```

Chiunque apra il sorgente della pagina può leggere la chiave. Su MapTiler è possibile (e consigliato) limitare le chiavi per dominio di riferimento HTTP; ma se la chiave non ha restrizioni, è abusabile.

**Soluzione minima:**  
Aggiungere restrizioni di dominio sulla dashboard MapTiler. Come alternativa più robusta, proxare le richieste tile attraverso il backend FastAPI così la chiave non lascia mai il server — ma questo aumenta la latenza e il traffico.

**Soluzione intermedia accettabile per uso personale:**  
Documentare esplicitamente il rischio nel README e aggiungere un commento nel template.

---
### 1.2 Nessun rate limiting sull'upload

**File:** `webapp/routes/upload.py`

Non c'è rate limiting sull'endpoint `/upload`. Un utente malintenzionato può inondare il server con upload multipli, saturando memoria (ogni sessione tiene un DataFrame in RAM) e CPU (il parsing FIT è costoso). La validazione della dimensione del file (50 MB) è presente, ma non c'è limite sul numero di richieste per IP/tempo.

**Soluzione consigliata per Render:**

```python
# In app.py, aggiungere slowapi o dipendere da un reverse proxy
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# Nel router upload:
@router.post("/upload")
@limiter.limit("10/minute")
async def upload_fit(request: Request, ...):
```

---


## 2. Bug e Correttezza

### 2.1 `split_included` — mutazione durante iterazione

**File:** `webapp/utils/effort_analyzer.py`

```python
def split_included(df, efforts):
    sorted_efforts = sorted(efforts, key=lambda x: x[0])
    changed = True
    
    while changed:
        changed = False
        current_efforts = list(sorted_efforts)  # copia superficiale
        
        for i in range(len(current_efforts)):
            if changed:
                break
            for j in range(len(current_efforts)):
                ...
                if s < s2 and e2 < e:
                    sorted_efforts = [...]  # riassegnazione, non mutazione
```

La logica è corretta (si esce dai loop interni appena `changed = True`), ma l'algoritmo è O(n³) nel caso peggiore. Con molti effort questa funzione può diventare lenta. Considerare un approccio basato su sweep line O(n log n).

---

### 2.2 `detect_sprints` — `time_sec` fuori bounds

**File:** `webapp/utils/effort_analyzer.py`

```python
while i < len(above_threshold) and above_threshold[i]:
    i += 1
end = i
...
durata = time_sec[end-1] - time_sec[start]
```

Se `end == len(time_sec)`, allora `time_sec[end-1]` è l'ultimo elemento — corretto. Ma se `time_sec` è più corto di `above_threshold` per qualche motivo (es. FIT file malformato con record senza timestamp), si ha un `IndexError`. Aggiungere `end = min(end, len(time_sec))`.

---

### 2.3 `trim_segment` — finestra trim più grande dell'effort

**File:** `webapp/utils/effort_analyzer.py`

```python
if end - start < trim_win * 2:
    break
```

Il controllo è `trim_win * 2`, ma il codice successivo tenta di applicare `trim_win` sia a inizio che a fine. Se `end - start == trim_win * 2 + 1`, il trim potrebbe portare a `start >= end`. Meglio usare `trim_win * 2 + 1` come soglia minima, o aggiungere un check finale `if start >= end: return original_start, original_end`.

---

## 3. Architettura e Design

### 3.1 Codice duplicato massiccio tra map3d.js e altimetria_d3.html

Le funzioni `buildStreamChartsD3`, `buildSprintStreamCharts`, `calculateTimeBasedMovingAverage`, `getIntensityZones`, `fmtDur`, e decine di altre sono copiate verbatim (o quasi) tra:

- `webapp/static/js/map3d.js` (~3000 righe)
- `webapp/templates/altimetria_d3.html` (sezione `<script>`, ~1500 righe)
- `webapp/templates/map2d.html` (sezione `<script>`, ~500 righe)

Questo crea tre copie dello stesso codice da mantenere sincronizzate. Una modifica a `buildStreamChartsD3` deve essere replicata manualmente in tre posti.

**Soluzione consigliata:**  
Estrarre il codice condiviso in un file `webapp/static/js/peffort_common.js` e includerlo con un tag `<script src="...">` nei template. Le funzioni specifiche per ogni vista rimangono nei rispettivi file.

---

### 3.2 Setup dei router — pattern fragile

**File:** `webapp/app.py` e tutti i moduli in `routes/`

Il pattern attuale usa variabili globali mutabili (`_shared_sessions`) nei moduli route:

```python
# In ogni route module:
_shared_sessions: Dict[str, Any] = {}

def setup_X_router(sessions_dict):
    global _shared_sessions
    _shared_sessions = sessions_dict
```

Questo funziona ma è fragile: se `setup_X_router` non viene chiamato prima che una request arrivi, le sessioni sono vuote. Non c'è garanzia di ordine di inizializzazione oltre a quello in `app.py`.

**Soluzione più robusta:** Usare FastAPI dependency injection:

```python
# dependencies.py
from fastapi import Request

def get_sessions(request: Request) -> dict:
    return request.app.state.sessions

# In ogni router:
@router.get("/dashboard/{session_id}")
async def dashboard(session_id: str, sessions=Depends(get_sessions)):
    ...
```

Questo elimina le variabili globali e rende i moduli testabili in isolamento.

---

### 3.3 `prepare_chart_data` duplica `calculate_effort_parameters`

**File:** `webapp/routes/altimetria_d3.py` vs `webapp/utils/map3d_core.py`

`prepare_chart_data` in `altimetria_d3.py` contiene circa 200 righe di calcoli metriche (VAM, kJ, HR, velocità, ecc.) che sono sostanzialmente identici a `calculate_effort_parameters` in `map3d_core.py`. Le due funzioni producono gli stessi valori ma con nomi di campo leggermente diversi.

**Soluzione:** Creare una singola funzione `compute_segment_metrics(df, s, e, cp, weight, joules_cum, joules_over_cp_cum)` in un modulo `utils/segment_metrics.py` riutilizzata da entrambi.

---

### 3.4 Sessioni: persistenza in memoria vs. obiettivo di deployment remoto

**File:** `webapp/sessions.py`, `webapp/app.py`

Il file `sessions.py` implementa un `SessionStore` LRU in-memory con TTL di 24 ore. Questo è stato identificato come problema aperto nelle note di progetto. Su Render (free tier) i processi vengono spenti dopo periodi di inattività, perdendo tutte le sessioni.

**Opzione A — Persistenza su disco (consigliata per semplicità):**

```python
# sessions_disk.py
import pickle, json, os
from pathlib import Path

SESSION_DIR = Path("/tmp/peffort_sessions")
SESSION_DIR.mkdir(exist_ok=True)

def save_session(session_id: str, data: dict):
    # Serializza solo i metadati (non il DataFrame)
    meta = {k: v for k, v in data.items() if k != 'df'}
    df = data.get('df')
    
    with open(SESSION_DIR / f"{session_id}.pkl", 'wb') as f:
        pickle.dump({'meta': meta, 'df': df}, f)

def load_session(session_id: str) -> dict | None:
    path = SESSION_DIR / f"{session_id}.pkl"
    if not path.exists():
        return None
    with open(path, 'rb') as f:
        data = pickle.load(f)
    return {**data['meta'], 'df': data['df']}
```

**Opzione B — Render Persistent Disk:** Montare un disco persistente su `/data` e puntare `SESSION_DIR` lì. Costa ~$0.25/GB/mese.

**Nota:** Su Render free tier, `/tmp` è ephemeral ma persiste durante la vita del processo. La Opzione A funziona per il caso d'uso "carico → consulta entro qualche ora" se si usa Render's persistent disk.

---

## 4. Qualità del Codice

### 4.1 Template `altimetria_d3.html` — troppo grande (>3000 righe)

Il template include centinaia di righe di JavaScript inline mescolate con HTML/CSS. Questo rende impossibile usare un linter JS, il debugging è difficile, e il caching del browser non può riutilizzare il codice tra pagine diverse.

**Soluzione:** Estrarre in `webapp/static/js/altimetria_d3.js`.

---

### 4.2 `map3d.js` — 3500+ righe in un singolo file

Lo stesso problema di `altimetria_d3.html`. Il file `map3d.js` mescola:
- Inizializzazione mappa
- Logica altimetria
- Stream modal (D3)
- Calcolo metriche selezione
- Gestione effort markers
- Event handling

Andrebbero separati in moduli logici (es. `map3d_stream.js`, `map3d_altimetry.js`, `map3d_metrics.js`).

---

### 4.3 Costanti magiche sparse ovunque

Esempi sparsi nel codice:

```python
# effort_analyzer.py
WINDOW_SECONDS = 60
MERGE_POWER_DIFF_PERCENT = 15
# ... ma poi nei test:
efforts = create_efforts(df=df, cp=cp, window_sec=60, merge_pct=15, ...)
```

```javascript
// map3d.js
const bufferSeconds = 120;
const HIT_DIST = isTouchDevice ? 22 : 10;
const STEP_Y = PILL_H + PILL_PAD;
```

Le costanti Python sono definite in `effort_analyzer.py` ma non vengono usate nelle chiamate alle funzioni stesse. Le costanti JS non sono definite centralizzate.

---

### 4.5 `config.py` / `config_template.py` — naming confuso

Il file produttivo si chiama `config.py` (in `.gitignore`) e il template `config_template.py`. Questa convenzione non è ovvia: chi clona il repo vede `config_template.py` ma deve creare `config.py`. Un pattern più standard è `config.example.py` con un commento chiaro, o meglio ancora, solo variabili d'ambiente (vedi §7).

---

### 4.6 Dead code e TODO irrisolti

**File:** `webapp/routes/api.py`

```python
except Exception as e:
    logger.warning(f"Sprint detection failed: {e}")
    sprints = []
    sprint_detection_error = str(e)
else:
    sprint_detection_error = None
```

`sprint_detection_error` viene salvato nella sessione ma non viene mai mostrato all'utente né loggato in modo prominente. Se la detection fallisce silenziosamente, l'utente non sa perché non vede sprint.

**File:** `ROADMAP.md` — contiene TODO inline non tracciati in un issue tracker.

---

### 4.7 `api.py` — naming import endpoint potenzialmente confuso

**File:** `webapp/routes/api.py`

Esistono due endpoint diversi (`/{session_id}/import` e `/import-modifications/{session_id}`) con naming simile ma semantica diversa. Anche se entrambi sono attivi, lato manutenzione e UX API naming la distinzione non è immediata.

---

### 4.8 Type hints incomplete

Molte funzioni mancano di type hints o le usano in modo impreciso:

```python
# map3d_core.py
def calculate_effort_parameters(s: int, e: int, avg: float, 
                               df: pd.DataFrame, 
                               alt_values: np.ndarray,
                               ...) -> Dict[str, Any]:  # troppo generico
```

`Dict[str, Any]` potrebbe essere sostituito con un `TypedDict` o dataclass per rendere esplicito il contratto.

---

## 5. Performance

### 5.1 JavaScript — `computePower5sProfile()` ricalcolato ad ogni selezione

**File:** `webapp/static/js/map3d.js`

```javascript
function computePower5sProfile() {
    if (power5sCache) return power5sCache;
    ...
}
```

Il caching è presente, ma la funzione `calculateTimeBasedMovingAverage` per il profilo 5s viene ricalcolata in O(n) ogni volta che viene chiamata `filterTraceByDistance`. Per file di 3+ ore (10000+ punti) questo è percettibile. Il cache `power5sCache` è a livello di variabile globale JS — corretto, ma viene perso se la pagina viene ricaricata.

---

### 5.2 `altimetria_d3.py` — `convert_to_python_types` su struttura enorme

```python
chart_data = convert_to_python_types(chart_data)
```

`convert_to_python_types` è ricorsiva e attraversa l'intera struttura dati (che include stream dati per ogni effort — potenzialmente milioni di punti). Sarebbe più efficiente convertire i tipi numpy alla fonte, durante la creazione dei dati, invece di fare una passata ricorsiva alla fine.

---

## 6. Frontend / JavaScript

### 6.1 `localStorage` usato per sincronizzare zone tra tab

**File:** `webapp/templates/inspection.html`, `altimetria_d3.html`, `map3d.js`

Le zone di intensità vengono salvate in `localStorage` nell'Inspection tab e lette negli altri tab. Questo è un pattern valido, ma:

1. Se l'utente apre due sessioni diverse in tab diversi, le zone dell'ultima sessione sovrascrivono quelle della precedente (mitigabile con chiavi localStorage session-scoped).
2. Non c'è versioning: se il formato delle zone cambia in futuro, i dati vecchi in localStorage potrebbero causare errori silenziosi.

**Soluzione minima:** Aggiungere un check di versione:

```javascript
const ZONES_VERSION = 'v2';
const stored = localStorage.getItem(`inspection_zones_${ZONES_VERSION}`);
```

---

### 6.3 `inspection.html` — slider avg30s ha range 1-60 ma la label dice "30s Avg"

```html
<input type="range" id="avg30sSeconds" value="30" min="1" max="60" step="1">
```

Il range va da 1 a 60 secondi, ma lo slider è etichettato "Chart 2 - Avg" senza contesto. Se l'utente imposta 1 secondo, sta praticamente vedendo il dato raw, il che è confondente. Aggiungere un tooltip o una label con il valore attuale.

---

### 6.4 `location.reload()` dopo ogni operazione API

In `dashboard.html`, ogni operazione di successo (redetect efforts/sprints, update CP/weight) chiama `location.reload()`. Questo ricarica l'intera pagina, perdes lo stato dei tab aperti e della posizione di scroll. Sarebbe più UX-friendly aggiornare solo le parti necessarie della UI.

---

## 7. Deployment e Configurazione

### 7.1 MapTiler key: da variabile d'ambiente ma con fallback a file locale

**File:** `webapp/utils/map3d_generator.py`

```python
def _get_maptiler_key() -> str:
    key = os.environ.get("MAPTILER_API_KEY", "")
    if key:
        return key
    try:
        from config import get_maptiler_key
        return get_maptiler_key()
    except ImportError:
        ...
        return ""
```

Questa logica è corretta per il deployment (env var ha precedenza). Il fallback a `config.py` è utile per lo sviluppo locale. Documentare questo comportamento esplicitamente nel README per Render.

---

### 7.2 Hardcoded host e porta in STARTUP.md

```markdown
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8001
```

Su Render, la porta viene passata come variabile d'ambiente `PORT`. Aggiungere istruzioni per Render:

```bash
uvicorn app:app --host 0.0.0.0 --port ${PORT:-8001}
```

---

## 8. Documentazione e README

### 8.1 `ROADMAP.md` — note non strutturate

`ROADMAP.md` contiene note informali in italiano miste a TODO tecnici. Non è leggibile da un collaboratore esterno e non ha priorità o stato.

---

### 8.2 Mancanza di docstring nelle funzioni frontend-facing

Le funzioni Python core (`parse_fit`, `create_efforts`, `merge_extend`) hanno docstring ragionevoli. Le funzioni dei route (`dashboard_view`, `upload_fit`) hanno solo commenti sommari. Le funzioni JS non hanno JSDoc.

---

## 9. Quick Wins — Modifiche a Basso Rischio

Quick wins ancora aperte:

| # | File | Modifica | Impatto |
|---|------|----------|---------|
| 1 | `dashboard.html` | Ridurre uso di `location.reload()` con update parziali UI | UX |
| 2 | `webapp/templates` + `map3d.js` | Completare isolamento localStorage zone per sessione in tutte le viste | Correttezza multi-tab |
| 3 | `api.py` | Uniformare naming/documentazione endpoint import | Manutenibilità API |

---

## Riepilogo per Priorità

### Priorità Alta (prima del deployment)
1. **Completato** — §1.1 Chiave MapTiler: aggiunti warning runtime + checklist operativa + variabile `MAPTILER_KEY_DOMAIN_RESTRICTED`
2. **Completato** — §1.2 Rate limiting upload: strategia validata (limiter in-memory + supporto proxy headers + env di tuning produzione)
3. **Completato** — §3.4 Persistenza sessioni su Render: strategia validata (`/data` persistent disk consigliato, Redis opzionale)

### Priorità Media (refactoring successivo)
4. **§4.1/4.2** — Template JS troppo grandi → separare in file statici

### Priorità Bassa (miglioramento continuo)
5. **§4.8** — Aggiungere TypedDict per i return type delle funzioni core
7. **§8.2** — Aggiungere docstring/JSDoc nelle parti frontend-facing

---

*Review completata — aprile 2026*
