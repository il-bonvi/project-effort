# 🚀 PEFFORT Web - Guida Avvio Server

## ⚡ Quick Start

### Avvio Rapido (Riga Singola)
```powershell
cd webapp && python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

**Poi apri il browser su**: http://localhost:8000

---

## 📋 Istruzioni Dettagliate

### 1️⃣ Apri PowerShell/Terminal

**Naviga alla cartella del progetto:**
```powershell
cd C:\Users\bonvi\Documents\GitHub\project-effort
```

### 2️⃣ Avvia il Server

**Opzione A: Con Auto-Reload (CONSIGLIATO per development)**
```powershell
cd webapp
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

**Opzione B: Senza Auto-Reload**
```powershell
cd webapp
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

### 3️⃣ Controlla che Funzioni

Vedrai output come:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

### 4️⃣ Apri il Browser

Vai a: **http://localhost:8000**

---

## 🔄 Riavvio del Server

### Se il Server è Ancora in Esecuzione

**Opzione 1: Ricarica la Pagina nel Browser**
- Press `F5` o `Ctrl+R` per ricaricare
- Se hai cambiato il **Python code**, il server auto-riavvia (con `--reload`)

**Opzione 2: Ferma e Riavvia**

Nel terminal dove è in esecuzione uvicorn, premi:
```
Ctrl + C
```

Vedrai:
```
Shutdown complete
```

Poi riavvia con il comando di avvio.

### Se il Server Non Risponde

**Forza la terminazione di uvicorn:**
```powershell
# Trova il processo
Get-Process python | Where-Object {$_.CommandLine -like "*uvicorn*"}

# Termina il processo (sostituisci [PID] con il numero)
Stop-Process -Id [PID] -Force

# Esempio:
Stop-Process -Id 1234 -Force
```

Poi riavvia il server.

---

## 🛠️ Troubleshooting

### ❌ Errore: "Port 8000 already in use"
```
Address already in use
```

**Soluzione:**
```powershell
# Usa una porta diversa
cd webapp
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8001
```

Poi apri browser su: http://localhost:8001

### ❌ Errore: "ModuleNotFoundError"
```
ModuleNotFoundError: No module named 'fastapi'
```

**Soluzione: Installa le dipendenze**
```powershell
pip install -r requirements.txt
```

### ❌ Errore: "No such file or directory"
Assicurati di essere nella cartella corretta:
```powershell
cd C:\Users\bonvi\Documents\GitHub\project-effort
ls webapp/  # Dovresti vedere: app.py, routes/, templates/
```

---

## 📂 Struttura Cartelle

```
project-effort/
├── config.py              ← API keys (DO NOT COMMIT)
├── requirements.txt       ← Dipendenze Python
├── STARTUP.md             ← Questo file
│
├── webapp/
│   ├── app.py             ← Main FastAPI application
│   ├── routes/            ← Route handlers
│   └── templates/         ← HTML templates
│
└── PEFFORT/               ← Core analysis modules
```

---

## 🔑 Configurazione Iniziale

### Prima di Avviare per la Prima Volta

1. **Configurazione API Key MapTiler** (opzionale, solo per 3D Map)
   - Apri `config.py` nella root
   - Sostituisci `YOUR_MAPTILER_API_KEY_HERE` con la tua chiave
   - Scarica gratis da: https://cloud.maptiler.com/

2. **Installa dipendenze**
   ```powershell
   pip install -r requirements.txt
   ```

---

## 📊 Verifica che Tutto Funzioni

### Test 1: Home Page
```
http://localhost:8000
```
Dovresti vedere la pagina di upload con il form.

### Test 2: Upload FIT File
1. Clicca "Scegli file"
2. Seleziona un file `.fit`
3. Imposta FTP (default: 280W) e Weight (default: 70kg)
4. Click "Upload & Analyze"

### Test 3: Dashboard
Dopo l'upload dovresti vedere:
- Tab: Overview
- Tab: Inspection
- Tab: Altimetria
- Tab: 🗺️ 3D Map
- Tab: Settings
- Tab: Export

---

## 🎯 Comandi Utili

### Ricarica Codice Automatico
Il server con `--reload` ascolta i cambiamenti ai file Python.

Se modifichi:
- ✅ Widget, routes → Auto-ricarica automaticamente
- ❌ Import PEFFORT → Potrebbe richiedere restart manuale

### Per Forzare Restart
```powershell
# Ctrl + C nel terminal
# Poi riavvia
cd webapp && python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### Visualizza Log Dettagliato
```powershell
cd webapp
python -m uvicorn app:app --reload --log-level debug
```

---

## 📝 Note Importanti

### 🔐 API Key Security
- Il file `config.py` è nel `.gitignore`
- **Non** verrà committato su git
- Ogni sviluppatore deve configurarlo localmente

### 💾 File Temporanei
- I file FIT caricati rimangono **solo in memoria**
- Non vengono salvati su disco (efficiente!)
- Dati rimangono fino a browser close o idle 24h

### 🌐 Accesso Remoto
Per accedere da altri computer sulla rete:
```powershell
# Sostituisci TUO_IP_LOCALE
http://TUO_IP_LOCALE:8000

# Esempio:
http://192.168.1.100:8000
```

---

## ✨ Tips & Tricks

### Apri Server e Browser Automaticamente
Crea uno script PowerShell (`start_server.ps1`):
```powershell
# Start server in background
Start-Process -WindowStyle Minimized -FilePath "powershell.exe" -ArgumentList "-NoExit", "-Command", "cd webapp; python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000"

# Wait 3 seconds for startup
Start-Sleep -Seconds 3

# Open browser
Start-Process "http://localhost:8000"
```

Poi esegui:
```powershell
.\start_server.ps1
```

### Cambia Porta Dinamicamente
```powershell
# Per usare porta diversa (es. 9000)
cd webapp
python -m uvicorn app:app --reload --host 0.0.0.0 --port 9000
```

---

## 🆘 Support

Se il server non parte:
1. ✅ Verifica di essere nella cartella corretta: `C:\Users\bonvi\Documents\GitHub\project-effort`
2. ✅ Controlla che Python sia installato: `python --version`
3. ✅ Installa dipendenze: `pip install -r requirements.txt`
4. ✅ Verifica che porta 8000 sia libera: `netstat -ano | findstr :8000`

---

**Felice analisi! 🚴‍♂️📊**
