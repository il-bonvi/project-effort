# 👨‍💻 PEFFORT Developer Setup Guide

Questa guida è per chi vuole contribuire o modificare il progetto PEFFORT.

## 🔧 Configurazione Automatica (Consigliato)

Il modo **più veloce e semplice** per configurare tutto:

### Windows:
```
SETUP.bat
```
Doppio clic e tutto viene configurato automaticamente!

### macOS / Linux:
```bash
python setup_project.py
```

## 📦 Cosa Viene Configurato?

Lo script `setup_project.py` automaticamente:

1. **Crea virtual environment** (`.venv`)
   - Isolata da altri progetti Python

2. **Installa dipendenze** (`requirements.txt`)
   - FastAPI, uvicorn, plotly, pandas, numpy, fitparse, etc.

3. **Configura API keys**
   - Dialog GUI per inserire MapTiler API key
   - Genera `config.py` (ignorato da git per sicurezza)

4. **Crea launcher scripts**
   - `run_server.bat` (Windows)
   - `run_server.sh` (macOS/Linux)

5. **Avvia il server** (opzionale)

## 🚀 Avvio Manuale del Server

Se preferisci controllare quando il server si avvia:

```bash
# 1. Attiva virtual environment
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS/Linux

# 2. Installa dipendenze (se ancora non fatte)
pip install -r requirements.txt

# 3. Naviga a webapp
cd webapp

# 4. Avvia il server con auto-reload
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8001
```

**Server disponibile a:** `http://localhost:8001`

## 📝 File di Configurazione

### `config.py` (AUTO-GENERATO, IGNORATO DA GIT)
```python
MAPTILER_API_KEY = "your-key-here"
MAPBOX_ACCESS_TOKEN = "optional"
```
- **NON committare mai questo file** (le chiavi API sono sensibili)
- Auto-generato da `setup_project.py`
- Elencato in `.gitignore`

### `config_template.py` (TEMPLATE DI RIFERIMENTO)
- Template che mostra la struttura di `config.py`
- **Questo SI viene committato** come documentazione

### `requirements.txt`
```
fastapi>=0.109.1
uvicorn>=0.24.0
python-multipart>=0.0.22
fitparse>=1.2.0
pandas>=2.0.0
numpy>=1.24.0
plotly>=5.18.0
```
- Aggiungi dipendenze qui se necessario
- Aggiorna con: `pip freeze > requirements.txt`

## 🔑 API Keys & Secrets

### MapTiler (Obbligatorio per mappe 3D)
1. Vai a https://cloud.maptiler.com/
2. Crea account gratuito
3. Copia la default API key
4. Incolla quando richiesto da `setup_project.py`
5. O edita manualmente `config.py`

**Utilizzo nel codice:**
```python
from config import get_maptiler_key

api_key = get_maptiler_key()
# Usa api_key in map3d_generator.py
```

## 📁 Struttura Progetto

```
project-effort/
├── setup_project.py              ← Setup automatico main
├── SETUP.bat                     ← Windows launcher (doppio clic)
├── SETUP_GUIDE.md                ← Guida setup per utenti
├── README_DEV.md                 ← Questo file
├── config.py                     ← ⚠️ AUTO-GENERATO, NON COMMITTARE
├── config_template.py            ← 📄 Template di riferimento
├── run_server.bat                ← Auto-generato, launcher Windows
├── run_server.sh                 ← Auto-generato, launcher Unix
├── requirements.txt              ← Dipendenze Python
├── .gitignore                    ← Esclude config.py e venv
│
├── webapp/
│   ├── app.py                    ← FastAPI main app
│   ├── routes/                   ← Endpoint API
│   │   ├── home.py
│   │   ├── api.py
│   │   ├── upload.py
│   │   ├── dashboard.py
│   │   ├── inspection.py
│   │   ├── altimetria_d3.py
│   │   └── map3d.py
│   ├── templates/                ← HTML Jinja2 templates
│   │   ├── home.html
│   │   ├── dashboard.html
│   │   ├── inspection.html
│   │   ├── map3d.html
│   │   └── altimetria_d3.html
│   ├── static/                   ← CSS, JS, assets
│   │   ├── css/
│   │   │   └── map3d.css
│   │   └── js/
│   │       └── map3d.js
│   └── utils/                    ← Core logic
│       ├── analysis_config.py
│       ├── chart_renderer.py
│       ├── effort_analyzer.py
│       ├── map3d_core.py
│       ├── map3d_generator.py
│       ├── map3d_renderer.py
│       └── metrics.py
│
└── .venv/                        ← Virtual environment (auto-creato)
```

## 🐛 Troubleshooting

### Errore: "Python non trovato"
- Installa Python 3.9+ da https://www.python.org/
- ⚠️ **Durante l'installazione, seleziona "Add Python to PATH"**

### Errore: "Permission denied" (macOS/Linux)
```bash
chmod +x setup_project.py
chmod +x run_server.sh
python setup_project.py
```

### La porta 8001 è già occupata
```bash
cd webapp
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8002
```
Accedi a `http://localhost:8002`

### Mappe 3D non si caricano
- Verifica che la MapTiler API key sia corretta in `config.py`
- Controlla https://cloud.maptiler.com/ che la key sia attiva
- Prova a ricaricare la pagina del browser

### Virtual environment corrotta
```bash
# Rimuovi la venv corrotta
rm -r .venv              # macOS/Linux
rmdir /s .venv           # Windows

# Ricrea tutto con setup
python setup_project.py
```

## 📦 Aggiornare Dipendenze

Se aggiungi nuove dipendenze:

```bash
# Attiva la venv
.venv\Scripts\activate   # Windows

# Aggiungi con pip
pip install nome-dipendenza

# Aggiorna requirements.txt
pip freeze > requirements.txt

# Committare requirements.txt (NON la venv!)
git add requirements.txt
git commit -m "Aggiunta dipendenza: nome-dipendenza"
```

## 🔐 .gitignore - File Non Trackati

```
config.py                    ← Le API keys NON vanno su git!
.venv/                       ← Virtual environment locale
uploads/                     ← File caricati dagli utenti
__pycache__/                 ← Cache Python
*.bat                        ← Script launcher locali
```

File `.gitignore` è già configurato correttamente - **non modificare a meno che necessario**.

## ✅ Checklist Primo Setup

- [ ] Python 3.9+ installato e in PATH
- [ ] Eseguito `SETUP.bat` (Windows) o `python setup_project.py` (Unix)
- [ ] Inserita MapTiler API key durante setup
- [ ] Verificato che `config.py` è stato creato
- [ ] Eseguito il server (`run_server.bat` o manualmente)
- [ ] Raggiunto `http://localhost:8001` nel browser
- [ ] Pagina home si carica correttamente

## 🚀 Prossimi Passi

1. **Uploadare file GPS/FIT** tramite interfaccia
2. **Visualizzare dati** nei dashboard
3. **Analizzare percorsi** con mappa 3D e grafici
4. **Sviluppare nuove feature** seguendo la struttura modular routes

## 📚 Documentazione Aggiuntiva

- `STARTUP.md` - Guida avvio rapido server
- `SETUP_GUIDE.md` - Setup per utenti finali
- `ROADMAP.md` - Feature roadmap

---

**Per sviluppo rapido: doppio clic su SETUP.bat e code! 🚀**
