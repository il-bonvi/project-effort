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

### 1.2 Path traversal parzialmente mitigato ma non completamente

**File:** `webapp/routes/upload.py`

```python
safe_filename = Path(file.filename).name
safe_filename = safe_filename.replace('/', '_').replace('\\', '_')
```

`Path(file.filename).name` su Windows estrae solo il nome base, ma su Linux `Path("../../etc/passwd").name` restituisce `passwd` — quindi la prima riga già risolve il problema. La seconda riga è ridondante ma innocua. Il vero rischio residuo è l'uso del filename nel percorso temporaneo: il file viene comunque cancellato dopo il parsing, quindi l'impatto è limitato. Buona pratica comunque usare un nome puramente basato su UUID:

```python
# Più sicuro: ignora completamente il filename originale per il path su disco
file_path = UPLOAD_DIR / f"{session_id}.fit"
```

---

### 1.3 Nessun rate limiting sull'upload

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

### 1.4 `eval`/`json.loads` su dati utente senza validazione schema

**File:** `webapp/routes/api.py` — `import_dashboard_modifications`

```python
async def import_dashboard_modifications(session_id: str, modifications: Dict[str, Any]):
```

Il corpo JSON viene accettato come `Dict[str, Any]` grezzo e poi i campi vengono acceduti direttamente:

```python
required_fields = ['session_id', 'efforts', 'deleted_efforts', 'deleted_sprints']
```

Non c'è validazione del tipo dei valori interni (es. `efforts` potrebbe essere una stringa invece di una lista). Se `modifications['efforts']` non è iterabile, il codice solleva un'eccezione non gestita che può esporre stack trace.

**Soluzione:** Usare un modello Pydantic esplicito con validazione dei tipi, come già fatto per altri endpoint (es. `MergeRequest`, `LocalModificationsRequest`).

---

### 1.5 `sys.path.insert` globale nei moduli route

**File:** Quasi tutti i file in `webapp/routes/`

```python
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))
```

Questa riga appare in ogni modulo route e viene eseguita a import time. Oltre ad essere un code smell, può causare problemi di import se il path viene aggiunto più volte o se ci sono moduli con lo stesso nome altrove nel `sys.path`. Peggio, su un server condiviso potrebbe esporre moduli non intenzionali.

**Soluzione:** Rimuovere queste righe da tutti i moduli. Il path dovrebbe essere configurato una volta sola in `app.py` o, meglio ancora, installare il pacchetto PEFFORT come dipendenza con `pip install -e .` in modo che sia importabile normalmente.

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

### 2.2 Indice `end_idx` fuori bounds in `calculate_effort_parameters`

**File:** `webapp/utils/map3d_core.py`

```python
s = max(0, s)
e = max(s, min(e, len(power_all)))
seg_power = power_all[s:e]
seg_alt_arr = alt_values[max(0, s):min(e, len(alt_values))]
```

`e` viene clampato a `len(power_all)`, ma gli array `alt_values` e `dist_km_values` potrebbero avere dimensioni diverse da `power_all`. Il clamp viene applicato separatamente con `len(alt_values)` — questo è corretto ma introduce asimmetria: `seg_power` e `seg_alt_arr` potrebbero avere lunghezze diverse, causando errori silenziosi nei calcoli successivi (es. `elevation_gain = seg_alt_arr[-1] - seg_alt_arr[0]` quando `seg_alt_arr` è più corto di `seg_power`).

**Soluzione:** Calcolare un `safe_e = min(e, len(power_all), len(alt_values), len(dist_km_values))` unico all'inizio della funzione.

---

### 2.3 Doppia assegnazione `stream_effort_start` in `altimetria_d3.py`

**File:** `webapp/routes/altimetria_d3.py`

```python
sprint_info = {
    ...
    # Track sprint position: ACTUAL times relative to buffer start (not indices)
    'stream_effort_start': 0.0,
    'stream_effort_end':   float(time_sec[end - 1] - time_sec[start]),
    'stream_effort_duration': int(duration),     # Actual sprint duration (not including buffer)
    # ... dopo alcune righe ...
    'stream_effort_start': 0.0,  # ← DUPLICATO
    'stream_effort_end':   float(time_sec[end - 1] - time_sec[start]),
}
```

