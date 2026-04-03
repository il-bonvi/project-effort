# PEFFORT Web — Code Review Completa

> **Data review:** Aprile 2026  
> **Codebase:** FastAPI + Jinja2 + D3.js / ECharts / MapLibre GL  

---

## Indice

1. [Architettura & Struttura](#1-architettura--struttura)
2. [Sicurezza](#2-sicurezza)
3. [Gestione Sessioni & Memoria](#3-gestione-sessioni--memoria)
4. [Qualità del Codice Python](#4-qualità-del-codice-python)
5. [Gestione Errori](#5-gestione-errori)
6. [Performance](#6-performance)
7. [Frontend / JavaScript](#7-frontend--javascript)
8. [Template / Jinja2](#8-template--jinja2)
9. [Deployment / Infrastruttura](#9-deployment--infrastruttura)
10. [Problemi Minori & Stile](#10-problemi-minori--stile)
11. [Riepilogo Priorità](#11-riepilogo-priorità)
12. [Refactoring Suggeriti](#12-refactoring-suggeriti)

---

## Legenda Severità

| Simbolo | Livello | Descrizione |
|---------|---------|-------------|
| 🔴 | **CRITICO** | Blocca il deployment o causa crash/perdita dati |
| 🟠 | **ALTO** | Impatto significativo su sicurezza, stabilità o manutenibilità |
| 🟡 | **MEDIO** | Problema reale ma con workaround disponibili |
| 🟢 | **BASSO** | Miglioramento qualitativo, non urgente |

---

## 1. Architettura & Struttura

### Punti di Forza

- Separazione chiara tra `routes/`, `utils/` e `templates/`
- Pattern `setup_XXX_router(sessions_dict)` per iniettare lo stato condiviso è coerente in tutta la codebase
- Separazione `map3d_core` / `map3d_generator` / `map3d_renderer` segue correttamente il principio di singola responsabilità
- Uso di Pydantic models per la validazione degli input negli endpoint API

### Problemi

#### 🟠 [ALTO] Stato globale mutabile via riferimenti di modulo

Ogni modulo route mantiene un proprio `_shared_sessions` come variabile globale di modulo, inizializzata con un dict vuoto e poi sostituita via `setup_XXX_router()`.

```python
# In routes/api.py, upload.py, map3d.py, inspection.py, ecc.
_shared_sessions: Dict[str, Any] = {}

def setup_api_router(sessions_dict: Dict[str, Any]) -> APIRouter:
    global _shared_sessions
    _shared_sessions = sessions_dict
    return router
```

**Problema:** Se un modulo viene importato prima della chiamata a `setup_XXX_router()`, o se l'ordine di inizializzazione cambia, il riferimento punta ancora al dict vuoto. Il pattern è funzionante ma fragile e difficile da testare.

**Soluzione raccomandata:** un modulo `sessions.py` dedicato come fonte unica di verità.

```python
# webapp/sessions.py  (nuovo file)
from typing import Dict, Any

_store: Dict[str, Any] = {}

def get_store() -> Dict[str, Any]:
    return _store

def get_session(session_id: str) -> Dict[str, Any] | None:
    return _store.get(session_id)

def set_session(session_id: str, data: Dict[str, Any]) -> None:
    _store[session_id] = data

def delete_session(session_id: str) -> bool:
    return _store.pop(session_id, None) is not None
```

Tutti i moduli importano da `sessions.py` invece di ricevere il dict come parametro.

---

#### 🟡 [MEDIO] `@app.on_event` deprecato in FastAPI >= 0.93

```python
# webapp/app.py
@app.on_event("startup")
async def startup_event():
    logger.info("PEFFORT Web app started on http://localhost:8001")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("PEFFORT Web app shut down")
```

**Soluzione:** usare il nuovo pattern `lifespan`:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    logger.info("PEFFORT Web app started")
    yield
    # shutdown
    logger.info("PEFFORT Web app shut down")

app = FastAPI(
    title="PEFFORT Web",
    lifespan=lifespan,
    ...
)
```

---

#### 🟢 [BASSO] Import duplicati del `_project_root` in quasi ogni route

```python
# Ripetuto identicamente in routes/api.py, upload.py, map3d.py, inspection.py, map2d.py
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))
```

Questo blocco è copiato in 5+ file. Centralizzare in `webapp/__init__.py` o in un modulo `webapp/compat.py` eseguito una sola volta.

---

## 2. Sicurezza

### 🔴 [CRITICO] Session ID troppo corto — collisioni e brute-force

```python
# webapp/routes/upload.py
session_id = str(uuid.uuid4())[:8]   # solo 8 caratteri hex
```

**Problemi:**
1. Spazio di 16^8 ≈ 4.3 miliardi — con il birthday paradox, la probabilità di collisione diventa non trascurabile dopo ~65k sessioni
2. Un attaccante può enumerare sessioni con ~4 miliardi di richieste (realistico con automazione)
3. Qualsiasi session_id a 8 char è indovinabile con attacchi mirati

**Soluzione:**
```python
session_id = str(uuid.uuid4())          # UUID completo: 32 caratteri hex
# oppure
import secrets
session_id = secrets.token_urlsafe(24)  # 32 caratteri URL-safe, 192 bit di entropia
```

---

### 🟠 [ALTO] Nessuna autenticazione né rate limiting

L'app è esposta publicamente su Render senza alcuna forma di autenticazione. Chiunque raggiunga l'URL può:
- Uploadare file FIT arbitrari (consumando memoria e CPU)
- Accedere a sessioni altrui se conosce il session_id
- Enumerare sessioni attive via `/api/{session_id}/status`
- Abusare degli endpoint di re-detection per attacchi DoS

**Soluzioni per uso personale (in ordine di semplicità):**

```python
# Opzione 1: HTTP Basic Auth via middleware
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets, os

security = HTTPBasic()

def require_auth(credentials: HTTPBasicCredentials = Depends(security)):
    correct_user = secrets.compare_digest(
        credentials.username, os.environ.get("APP_USER", "admin")
    )
    correct_pass = secrets.compare_digest(
        credentials.password, os.environ.get("APP_PASSWORD", "")
    )
    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Basic"},
        )

# Applicare come dipendenza globale in app.py
app = FastAPI(dependencies=[Depends(require_auth)])
```

```python
# Opzione 2: slowapi per rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@router.post("/upload")
@limiter.limit("10/hour")
async def upload_fit(request: Request, ...):
    ...
```

---

### 🟠 [ALTO] XSS potenziale nel report HTML esportato

```python
# webapp/routes/api.py - export_html_report
filename_escaped = html_module.escape(filename)
# ...
html = html.replace('{{ filename }}', filename_escaped)         # ✓ escaped
html = html.replace('{{ chart_data_json | safe }}', chart_data_json)  # ⚠ non escaped
```

`chart_data_json` contiene dati utente (filename, label degli effort, ecc.). Se un filename contiene `</script><script>alert(document.cookie)</script>`, il report HTML esportato è vulnerabile a XSS stored quando aperto nel browser.

**Soluzione:**
```python
import json

# Sanitizzare le stringhe pericolose in chart_data_json
# oppure iniettare come testo dentro un tag application/json (già fatto nel template live)
safe_chart_data = chart_data_json.replace('</script>', '<\\/script>')
html = html.replace('{{ chart_data_json | safe }}', safe_chart_data)
```

---

### 🔴 [CRITICO] `config.py` importato direttamente — rompe il deployment

```python
# webapp/utils/map3d_generator.py
from config import get_maptiler_key
```

`config.py` è in `.gitignore` e non esiste su Render. L'import avviene **al caricamento del modulo**, non all'uso della funzione. Questo significa che l'intera applicazione non parte se `config.py` non esiste, anche se la mappa 3D non viene mai richiesta.

**Soluzione completa per deployment:**

```python
# webapp/utils/map3d_generator.py
import os

def _get_maptiler_key() -> str:
    """Legge la API key da env var (deployment) o config.py (locale)."""
    # Prima prova la variabile d'ambiente (Render, produzione)
    key = os.environ.get("MAPTILER_API_KEY", "")
    if key:
        return key
    # Fallback a config.py locale (sviluppo)
    try:
        from config import get_maptiler_key
        return get_maptiler_key()
    except ImportError:
        logger.warning(
            "MAPTILER_API_KEY non trovata. "
            "Impostare la variabile d'ambiente o creare config.py."
        )
        return ""
```

**Su Render:** aggiungere `MAPTILER_API_KEY` come Environment Variable nel dashboard.

---

### 🟡 [MEDIO] Nessuna protezione CSRF

Gli endpoint POST (es. `/api/{session_id}/apply-local-modifications`) non hanno protezione CSRF. Per un'app monoutente accessibile solo da browser di fiducia, il rischio è basso, ma vale la pena documentarlo esplicitamente.

---

### 🟡 [MEDIO] `| safe` su dati utente nei template Jinja2

```html
<!-- webapp/templates/inspection.html -->
const timeAxis = {{ time_axis_json | safe }};
const effortsData = {{ efforts_data_json | safe }};
```

I dati sono serializzati in Python come JSON prima di essere passati al template, quindi il rischio concreto è basso. Tuttavia il pattern corretto con Jinja2 è:

```python
# In inspection.py - passare oggetti Python, non stringhe JSON pre-serializzate
context = {
    'time_axis': time_axis,       # lista Python, non stringa JSON
    'efforts_data': efforts_data, # lista Python
}
```

```html
<!-- Nel template, usare il filtro tojson che gestisce l'escaping correttamente -->
const timeAxis = {{ time_axis | tojson }};
const effortsData = {{ efforts_data | tojson }};
```

Il filtro `tojson` di Jinja2 gestisce automaticamente l'escaping di `</script>`, `<!--`, ecc.

---

## 3. Gestione Sessioni & Memoria

### 🔴 [CRITICO] Memory leak — sessioni mai rimosse

```python
# webapp/app.py
sessions: Dict[str, Dict[str, Any]] = {}
# Non esiste nessuna logica di cleanup, TTL, o limite massimo
```

Ogni upload aggiunge al dict una sessione contenente l'intero DataFrame pandas (potenzialmente 50-100MB per file FIT grandi). Con N upload nel tempo, la memoria cresce senza limiti fino a OOM crash. Su Render free tier la memoria disponibile è ~512MB.

**Soluzione con TTL e LRU:**

```python
# webapp/sessions.py
import time
from collections import OrderedDict
from threading import Lock
from typing import Dict, Any, Optional

class SessionStore:
    def __init__(self, max_sessions: int = 20, ttl_seconds: int = 86400):
        self._store: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._timestamps: Dict[str, float] = {}
        self._max = max_sessions
        self._ttl = ttl_seconds
        self._lock = Lock()

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._evict_expired()
            session = self._store.get(session_id)
            if session:
                # Aggiorna timestamp (LRU touch)
                self._store.move_to_end(session_id)
                self._timestamps[session_id] = time.time()
            return session

    def set(self, session_id: str, data: Dict[str, Any]) -> None:
        with self._lock:
            self._evict_expired()
            # Se supera il limite, rimuovi la più vecchia
            if len(self._store) >= self._max and session_id not in self._store:
                oldest_id, _ = next(iter(self._store.items()))
                self._remove(oldest_id)
            self._store[session_id] = data
            self._timestamps[session_id] = time.time()

    def _remove(self, session_id: str) -> None:
        self._store.pop(session_id, None)
        self._timestamps.pop(session_id, None)

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [
            sid for sid, ts in self._timestamps.items()
            if now - ts > self._ttl
        ]
        for sid in expired:
            self._remove(sid)
            import logging
            logging.getLogger(__name__).info(f"Sessione {sid} scaduta e rimossa")

    def __contains__(self, session_id: str) -> bool:
        return self.get(session_id) is not None

    def __len__(self) -> int:
        return len(self._store)

# Singleton globale
store = SessionStore(max_sessions=20, ttl_seconds=86400)
```

---

### 🟠 [ALTO] Sessions non thread-safe in modalità multi-worker

```python
sessions: Dict[str, Dict[str, Any]] = {}
```

FastAPI con uvicorn in modalità default (singolo processo) non ha problemi di race condition. Ma con `--workers N` (multi-processo), ogni worker ha il suo `sessions` dict indipendente — le sessioni non sono condivise tra worker. Un upload sul worker 1 non è accessibile dal worker 2.

**Per Render free tier (single process) è accettabile**, ma va documentato esplicitamente nel `STARTUP.md` e `README.md`:

```markdown
## Note Deployment Multi-Worker

L'app usa sessioni in-memory. Con più worker (`--workers N`), le sessioni 
non sono condivise tra processi. Per deployment multi-worker, usare Redis 
come session store o limitare a `--workers 1`.
```

---

### 🟡 [MEDIO] Nessun endpoint per cancellare manualmente una sessione

Un utente non può liberare memoria dopo aver finito di analizzare un file. Aggiungere:

```python
# routes/api.py
@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """Rimuove una sessione e libera la memoria associata."""
    if session_id not in _shared_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    del _shared_sessions[session_id]
    return {"status": "deleted", "session_id": session_id}
```

---

## 4. Qualità del Codice Python

### 🟡 [MEDIO] `split_included` ha complessità O(n³) nel caso peggiore

```python
# webapp/utils/effort_analyzer.py
def split_included(df, efforts):
    changed = True
    while changed:                           # O(n) iterazioni worst case
        changed = False
        current_efforts = list(sorted_efforts)
        for i in range(len(current_efforts)):         # O(n)
            for j in range(len(current_efforts)):     # O(n)
                if i == j: continue
                # Verifica se j è contenuto in i...
```

Per dataset normali (10-30 efforts) non è un problema. Con parametri aggressivi (finestra piccola, tanti effort) può diventare lento.

**Ottimizzazione:** ordinare per start_idx e usare un approccio a sweep line O(n log n):

```python
def split_included(df: pd.DataFrame, efforts: List[Tuple]) -> List[Tuple]:
    power = df["power"].values
    efforts = sorted(efforts, key=lambda x: x[0])
    changed = True
    
    while changed:
        changed = False
        result = []
        i = 0
        while i < len(efforts):
            outer = efforts[i]
            s_out, e_out, _ = outer
            
            # Cerca il primo effort completamente contenuto in outer
            contained_idx = None
            for j in range(i + 1, len(efforts)):
                s_in, e_in, avg_in = efforts[j]
                if s_in >= e_out:
                    break  # non ci sono più candidati (lista ordinata)
                if s_in > s_out and e_in < e_out:
                    contained_idx = j
                    break
            
            if contained_idx is not None:
                s_in, e_in, avg_in = efforts[contained_idx]
                # Dividi outer attorno a inner
                if s_in > s_out:
                    seg = power[s_out:s_in]
                    if len(seg): result.append((s_out, s_in, seg.mean()))
                result.append((s_in, e_in, avg_in))
                if e_in < e_out:
                    seg = power[e_in:e_out]
                    if len(seg): result.append((e_in, e_out, seg.mean()))
                result.extend(efforts[i+1:contained_idx])
                result.extend(efforts[contained_idx+1:])
                efforts = sorted(result, key=lambda x: x[0])
                changed = True
                break
            else:
                result.append(outer)
                i += 1
        
        if not changed:
            efforts = result
    
    return efforts
```

---

### 🟡 [MEDIO] `merge_extend` potenzialmente non terminante

```python
# webapp/utils/effort_analyzer.py
def merge_extend(df, efforts, ...):
    changed = True
    while changed:      # ← nessun limite di iterazioni
        changed = False
        # ...
```

A differenza di `trim_segment` (che ha `max_iterations=100`), `merge_extend` non ha protezione. Con dati patologici potrebbe eseguire molte iterazioni.

**Soluzione:**
```python
MAX_ITERATIONS = 100
iteration = 0
while changed and iteration < MAX_ITERATIONS:
    changed = False
    iteration += 1
    # ...

if iteration >= MAX_ITERATIONS:
    logger.warning(f"merge_extend ha raggiunto il limite di {MAX_ITERATIONS} iterazioni")
```

---

### 🟡 [MEDIO] Conversione semicircles→degrees tecnicamente imprecisa

```python
# webapp/utils/effort_analyzer.py
SEMICIRCLES_TO_DEGREES = 180 / (2**31 - 1)
```

Il protocollo FIT specifica la conversione come `180 / 2^31` (non `2^31 - 1`). La differenza è ~0.046 nanodegrees (irrilevante in pratica) ma tecnicamente errata.

```python
SEMICIRCLES_TO_DEGREES = 180 / (2**31)  # Corretto per protocollo FIT
```

---

### 🟡 [MEDIO] DataFrame mutato in-place senza copia difensiva

```python
# webapp/utils/effort_analyzer.py - parse_fit()
df["power"] = pd.to_numeric(df["power"], errors='coerce').fillna(0).astype(int)
df["heartrate"] = pd.to_numeric(df["heartrate"], errors='coerce').fillna(0).astype(int)
# ecc...
```

Il DataFrame originale viene modificato. Se lo stesso oggetto viene riutilizzato (ora non accade, ma in futuro potrebbe), le modifiche sono permanenti e inattese.

**Soluzione:** aggiungere `df = df.copy()` subito dopo la creazione del DataFrame da `pd.DataFrame(data)`.

---

### 🟢 [BASSO] Type hints incompleti e inconsistenti

```python
# Alcune funzioni hanno type hints completi:
def parse_fit(file_path: str) -> pd.DataFrame:  # ✓
def get_zone_color(avg_power: float, cp: float) -> str:  # ✓

# Altre no:
def trim_segment(power, start, end, trim_win, trim_pct, max_iterations=100):  # ✗
def create_efforts(df, cp, window_sec=60, merge_pct=15, ...):  # ✗ (parziale)
```

Completare i type hints migliora la leggibilità, l'IDE support e la rilevazione di bug a compile-time.

---

### 🟢 [BASSO] Costanti magiche sparse nel codice

```python
# webapp/utils/effort_analyzer.py
WINDOW_SECONDS = 60          # definita ma mai usata direttamente
MERGE_POWER_DIFF_PERCENT = 15
# ecc...

# webapp/routes/altimetria_d3.py
buffer_seconds = 120  # magic number, compare in 4+ posti
```

Centralizzare tutte le costanti in un file `webapp/constants.py`.

---

## 5. Gestione Errori

### 🟡 [MEDIO] Fallback silenzioso per sprint detection

```python
# webapp/routes/upload.py
try:
    sprints = detect_sprints(...)
    logger.info(f"Detected {len(sprints)} sprints")
except Exception as e:
    logger.warning(f"Sprint detection failed: {e}")
    sprints = []   # ← fallback silenzioso, utente non informato
```

L'utente vede il dashboard senza sprint e non sa perché. Almeno includere un flag nella sessione:

```python
except Exception as e:
    logger.warning(f"Sprint detection failed: {e}")
    sprints = []
    sprint_detection_error = str(e)  # Mostrare nell'UI
```

---

### 🟡 [MEDIO] Endpoint `trim` usa parametri query su endpoint POST

```python
# webapp/routes/api.py
@router.post("/{session_id}/trim")
async def trim_effort(
    session_id: str, 
    effort_idx: int,        # ← query parameter su POST
    trim_start_sec: int = 0, 
    trim_end_sec: int = 0
):
```

Gli altri endpoint POST (merge, extend, split) usano correttamente Pydantic body models. Questo è inconsistente.

**Soluzione:**
```python
class TrimRequest(BaseModel):
    effort_idx: int
    trim_start_sec: int = 0
    trim_end_sec: int = 0

@router.post("/{session_id}/trim")
async def trim_effort(session_id: str, request: TrimRequest):
    ...
```

---

### 🟡 [MEDIO] Pattern `except Exception` ripetuto ~15 volte

```python
# Pattern ripetuto in quasi ogni endpoint
except Exception as e:
    logger.error(f"Error ...: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail=str(e))
```

Questo è accettabile come catch-all finale, ma andrebbe preceduto da handler specifici per errori prevedibili:

```python
except KeyError as e:
    raise HTTPException(status_code=400, detail=f"Colonna mancante nel DataFrame: {e}")
except ValueError as e:
    raise HTTPException(status_code=400, detail=f"Dati non validi: {e}")
except MemoryError:
    raise HTTPException(status_code=507, detail="Memoria insufficiente per elaborare il file")
except Exception as e:
    logger.error(f"Errore imprevisto: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail="Errore interno del server")
```

---

### 🟢 [BASSO] `str(e)` espone dettagli interni all'utente

```python
raise HTTPException(status_code=500, detail=str(e))
```

In produzione, esporre i dettagli delle eccezioni Python può rivelare path del filesystem, nomi di variabili, struttura del codice. Considerare messaggi di errore più generici per gli errori 500, con logging completo solo server-side.

---

## 6. Performance

### 🟠 [ALTO] `calculateTimeBasedMovingAverage` è O(n²) in JavaScript

```javascript
// Presente identicamente in map3d.js, altimetria_d3.html, map2d.html
function calculateTimeBasedMovingAverage(powerData, timeData, windowSeconds) {
    const result = [];
    for (let i = 0; i < timeData.length; i++) {
        const c = timeData[i], lo = c - windowSeconds/2, hi = c + windowSeconds/2;
        let sum = 0, cnt = 0;
        for (let j = 0; j < timeData.length; j++) {   // ← scorre TUTTO l'array ogni volta
            if (timeData[j] >= lo && timeData[j] <= hi) { sum += data[j]; cnt++; }
        }
        result.push(cnt ? sum/cnt : powerData[i]);
    }
    return result;
}
```

Con un file FIT di 1 ora a 1Hz = 3600 campioni: 3600 × 3600 = **~13 milioni di iterazioni**.  
Con file ad alta frequenza (es. 4Hz) = ~200 milioni di iterazioni → il browser si congela.

**Soluzione O(n) con sliding window:**

```javascript
function calculateTimeBasedMovingAverage(data, timeData, windowSeconds) {
    if (!data.length) return [];
    const result = new Array(data.length);
    let lo = 0, hi = 0, sum = 0, cnt = 0;

    for (let i = 0; i < data.length; i++) {
        const center = timeData[i];
        const winLo = center - windowSeconds / 2;
        const winHi = center + windowSeconds / 2;

        // Espandi finestra a destra
        while (hi < data.length && timeData[hi] <= winHi) {
            sum += data[hi];
            cnt++;
            hi++;
        }
        // Contrai finestra a sinistra
        while (lo < hi && timeData[lo] < winLo) {
            sum -= data[lo];
            cnt--;
            lo++;
        }

        result[i] = cnt > 0 ? sum / cnt : data[i];
    }
    return result;
}
```

**Speedup atteso:** da O(n²) a O(n) — ~3600× più veloce per file da 1 ora.

---

### 🟡 [MEDIO] Stream data serializzata integralmente nel JSON iniziale

```python
# webapp/routes/altimetria_d3.py - per OGNI effort e sprint
effort_info = {
    # ...
    'time_stream': time_stream,       # ~360+ float (120s buffer × 3Hz)
    'power_stream': power_stream,     # ~360+ float
    'hr_stream': hr_stream,           # ~360+ float
    'wkg_stream': wkg_stream,         # ~360+ float
    'cadence_stream': cadence_stream, # ~360+ float
    'torque_stream': torque_stream,   # ~360+ float
    'speed_stream': speed_stream,     # ~360+ float
}
```

Con 20 effort × 7 stream × 360 punti = **~50.000 float** solo per i dati stream, che vengono scaricati anche se l'utente non apre mai il modal "📊 Stream".

**Soluzione: lazy loading degli stream**

```python
# Nell'endpoint principale, escludere i stream
effort_info = {
    'id': orig_idx,
    'rank': rank_idx + 1,
    'line_data': line_data,
    'avg_power': ...,
    # NON includere time_stream, power_stream, ecc.
}

# Nuovo endpoint dedicato per recuperare gli stream on demand
@router.get("/{session_id}/effort/{effort_id}/stream")
async def get_effort_stream(session_id: str, effort_id: int):
    """Carica i dati stream solo quando richiesti (click su 📊 Stream)."""
    # ... calcola e restituisce solo i dati stream
```

```javascript
// Nel frontend, caricare on demand
async function openStreamModal(elemId, dataId, type) {
    // Se i dati stream non sono già caricati, fetchali
    const data = type === 'effort'
        ? chartData.efforts.find(e => e.id == dataId)
        : chartData.sprints.find(s => s.id == dataId);
    
    if (!data.time_stream) {
        const response = await fetch(`/api/${sessionId}/${type}/${dataId}/stream`);
        Object.assign(data, await response.json());
    }
    // ... apri modal
}
```

---

### 🟡 [MEDIO] `computePower5sProfile()` ricalcolata per ogni drag sull'altimetria

```javascript
// map3d.js e map2d.html
let power5sCache = null;

function computePower5sProfile() {
    if (power5sCache) return power5sCache;
    // ... calcolo O(n²) con calculateTimeBasedMovingAverage
    power5sCache = ...;
    return power5sCache;
}
```

La cache funziona, ma il calcolo iniziale (al primo drag) può essere lento per la stessa ragione O(n²) di cui sopra. Con la sliding window O(n) proposta, questo diventa irrilevante.

---

### 🟢 [BASSO] `drawFullElevationChart()` viene richiamata ad ogni pixel durante il resize

```javascript
// map3d.js e map2d.html
document.addEventListener('mousemove', (e) => {
    if (!isResizing) return;
    // ...
    drawFullElevationChart();  // ← ricostruisce tutto il SVG D3 ad ogni mousemove
    if (map) setTimeout(() => map.resize(), 0);
});
```

Durante il drag del resize handle, `drawFullElevationChart()` viene chiamata decine di volte al secondo, ricostruendo l'intero SVG. Usare un debounce/throttle:

```javascript
const debouncedDraw = debounce(drawFullElevationChart, 50);

document.addEventListener('mousemove', (e) => {
    if (!isResizing) return;
    const newH = Math.max(100, Math.min(400, window.innerHeight - e.clientY));
    elevationChart.style.height = newH + 'px';
    mapDiv.style.bottom = newH + 'px';
    debouncedDraw();
    if (map) setTimeout(() => map.resize(), 0);
});
```

---

## 7. Frontend / JavaScript

### 🔴 [CRITICO] Logica massivamente duplicata tra file JS/HTML

Le seguenti funzioni sono **copiate letteralmente** tra `map3d.js`, `altimetria_d3.html` e `map2d.html`:

| Funzione | Righe | Copie |
|----------|-------|-------|
| `buildStreamChartsD3()` | ~300 | 2 |
| `buildSprintStreamCharts()` | ~200 | 2 |
| `openStreamModal()` / `closeStreamModal()` | ~30 | 2 |
| `calculateTimeBasedMovingAverage()` | ~15 | 3 |
| `getIntensityZones()` | ~15 | 3 |
| Stream modal HTML | ~40 | 2 |
| Logica altimetria D3 | ~200 | 2 |

**Totale stimato:** ~800 righe di codice duplicato. Una modifica all'uno non si riflette negli altri.

**Soluzione:** estrarre in file statici dedicati:

```
webapp/static/js/
├── stream_modal.js      ← modal stream, openStreamModal, buildStreamChartsD3
├── altimetry_chart.js   ← drawFullElevationChart, selezione, metriche
├── intensity_zones.js   ← getIntensityZones, zoneColorForPower
└── utils.js             ← fmtDur, format_time_mmss, calculateTimeBasedMovingAverage
```

```html
<!-- map3d.html, map2d.html, altimetria_d3.html -->
<script src='/static/js/utils.js'></script>
<script src='/static/js/intensity_zones.js'></script>
<script src='/static/js/altimetry_chart.js'></script>
<script src='/static/js/stream_modal.js'></script>
```

---

### 🟠 [ALTO] `localStorage` come canale di comunicazione inter-tab

```javascript
// webapp/templates/inspection.html
localStorage.setItem(`effort_update_signal_${sessionId}`, Date.now().toString());

// webapp/templates/altimetria_d3.html, map3d.js
window.addEventListener('storage', function(event) {
    if (event.key === updateSignalKey) { location.reload(); }
});
```

**Problemi:**
1. Un full page reload ricarica l'intera pagina, inclusi tutti i dati stream
2. Se la sessione scade tra il salvataggio e il reload, l'utente vede un errore 404
3. Non funziona se i tab sono su origini diverse (es. http vs https)

**Soluzione migliore:** BroadcastChannel API (supportato da tutti i browser moderni):

```javascript
// inspection.html - dopo aver salvato
const channel = new BroadcastChannel(`peffort_${sessionId}`);
channel.postMessage({ type: 'efforts_updated' });
channel.close();

// altimetria_d3.html, map3d.html
const channel = new BroadcastChannel(`peffort_${sessionId}`);
channel.onmessage = (event) => {
    if (event.data.type === 'efforts_updated') {
        // Aggiornamento selettivo invece di full reload
        fetchAndUpdateEfforts();
    }
};
```

---

### 🟡 [MEDIO] Event handler `onclick` inline nei template

```html
<!-- webapp/templates/map3d.html -->
<button class='control-btn' id='toggleEfforts' onclick='toggleEfforts()'>👊 Efforts: ON</button>
<button class='control-btn' id='toggleSprints' onclick='toggleSprints()'>🏃 Sprints: ON</button>
<button class='control-btn' onclick='resetView()'>🎯 Reset View</button>
```

Handler inline:
- Violano la Content Security Policy (se mai aggiunta)
- Rendono il testing unitario impossibile
- Dipendono da funzioni globali (`window.toggleEfforts`)

**Soluzione:**
```html
<button class='control-btn' id='toggleEfforts'>👊 Efforts: ON</button>
```
```javascript
document.getElementById('toggleEfforts').addEventListener('click', toggleEfforts);
```

---

### 🟡 [MEDIO] `let` invece di `const` per dati immutabili

```javascript
// webapp/templates/map3d.html
let efforts_data_json = {{ efforts_data_json | safe }};   // ← dovrebbe essere const
const chart_data_json = {{ chart_data_json | safe }};     // ← corretto
```

`efforts_data_json` non viene mai riassegnato (viene letto e passato a `currentEfforts`). Usare `const` per tutti i dati iniettati dal server.

---

### 🟢 [BASSO] Funzione vuota dead code

```javascript
// webapp/templates/altimetria_d3.html
// ── Legacy single chart (unused but kept for safety) ──────────────────────
function buildD3Chart() {}
```

Questa funzione è vuota e non viene mai chiamata. Rimuovere.

---

### 🟢 [BASSO] `avg30sSeconds` / `avg60sSeconds` duplicate tra inspection e stream modal

```javascript
// In inspection.html (slider avanzamento media)
let avg30sSeconds = 30;
let avg60sSeconds = 60;

// In altimetria_d3.html e map3d.js (stream modal)
let avg30sSeconds = 30;
let avg60sSeconds = 60;
```

I valori vengono sincronizzati via `localStorage` (`stream_avg30s`, `stream_avg60s`), il che funziona. Ma sarebbe più pulito avere un unico punto di lettura/scrittura.

---

## 8. Template / Jinja2

### 🟡 [MEDIO] `{% raw %}` block che ingloba centinaia di righe JS

```html
<!-- webapp/templates/altimetria_d3.html -->
{% raw %}
<script>
// ~800 righe di JavaScript D3 con sintassi {{ }} per template literals
// ...
</script>
{% endraw %}
```

L'intera sezione JS è dentro `{% raw %}` per evitare conflitti con Jinja2. Questo rende impossibile iniettare variabili server-side direttamente nel codice JS (soluzione workaround: `<script type="application/json">` separato).

Il problema emerge nell'export HTML dove si usano string replace:
```python
html = html.replace('{% raw %}', '').replace('{% endraw %}', '')
```

**Soluzione a lungo termine:** spostare tutto il JavaScript in file `.js` statici (già raccomandato sopra), rendendo il template un semplice contenitore di dati.

---

### 🟡 [MEDIO] String replace fragile per l'export HTML

```python
# webapp/routes/api.py - export_html_report
html = html.replace('{{ filename }}', filename_escaped)
html = html.replace('{{ chart_data_json | safe }}', chart_data_json)
html = html.replace(
    """function getIntensityZones() {
    const stored = localStorage.getItem('inspection_zones');
    ...""",  # ← 10 righe di codice JS cercate letteralmente
    """function getIntensityZones() {
    return chartData.intensity_zones;
}"""
)
```

Questo approccio è estremamente fragile: se il template cambia anche di un solo spazio o newline, il replace non trova il match e il report esportato è broken silenziosamente.

**Soluzione:** usare placeholder espliciti nel template:

```html
<!-- In altimetria_d3.html -->
<script id="export-overrides">
// EXPORT_ZONES_OVERRIDE_PLACEHOLDER
function getIntensityZones() {
    const stored = localStorage.getItem('inspection_zones');
    // ...
}
</script>
```

```python
# In api.py
html = html.replace(
    '// EXPORT_ZONES_OVERRIDE_PLACEHOLDER',
    '// Zones locked at export time — localStorage not available'
)
```

---

### 🟢 [BASSO] Versioning dei file statici tramite query string

```html
<!-- webapp/templates/map3d.html -->
<link href='/static/css/map3d.css?v=202603294' rel='stylesheet' />
<script src='/static/js/map3d.js?v=2026040301'></script>
```

Il versioning manuale tramite query string funziona, ma va aggiornato a mano ad ogni modifica. Considerare cache busting automatico:

```python
# In app.py
import hashlib
from pathlib import Path

def file_hash(path: str) -> str:
    return hashlib.md5(Path(path).read_bytes()).hexdigest()[:8]

# Passare come variabile al template
context['css_version'] = file_hash('webapp/static/css/map3d.css')
```

---

## 9. Deployment / Infrastruttura

### 🔴 [CRITICO] `config.py` assente su Render rompe l'intera applicazione

Come dettagliato nella sezione Sicurezza, l'import di `config.py` avviene a livello di modulo in `map3d_generator.py`. Se il file non esiste, **tutta l'applicazione non parte** — non solo la funzionalità mappa 3D.

**Piano di migrazione completo:**

1. Creare `webapp/config_manager.py`:
```python
import os
import logging

logger = logging.getLogger(__name__)

def get_maptiler_key() -> str:
    # 1. Variabile d'ambiente (produzione/Render)
    key = os.environ.get("MAPTILER_API_KEY", "")
    if key:
        return key
    
    # 2. File config.py locale (sviluppo)
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from config import get_maptiler_key as _get_key
        return _get_key()
    except ImportError:
        pass
    
    logger.warning(
        "MapTiler API key non trovata. "
        "La mappa 3D mostrerà un messaggio di errore. "
        "Configurare MAPTILER_API_KEY come env var."
    )
    return ""
```

2. In `map3d_generator.py`, sostituire l'import diretto:
```python
from .config_manager import get_maptiler_key
```

3. Su Render, aggiungere Environment Variable: `MAPTILER_API_KEY=<chiave>`

4. Gestire gracefully il caso di chiave assente nel template map3d:
```javascript
// map3d.html
const maptiler_key = '{{ maptiler_key }}';
if (!maptiler_key) {
    document.getElementById('map').innerHTML = 
        '<div style="...">⚠️ MapTiler API key non configurata</div>';
}
```

---

### 🟠 [ALTO] Nessun `health check` endpoint

Render e altri PaaS richiedono un endpoint di health check per il monitoring:

```python
# webapp/app.py
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "sessions_active": len(sessions),
        "version": "1.0.0"
    }

@app.get("/ready")
async def ready():
    """Readiness check — verifica che l'app sia pronta a ricevere traffico."""
    return {"status": "ready"}
```

---

### 🟡 [MEDIO] Nessun `requirements.txt` nel repository (o non aggiornato)

Il file è referenziato in `README.md` e `STARTUP.md` ma non è incluso nel commit analizzato. Se non è aggiornato, l'installazione su un nuovo ambiente fallirà con `ModuleNotFoundError`.

**Generare requirements.txt aggiornato:**
```bash
# Con pip
pip freeze > requirements.txt

# Oppure con pip-tools (più pulito, separa dipendenze dirette da transitive)
pip install pip-tools
pip-compile pyproject.toml   # se si usa pyproject.toml
```

**Dipendenze minime attese:**
```
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
python-multipart
jinja2
fitparse
pandas
numpy
scipy  # se usato
```

---

### 🟢 [BASSO] `UPLOAD_DIR` non necessaria — il file viene subito eliminato

```python
# webapp/routes/upload.py
UPLOAD_DIR = Path(tempfile.gettempdir()) / "peffort_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
```

Il file viene salvato su disco e poi immediatamente eliminato dopo il parsing:
```python
df = parse_fit(str(file_path))
if file_path.exists():
    file_path.unlink()  # ← eliminato subito
```

Si potrebbe evitare la scrittura su disco usando `SpooledTemporaryFile` direttamente:

```python
import tempfile

# Invece di scrivere in UPLOAD_DIR:
with tempfile.NamedTemporaryFile(suffix='.fit', delete=True) as tmp:
    content = await file.read()
    tmp.write(content)
    tmp.flush()
    df = parse_fit(tmp.name)
```

---

## 10. Problemi Minori & Stile

### 🟡 [MEDIO] Timestamp hardcoded nell'export JSON

```python
# webapp/routes/api.py - export_modifications
data = {
    'session_id': session_id,
    'efforts': efforts_modifications,
    'timestamp': '2026-02-10T00:00:00.000Z',  # ← placeholder dimenticato
    ...
}
```

**Fix immediato:**
```python
from datetime import datetime, timezone
'timestamp': datetime.now(timezone.utc).isoformat(),
```

---

### 🟢 [BASSO] Throttle altimetria troppo aggressivo

```javascript
// map3d.js - durante drag selezione
const now = Date.now();
if (now - lastAltimetryUpdate > 30) {  // 30ms = ~33fps
    lastAltimetryUpdate = now;
    // update zone colors su mappa
}
```

30ms è aggressivo. Aggiornare le zone-colored polylines ogni 30ms durante il drag può essere pesante soprattutto su dispositivi lenti. Aumentare a 50-80ms.

---

### 🟢 [BASSO] `ROADMAP.md` contiene TODO aperti non tracciati

```markdown
2) AGGIORNARE REQUIREMENTS....
```

I TODO nel codice e nei file di progetto andrebbero tracciati come issue su GitHub invece di rimanere in file Markdown non strutturati.

---

### 🟢 [BASSO] Copyright notice con licenza contradittoria

```python
# webapp/routes/api.py e altri file
# ==============================================================================
# Copyright (c) 2026 Andrea Bonvicin - bFactor Project
# PROPRIETARY LICENSE - TUTTI I DIRITTI RISERVATI
# Sharing, distribution or reproduction is strictly prohibited.
# ==============================================================================
```

Ma il file `LICENSE` alla root è Apache 2.0 (permissivo). C'è una contraddizione. Scegliere una sola licenza e applicarla coerentemente.

---

### 🟢 [BASSO] Commenti in italiano e inglese mischiati

Il codice alterna commenti in italiano e inglese senza un criterio evidente. Per un progetto personale è accettabile, ma per consistenza scegliere una sola lingua.

---

## 11. Riepilogo Priorità

### Fix Urgenti (prima del deployment su Render)

| # | Problema | File | Impatto |
|---|----------|------|---------|
| 1 | 🔴 `config.py` import rompe l'app | `map3d_generator.py` | Deploy impossibile |
| 2 | 🔴 Session ID solo 8 chars | `upload.py` | Sicurezza |
| 3 | 🔴 Nessun cleanup sessioni → OOM | `app.py` | Stabilità |
| 4 | 🟠 Nessuna autenticazione | `app.py` | Sicurezza |
| 5 | 🟠 Health check mancante | `app.py` | Operatività |

### Fix Importanti (prossime settimane)

| # | Problema | File | Impatto |
|---|----------|------|---------|
| 6 | 🟠 `calculateTimeBasedMovingAverage` O(n²) | JS multipli | Performance |
| 7 | 🟠 XSS nel report HTML esportato | `api.py` | Sicurezza |
| 8 | 🟠 Logica duplicata tra file JS | JS multipli | Manutenibilità |
| 9 | 🟡 `merge_extend` senza limite iterazioni | `effort_analyzer.py` | Stabilità |
| 10 | 🟡 Timestamp hardcoded nell'export | `api.py` | Correttezza |

### Miglioramenti (backlog)

| # | Problema | Impatto |
|---|----------|---------|
| 11 | 🟡 Stream data lazy loading | Performance |
| 12 | 🟡 `on_event` deprecato | Futuro |
| 13 | 🟡 localStorage → BroadcastChannel | Robustezza |
| 14 | 🟡 String replace fragile per export | Robustezza |
| 15 | 🟢 Type hints incompleti | Qualità |
| 16 | 🟢 Dead code `buildD3Chart()` | Pulizia |
| 17 | 🟢 `requirements.txt` aggiornare | Deployment |

---

## 12. Refactoring Suggeriti

### 12.1 Session Store centralizzato

Creare `webapp/sessions.py` come descritto nella sezione 3. Tutti i moduli importano da lì invece di ricevere il dict come parametro. Elimina il pattern `global _shared_sessions` ripetuto 8 volte.

### 12.2 JavaScript modulare

```
webapp/static/js/
├── utils.js              # fmtDur, format_time_mmss, debounce, moving average
├── intensity_zones.js    # getIntensityZones, zoneColorForPower  
├── stream_modal.js       # openStreamModal, buildStreamChartsD3, buildSprintStreamCharts
├── altimetry_chart.js    # drawFullElevationChart, selezione, metriche range
├── map3d.js              # (ridotto: solo logica specifica MapLibre)
└── map2d.js              # (ridotto: solo logica specifica Leaflet)
```

### 12.3 Config manager unificato

```python
# webapp/config_manager.py
import os
from pathlib import Path

class AppConfig:
    @staticmethod
    def maptiler_key() -> str:
        return os.environ.get("MAPTILER_API_KEY") or AppConfig._from_file()
    
    @staticmethod  
    def _from_file() -> str:
        try:
            from config import get_maptiler_key
            return get_maptiler_key()
        except ImportError:
            return ""
    
    @staticmethod
    def is_development() -> bool:
        return os.environ.get("ENVIRONMENT", "development") == "development"
```

### 12.4 Aggiunta `requirements.txt` con pin delle versioni

```
fastapi==0.115.0
uvicorn[standard]==0.31.0
python-multipart==0.0.12
jinja2==3.1.4
fitparse==1.2.0
pandas==2.2.3
numpy==2.1.3
slowapi==0.1.9       # rate limiting
```

### 12.5 Variabili d'ambiente per Render (`render.yaml`)

```yaml
services:
  - type: web
    name: peffort-web
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: cd webapp && uvicorn app:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: MAPTILER_API_KEY
        sync: false   # impostare manualmente nel dashboard Render
      - key: ENVIRONMENT
        value: production
      - key: APP_USER
        sync: false
      - key: APP_PASSWORD
        sync: false
```

---

*Fine review. Totale issues identificate: 32 (5 critici, 9 alti, 13 medi, 5 bassi).*
