# PEFFORT Web

Webapp FastAPI per analisi file FIT.

## Requisiti

- Windows 10/11
- Python 3.11+ installato e disponibile nel PATH
- PowerShell

## Installazione su nuova macchina

1. Clona o copia il progetto.
2. Apri PowerShell nella root del progetto.
3. Crea ambiente virtuale:

```powershell
python -m venv .venv
```

4. Attiva ambiente virtuale:

```powershell
& .\.venv\Scripts\Activate.ps1
```

5. Installa dipendenze:

```powershell
pip install -r requirements.txt
```

6. Configura chiavi API (opzionale per mappa 3D):

- Modifica `config.py`
- Imposta `MAPTILER_API_KEY`

## Avvio server

Dalla root del progetto:

```powershell
cd webapp
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8001
```

Apri il browser:

- http://localhost:8001

## Avvio rapido alternativo

Da root progetto:

```powershell
run_server.bat
```

## Troubleshooting minimo

- Errore porta occupata: cambia porta (`--port 8002`)
- Modulo non trovato: verifica venv attiva e riesegui `pip install -r requirements.txt`
- Errore permessi script PowerShell:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