La chiave `stream_effort_start` appare due volte nello stesso dict literal. Python non solleva errori (vince l'ultima), ma è un bug latente e rende il codice difficile da leggere.

---

### 2.4 `detect_sprints` — `time_sec` fuori bounds

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

### 2.5 `trim_segment` — finestra trim più grande dell'effort

**File:** `webapp/utils/effort_analyzer.py`

```python
if end - start < trim_win * 2:
    break
```

Il controllo è `trim_win * 2`, ma il codice successivo tenta di applicare `trim_win` sia a inizio che a fine. Se `end - start == trim_win * 2 + 1`, il trim potrebbe portare a `start >= end`. Meglio usare `trim_win * 2 + 1` come soglia minima, o aggiungere un check finale `if start >= end: return original_start, original_end`.

---

### 2.6 Sessioni: nessun cleanup periodico dei file temporanei

**File:** `webapp/routes/upload.py`

```python
UPLOAD_DIR = Path(tempfile.gettempdir()) / "peffort_uploads"
```

I file vengono cancellati subito dopo il parsing (`file_path.unlink()`), ma se il parsing solleva un'eccezione dopo la creazione del file, il blocco `except Exception` non pulisce il file:

```python
except Exception as e:
    logger.error(f"Error saving file: {e}")
    if file_path.exists():
        file_path.unlink()
    raise HTTPException(...)
```

In realtà questo blocco **fa** la pulizia — corretto. Ma il blocco di parsing sotto:

```python
try:
    df = parse_fit(str(file_path))
    if file_path.exists():
        file_path.unlink()
except Exception as e:
    if file_path.exists():
        file_path.unlink()
    raise HTTPException(...)
```

Anche questo è corretto. Il problema è solo che se il processo viene killato durante il parsing, il file rimane su disco a tempo indeterminato. Usare `try/finally` è più robusto:

```python
try:
    df = parse_fit(str(file_path))
finally:
    if file_path.exists():
        file_path.unlink()
```

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

### 3.5 `app.py` non usa `asynccontextmanager` per la pulizia delle sessioni

**File:** `webapp/app.py`

Il `lifespan` context manager è definito ma non fa pulizia delle sessioni scadute:

```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("PEFFORT Web app started")
    yield
    logger.info("PEFFORT Web app shut down")
```

`SessionStore.cleanup()` esiste ma non viene mai chiamato automaticamente. Le sessioni scadono solo quando si tenta di accedervi. Su un server con molti upload questo significa che la memoria non viene mai rilasciata proattivamente.

**Soluzione:** Aggiungere un task di background:

```python
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    async def cleanup_task():
        while True:
            await asyncio.sleep(3600)  # ogni ora
            sessions.cleanup()
    
    task = asyncio.create_task(cleanup_task())
    yield
    task.cancel()
```

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

### 4.4 Logging inconsistente

Alcuni moduli usano `logger.info`, altri `logger.warning`, altri ancora `print` (non trovati nel codice attuale ma la struttura è a rischio). Il livello di logging in `app.py` è `INFO` globale, che su produzione genererà troppo output. Considerare `WARNING` su produzione e `INFO` in sviluppo tramite variabile d'ambiente:

```python
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
```

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

### 4.7 `api.py` — funzione `import_modifications` non usata come endpoint

**File:** `webapp/routes/api.py`

La funzione `import_modifications` è definita e inclusa in `__all__`, ma nel router è registrata solo come `import_dashboard_modifications` su `/api/import-modifications/{session_id}`. Esiste anche `/{session_id}/import` ma con logica diversa. Il naming è confuso e il codice di `import_modifications` nell'`__all__` non corrisponde a nessuna route attiva.

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

### 5.1 `prepare_chart_data` — calcola tutto ad ogni request

**File:** `webapp/routes/altimetria_d3.py`

`prepare_chart_data` ricalcola kJ cumulativi, VAM, metriche HR, stream dati per ogni effort ad ogni richiesta della pagina altimetria. Per un file con 100 effort e 3 ore di dati, questo può richiedere secondi.

**Soluzione:** Calcolare e cachare i dati derivati nella sessione alla prima richiesta:

```python
if 'chart_data_cache' not in session:
    session['chart_data_cache'] = prepare_chart_data(session)
chart_data = session['chart_data_cache']
```

Invalidare la cache quando efforts/sprints vengono modificati (già gestito dalle API di modifica).

---

### 5.2 `map3d_generator.py` — ricalcola GeoJSON ad ogni richiesta

Stesso pattern: ogni visita alla mappa 3D ricalcola il GeoJSON, filtra le coordinate, calcola zoom e center. Questi dati non cambiano tra una request e l'altra (le coordinate GPS non cambiano). Cacheabili nella sessione.

---

### 5.3 JavaScript — `computePower5sProfile()` ricalcolato ad ogni selezione

**File:** `webapp/static/js/map3d.js`

```javascript
function computePower5sProfile() {
    if (power5sCache) return power5sCache;
    ...
}
```

Il caching è presente, ma la funzione `calculateTimeBasedMovingAverage` per il profilo 5s viene ricalcolata in O(n) ogni volta che viene chiamata `filterTraceByDistance`. Per file di 3+ ore (10000+ punti) questo è percettibile. Il cache `power5sCache` è a livello di variabile globale JS — corretto, ma viene perso se la pagina viene ricaricata.

---

### 5.4 `altimetria_d3.py` — `convert_to_python_types` su struttura enorme

```python
chart_data = convert_to_python_types(chart_data)
```

`convert_to_python_types` è ricorsiva e attraversa l'intera struttura dati (che include stream dati per ogni effort — potenzialmente milioni di punti). Sarebbe più efficiente convertire i tipi numpy alla fonte, durante la creazione dei dati, invece di fare una passata ricorsiva alla fine.

---

## 6. Frontend / JavaScript

### 6.1 `localStorage` usato per sincronizzare zone tra tab

**File:** `webapp/templates/inspection.html`, `altimetria_d3.html`, `map3d.js`

Le zone di intensità vengono salvate in `localStorage` nell'Inspection tab e lette negli altri tab. Questo è un pattern valido, ma:

1. Se l'utente apre due sessioni diverse in tab diversi, le zone dell'ultima sessione sovrascrivono quelle della precedente.
2. Non c'è versioning: se il formato delle zone cambia in futuro, i dati vecchi in localStorage potrebbero causare errori silenziosi.

**Soluzione minima:** Aggiungere un check di versione:

```javascript
const ZONES_VERSION = 'v2';
const stored = localStorage.getItem(`inspection_zones_${ZONES_VERSION}`);
```

---

### 6.2 BroadcastChannel non gestito su browser non supportati

**File:** Tutti i template con la riga:

```javascript
const effortUpdateChannel = new BroadcastChannel('peffort_{{ session_id }}');
```

BroadcastChannel non è supportato in Safari < 15.4 (e non funziona in iframes cross-origin). Aggiungere un fallback:

```javascript
let effortUpdateChannel = null;
try {
    effortUpdateChannel = new BroadcastChannel('peffort_{{ session_id }}');
    effortUpdateChannel.onmessage = (event) => { ... };
} catch (e) {
    console.warn('BroadcastChannel not supported');
}
```

---

### 6.3 `inspection.html` — slider avg30s ha range 1-60 ma la label dice "30s Avg"

```html
<input type="range" id="avg30sSeconds" value="30" min="1" max="60" step="1">
```

Il range va da 1 a 60 secondi, ma lo slider è etichettato "Chart 2 - Avg" senza contesto. Se l'utente imposta 1 secondo, sta praticamente vedendo il dato raw, il che è confondente. Aggiungere un tooltip o una label con il valore attuale.

---

### 6.4 Nessuna gestione errori nelle chiamate `fetch` del dashboard

**File:** `webapp/templates/dashboard.html`

```javascript
async function redetectEfforts() {
    ...
    const response = await fetch(`/api/${sessionId}/redetect-efforts`, { ... });
    const result = await response.json();
    if (result.success) {
        alert(`✅ Re-detected ${result.total_efforts} efforts!`);
        location.reload();
    } else {
        alert(`❌ Error: ${result.message}`);
    }
}
```

Se `fetch` fallisce per problemi di rete, la Promise viene rigettata e l'errore non viene catturato (nessun `try/catch` esterno). L'utente vedrà un errore nella console ma nessun feedback visivo.

---

### 6.5 `location.reload()` dopo ogni operazione API

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

### 7.2 `requirements.txt` non incluso nella review ma probabilmente mancante di dipendenze

**File:** `requirements.txt` (non allegato)

Non è possibile fare una review completa senza `requirements.txt`, ma basandosi sulle importazioni nel codice, le dipendenze dovrebbero includere:

```
fastapi
uvicorn[standard]
fitparse
pandas
numpy
jinja2
python-multipart  # per Form() in FastAPI
```

Assicurarsi che `python-multipart` sia presente — è necessario per il parsing dei form e viene spesso dimenticato.

---

### 7.3 Hardcoded host e porta in STARTUP.md

```markdown
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8001
```

Su Render, la porta viene passata come variabile d'ambiente `PORT`. Aggiungere istruzioni per Render:

```bash
uvicorn app:app --host 0.0.0.0 --port ${PORT:-8001}
```

---

### 7.4 Nessun `Procfile` o `render.yaml`

Per il deployment su Render, è consigliato avere un `render.yaml` nella root:

```yaml
services:
  - type: web
    name: peffort-web
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: cd webapp && uvicorn app:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: MAPTILER_API_KEY
        sync: false
```

---

## 8. Documentazione e README

### 8.1 README focalizzato su Windows, nessuna istruzione per Linux/Mac/Render

Il `README.md` e `STARTUP.md` sono scritti esclusivamente per Windows PowerShell. Per il deployment su Render (Linux) o per sviluppatori Mac, le istruzioni non sono applicabili.

**Aggiungere una sezione:**

```markdown
## Deployment su Render

1. Fork o push su GitHub
2. Crea un nuovo Web Service su render.com
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `cd webapp && uvicorn app:app --host 0.0.0.0 --port $PORT`
5. Environment Variables: `MAPTILER_API_KEY=<tua_chiave>`
```

---

### 8.2 `ROADMAP.md` — note non strutturate

`ROADMAP.md` contiene note informali in italiano miste a TODO tecnici. Non è leggibile da un collaboratore esterno e non ha priorità o stato.

---

### 8.3 Mancanza di docstring nelle funzioni frontend-facing

Le funzioni Python core (`parse_fit`, `create_efforts`, `merge_extend`) hanno docstring ragionevoli. Le funzioni dei route (`dashboard_view`, `upload_fit`) hanno solo commenti sommari. Le funzioni JS non hanno JSDoc.

---

## 9. Quick Wins — Modifiche a Basso Rischio

Queste modifiche sono sicure, rapide da implementare e migliorano subito la qualità:

| # | File | Modifica | Impatto |
|---|------|----------|---------|
| 1 | `effort_analyzer.py` | Rimuovere riga doppia `stream_effort_start` in `altimetria_d3.py` | Bug fix |
| 2 | `upload.py` | Sostituire i blocchi `try/except` con `try/finally` per la pulizia del file | Robustezza |
| 3 | `upload.py` | Usare `f"{session_id}.fit"` come path su disco invece di includere il filename utente | Sicurezza |
| 4 | `app.py` | Aggiungere il cleanup task periodico per le sessioni | Memoria |
| 5 | `map3d_generator.py` | Aggiungere commento esplicito "API key exposed in HTML — restrict by domain on MapTiler" | Awareness sicurezza |
| 6 | `api.py` | Loggare `sprint_detection_error` come warning se non None | Debug |
| 7 | Tutti i template | Aggiungere `try/catch` a `new BroadcastChannel(...)` | Compatibilità browser |
| 8 | `dashboard.html` | Aggiungere `try/catch` alle chiamate `fetch` nelle funzioni async | UX |
| 9 | `app.py` | Rendere il log level configurabile da env var | Ops |
| 10 | Root | Aggiungere `render.yaml` | Deployment |

---

## Riepilogo per Priorità

### Priorità Alta (prima del deployment)
1. **§1.1** — Chiave MapTiler visibile nel sorgente HTML → restringere per dominio su MapTiler dashboard
2. **§1.3** — Nessun rate limiting su `/upload` → aggiungere slowapi o nota nel README
3. **§2.3** — Chiave duplicata `stream_effort_start` → fix immediato
4. **§3.4** — Persistenza sessioni su Render → decidere strategia (disk, Redis, o accettare il rischio)
5. **§7.4** — Aggiungere `render.yaml` → necessario per deployment ordinato

### Priorità Media (refactoring successivo)
6. **§3.1** — Codice JS triplicato → estrarre `peffort_common.js`
7. **§3.2** — Global state nei router → migrare a FastAPI Depends
8. **§3.3** — Calcoli metriche duplicati → `utils/segment_metrics.py`
9. **§5.1** — Cache `prepare_chart_data` nella sessione
10. **§4.1/4.2** — Template JS troppo grandi → separare in file statici

### Priorità Bassa (miglioramento continuo)
11. **§4.8** — Aggiungere TypedDict per i return type delle funzioni core
12. **§6.1** — Versionare le zone in localStorage
13. **§8.1** — Aggiornare README con istruzioni Linux/Render
14. **§3.5** — Aggiungere cleanup task asincrono per le sessioni

---

*Review completata — aprile 2026*
