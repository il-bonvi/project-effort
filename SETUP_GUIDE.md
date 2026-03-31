# 🚀 PEFFORT - Setup Automatico per Nuovo PC

Hai scaricato il progetto PEFFORT? Perfetto! Questa guida ti spiega come configurare tutto in pochi passi.

## ⚡ Configurazione Veloce (1 Clic!)

### Windows:
1. **Doppio clic** su `SETUP.bat`
2. Inserisci la tua **API key MapTiler** quando richiesto
3. Il sistema installerà tutto automaticamente
4. Scegli se avviare il server subito

### macOS / Linux:
```bash
python setup_project.py
```

---

## 📋 Cosa Fa lo Script Setup?

✅ Crea la virtual environment (`.venv`)  
✅ Installa tutte le dipendenze da `requirements.txt`  
✅ Chiede l'API key MapTiler tramite dialog GUI  
✅ Genera il file `config.py` con la tua chiave  
✅ Crea script launcher per avviare il server facilmente  
✅ Opzione per avviare il server subito  

---

## 🔑 Dove Ottenere l'API Key MapTiler?

1. Vai su https://cloud.maptiler.com/
2. Crea un account gratuito (o accedi)
3. Vai in "API Keys"
4. Copia la tua chiave di default (o creane una nuova)
5. Incolla quando richiesto durante lo setup

**Nota:** Puoi lasciare il campo vuoto e aggiungerla dopo editando `config.py`

---

## 🎯 Avvio del Server

**Dopo il setup iniziale, per avviare il server:**

### Windows:
Doppio clic su `run_server.bat`

### macOS / Linux:
```bash
./run_server.sh
```

### Oppure manualmente:
```bash
# Attiva la venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # macOS/Linux

# Avvia il server
cd webapp
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8001
```

**Server disponibile su:** http://localhost:8001

---

## 🛠️ Troubleshooting

### Python non trovato
- Installa Python 3.9+ da https://www.python.org/
- **Importante:** Seleziona "Add Python to PATH" durante l'installazione

### L'API key dà errore sulla mappa 3D
- Controlla di aver incollato la chiave corretta in `config.py`
- Accedi a https://cloud.maptiler.com/ e verifica che la chiave sia attiva

### Porta 8001 già in uso
Se il server non si avvia perché la porta è occupata:
```bash
cd webapp
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8002
```
Poi accedi a `http://localhost:8002`

---

## 📁 Struttura del Progetto

```
project-effort/
├── setup_project.py       ← Script setup principale
├── SETUP.bat             ← Launcher per Windows (doppio clic!)
├── config.py             ← Auto-generato da setup (NON committare!)
├── requirements.txt      ← Dipendenze Python
├── webapp/               ← Applicazione FastAPI
│   ├── app.py
│   ├── routes/           ← Endpoint API
│   ├── templates/        ← HTML templates
│   ├── static/           ← CSS, JS
│   └── utils/            ← Utility functions
└── .gitignore            ← File sensibili non sincronizzati
```

---

## ✨ Funzionalità Principale

- **Upload FIT:** Carica file GPS/fitness
- **Dashboard:** Analisi dati con grafici
- **Mappa 3D:** Visualizzazione altimetria con MapTiler
- **Inspection:** Analisi dettagliata tracciati

---

## ❓ Domande?

Consulta `STARTUP.md` per istruzioni più dettagliate.

---

**Buon utilizzo di PEFFORT! 🎉**
