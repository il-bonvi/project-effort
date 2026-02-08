# 🗺️ Mappa 3D - Istruzioni di Configurazione

## ✅ Cosa è stato aggiunto

### 1. File Config con API Key
- **File**: `config.py` (root del progetto)
- **Contenuto**: Funzioni per gestire la chiave API MapTiler
- **IMPORTANTE**: Questo file è già in `.gitignore` e NON verrà committato

### 2. Route Map3D  
- **File**: `webapp/routes/map3d.py`
- **Endpoint**: `GET /map3d/{session_id}`
- **Funzione**: Genera la mappa 3D interattiva con terrain

### 3. Tab nel Dashboard
- **File**: `webapp/templates/dashboard.html`
- **Aggiunta**: Tab "🗺️ 3D Map" con iframe embedded
- **Posizione**: Dopo Altimetria, prima di Settings

### 4. Template HTML
- **File**: `webapp/templates/map3d.html`
- **Tipo**: Template di riferimento (la mappa reale è generata dinamicamente)

### 5. Registrazione Route
- **File**: `webapp/app.py`
- **Modifica**: Import, setup e registrazione del router map3d

---

## 🔧 Configurazione

### Step 1: Ottieni la chiave API MapTiler (GRATIS)

1. Vai su: https://cloud.maptiler.com/
2. Crea un account gratuito
3. Vai nella sezione "API Keys"
4. Copia la tua chiave API

### Step 2: Configura config.py

Apri il file `config.py` nella root del progetto e sostituisci:

```python
MAPTILER_API_KEY = "YOUR_MAPTILER_API_KEY_HERE"
```

con la tua chiave reale:

```python
MAPTILER_API_KEY = "abc123def456..."  # La tua chiave qui
```

**ATTENZIONE**: Non condividere mai questo file! È già in `.gitignore`.

---

## 🚀 Come Usare

### 1. Avvia il server

```powershell
cd project-effort
uvicorn webapp.app:app --reload
```

### 2. Carica un file FIT

- Vai su `http://localhost:8000`
- Carica un file .fit con **dati GPS**
- Imposta FTP e peso

### 3. Apri la Dashboard

- Dopo l'upload, verrai reindirizzato alla dashboard
- Vedrai le tab: Overview | Inspection | Altimetria | **🗺️ 3D Map** | Settings | Export

### 4. Visualizza la Mappa 3D

- Clicca sulla tab "**🗺️ 3D Map**"
- La mappa si caricherà nell'iframe
- **Oppure**: Clicca "🗺️ Apri in Nuova Finestra" per visualizzazione full-screen

---

## 🎮 Funzionalità della Mappa 3D

### Identiche all'app PEFFORT originale:

#### Mappa Interattiva
- ✅ Terrain 3D con esagerazione (DEM MapTiler)
- ✅ Traccia GPS evidenziata in giallo
- ✅ Controlli 3D: Pitch, Bearing, Zoom
- ✅ 8 stili mappa: Outdoor, Streets, Topo, Bright, Dark, Winter, Satellite, Hybrid

#### Markers Efforts
- ✅ Marker colorato per zona potenza (Z1-Z7)
- ✅ Numerati (1, 2, 3...)
- ✅ Popup al click con info effort
- ✅ Click apre sidebar dettagliata

#### Sidebar Dettagli Effort
- ✅ Potenza (Media, Best 5s, 1ª vs 2ª metà)
- ✅ Potenza Relativa (W/kg)
- ✅ Cadenza & Heart Rate
- ✅ Tempo, Distanza, Velocità
- ✅ Altimetria (Guadagno, Pendenza media/max)
- ✅ VAM (Effettivo e Teorico)
- ✅ Lavoro (kJ totali e sopra CP)
- ✅ Densità Oraria (kJ/h/kg)

#### Grafico Altimetrico
- ✅ Profilo elevazione sotto la mappa
- ✅ Tracce efforts sovrapposte colorate
- ✅ Resize verticale del grafico (drag handle)
- ✅ Highlight effort selezionato
- ✅ Linee verticali start/end effort

#### Controlli
- ✅ Dropdown per cambiare stile mappa
- ✅ Bottone "🎯 Reset View" per centrare
- ✅ Chiudi sidebar con ✕

---

## 📁 Struttura File Creati/Modificati

```
project-effort/
├── config.py                          # ⚡ NUOVO - API keys (in .gitignore)
├── .gitignore                         # ✏️ MODIFICATO - aggiunto config.py
│
└── webapp/
    ├── app.py                         # ✏️ MODIFICATO - import map3d router
    │
    ├── routes/
    │   ├── __init__.py               # ✏️ MODIFICATO - export map3d
    │   └── map3d.py                  # ⚡ NUOVO - route handler 3D map
    │
    └── templates/
        ├── dashboard.html             # ✏️ MODIFICATO - tab 3D Map
        └── map3d.html                 # ⚡ NUOVO - template riferimento
```

---

## ⚠️ Risoluzione Problemi

### Errore: "Session not found"
- Assicurati di aver caricato un file FIT prima di aprire la mappa

### Errore: "GPS data not available"
- Il file FIT non contiene dati GPS
- La mappa 3D richiede coordinate GPS valide

### Mappa non si carica
1. Verifica di aver configurato `MAPTILER_API_KEY` in `config.py`
2. Controlla la console browser (F12) per errori JavaScript
3. Verifica che il file FIT contenga GPS data

### Stili mappa non funzionano
- Verifica la connessione internet
- La chiave API MapTiler deve essere valida
- Account free ha limiti di richieste (50k/mese)

---

## 🎯 Differenze con l'App Desktop

**NESSUNA DIFFERENZA**:
- ✅ Codice identico al 100%
- ✅ Usa stesso `map3d_builder.py`
- ✅ Usa stesso `map3d_renderer.py`
- ✅ Usa stesso `map3d_core.py`
- ✅ CSS e JavaScript identici
- ✅ Grafici Plotly identici

L'unica differenza è il **metodo di visualizzazione**:
- Desktop: Apre in browser temporaneo
- Web: Embedded in dashboard o nuova finestra

---

## 📝 Note Tecniche

### Generazione Dinamica HTML
La mappa NON usa template Jinja2. L'HTML completo viene generato dinamicamente da:
- `PEFFORT/map3d_builder.py` → Orchestrazione
- `PEFFORT/map3d_core.py` → Calcoli GPS/efforts
- `PEFFORT/map3d_renderer.py` → HTML/CSS/JS

Questo garantisce che ogni mappa contenga i dati esatti della sessione.

### API Key Security
Il file `config.py` è escluso da git tramite `.gitignore`. Ogni utente deve configurare la propria chiave API localmente.

### Compatibilità Browser
- ✅ Chrome/Edge (consigliato)
- ✅ Firefox
- ✅ Safari
- ⚠️ Internet Explorer NON supportato (usa MapLibre GL JS moderno)

---

## ✨ Prossimi Passi

1. Configura `config.py` con la tua API key
2. Testa con un file FIT reale con GPS
3. Confronta con l'app desktop PEFFORT originale
4. Verifica che tutti gli effort siano visualizzati correttamente

**Tutto dovrebbe essere IDENTICO!** 🎉
