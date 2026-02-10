# PEFFORT Web Application - Refactored Structure

## Overview

Il file monolitico `webapp/app.py` è stato **diviso in sezioni coerenti** per migliorare manutenibilità, testabilità e scalabilità.

## Struttura Directory

```
webapp/
├── app.py                          # FastAPI main app (tutte le rotte per ora)
├── requirements.txt                # Python dependencies
│
├── templates/                      # HTML Templates
│   ├── home.html                  # 🏠 Home page - FIT upload form
│   ├── dashboard.html             # 📊 Main dashboard (12 tabs)
│   └── inspection.html            # 🔍 Interactive effort editor
│
├── routes/                         # Route Handlers (organizzazione logica)
│   ├── __init__.py               # Module exports
│   ├── upload.py                 # POST /upload handler
│   ├── dashboard.py              # GET /dashboard/{session_id} (placeholder)
│   ├── inspection.py             # GET /inspection/{session_id} (placeholder)
│   └── api.py                    # /api/* endpoints (placeholder)
│
└── utils/                         # Utility Functions & Business Logic
    ├── __init__.py               # Module exports
    ├── metrics.py                # NP, IF, TSS, VI calculations
    ├── parsers.py                # (Future) FIT parsing logic
    └── efforts.py                # (Future) Effort detection logic
```

## What Changed

### ✅ Already Refactored

- **`utils/metrics.py`** - Estratte tutte le funzioni di calcolo metriche
  - ✨ Ora riutilizzabile in altri progetti
  - 📦 Importazioni pulite: `from utils import calculate_ride_stats`

- **`templates/home.html`** - Estratto HTML dalla stringa Python
  - ✨ Leggibile come file HTML vero
  - 🎨 Più facile modificare CSS/JS senza toccare Python

- **`routes/upload.py`** - Estratto handler `POST /upload`
  - ✨ Logica upload separata dal resto
  - 📝 Docstrings dettagliati su parametri e flusso

- **`routes/__init__.py`** - Module initialization
  - ✨ Importazione centralizzata da moduli routes

- **`routes/api.py`, `routes/dashboard.py`, `routes/inspection.py`** - Placeholder files
  - 📋 Struttura pronta per estrazione successiva

### 📋 Placeholder (Da fare)

Questi file contengono le rotte ma rimangono in `app.py` per compatibilità:
- Dashboard tab system con 3 griglie ECharts
- API endpoints per redetect efforts/sprints
- Export FIT/JSON/GPX/CSV
- Session management

*Possono essere estratti in fase 2 quando il refactoring sarà completato.*

## Como Usare la Nuova Struttura

### Import delle utilità di calcolo

**Prima (non ideale):**
```python
from app import calculate_normalized_power, calculate_tss
```

**Adesso (pulito):**
```python
from utils import calculate_ride_stats, calculate_normalized_power
```

### Import degli handler di upload

**Adesso (quando sarà completato):**
```python
from routes.upload import upload_fit_handler

@app.post("/upload")
async def upload_fit(...):
    return await upload_fit_handler(app, sessions, upload_dir, ...)
```

## File Importanti

### `templates/home.html`
```
📁 Contenuto:
  ✓ HTML5 senza alcuna logica Python
  ✓ CSS inline per styling responsive
  ✓ JavaScript vanilla per drag & drop, validazione
  ✓ Form submit a /upload con tutti i parametri

📝 Modificare per:
  - Cambiare colori/font
  - Aggiungere nuovi campi parametri
  - Migliorare UX
```

### `utils/metrics.py`
```
📦 Funzioni esportate:
  • calculate_normalized_power(power_data)
  • calculate_intensity_factor(np_value, ftp)
  • calculate_tss(np_value, ftp, duration_hours)
  • calculate_variability_index(np_value, avg_power)
  • calculate_ride_stats(df, ftp) ← Usa tutte le precedenti

✨ Verificate e testate
```

### `routes/upload.py`
```
📝 Contiene una sola funzione:
  async def upload_fit_handler(
      app,
      sessions: Dict[str, Any],
      upload_dir: Path,
      file: UploadFile = File(...),
      ftp: float = Form(280),
      ... (altri parametri)
  ) -> RedirectResponse

🔄 Flusso:
  1. Validazione file .fit
  2. Save to disk
  3. Parse FIT → DataFrame
  4. Detect efforts (con PEFFORT engine)
  5. Detect sprints
  6. Calculate stats
  7. Store in sessions
  8. Redirect to /dashboard/{session_id}
```

## Vantaggi della Nuova Struttura

| Aspetto | Prima | Adesso |
|---------|--------|--------|
| **File monolitico** | 4069 linee! 💥 | Mod Suddiviso in parti logiche 📚 |
| **HTML inline** | Mescolato con Python | Separato in .html files 📄 |
| **Utilities** | Non riutilizzabili | Importabili da altri progetti 🔄 |
| **Manutenzione** | Difficile scrollare | Navigazione chiara per sezione |
| **Testing** | Hard to unit test | Easy to mock/test singoli moduli |
| **Collab** | Conflitti merge | Meno conflitti, file separati |

## Prossimi Passi

Vedi [REFACTORING_GUIDE.md](../REFACTORING_GUIDE.md) per:
1. ✅ Passo 1-4 completati (struttura creata)
2. 📋 Passo 5+: Estrarre remaining routes
3. 🚀 Fase 2: Usare Jinja2Templates per templates dinamici
4. 📦 Fase 3: Aggiungere type hints e docstrings completi

## Testing della Nuova Struttura

```bash
# Verifica che i file sono creati
ls -la webapp/templates/
ls -la webapp/routes/
ls -la webapp/utils/

# Verifica imports
python -c "from webapp.utils import calculate_ride_stats; print('✓ OK')"
python -c "from webapp.routes.upload import upload_fit_handler; print('✓ OK')"

# Run server (ancora usa app.py come prima)
python webapp/app.py
```

## Notes

- **app.py rimane il entry point** per compatibilità (per ora)
- **Tutti gli endpoint continuano a funzionare** come prima
- **Prossime fasi** estrapolicheranno più logica da app.py
- **HTML templates sono statici** (senza template engine al momento)
  - Possono diventare Jinja2 dinamici in fase 2

---

**Status**: 🟡 **In Progress** - Fase 1 completata, pronto per fase 2

Vedi REFACTORING_GUIDE.md per dettagli su come continuare >
