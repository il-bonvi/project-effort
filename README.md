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

- Copia `config.example.py` in `config.py`
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
start_server.bat
```

## Sicurezza MapTiler

La mappa 3D usa la chiave MapTiler nel codice client JavaScript.
Questo significa che la chiave e' visibile nel sorgente della pagina.

Per uso sicuro:

1. Imposta sempre restrizioni dominio/referrer nella dashboard MapTiler.
2. Non riutilizzare la stessa chiave su progetti non correlati.
3. Ruota periodicamente la chiave in caso di sospetto abuso.

Checklist operativa consigliata:

1. In MapTiler Cloud, limita la key al dominio di produzione e localhost di sviluppo.
2. Imposta in ambiente `MAPTILER_KEY_DOMAIN_RESTRICTED=true` dopo aver verificato la restrizione.
3. Controlla endpoint health: `maptiler_domain_restriction_ack` deve risultare `true`.

## Deployment su Render

1. Push del repository su GitHub.
2. Crea un nuovo Web Service su Render.
3. Build Command:

```bash
pip install -r requirements.txt
```

4. Start Command:

```bash
cd webapp && uvicorn app:app --host 0.0.0.0 --port $PORT
```

5. Environment Variables:
- `MAPTILER_API_KEY=<tua_chiave>`
- `MAPTILER_KEY_DOMAIN_RESTRICTED=true` (impostare solo dopo aver ristretto il dominio in MapTiler)
- `LOG_LEVEL=INFO` (oppure `WARNING` in produzione)
- `UPLOAD_RATE_LIMIT_MAX_REQUESTS=10`
- `UPLOAD_RATE_LIMIT_WINDOW_SECONDS=60`
- `UPLOAD_RATE_LIMIT_TRUST_PROXY_HEADERS=true` (consigliato dietro proxy/reverse proxy)
- `REDIS_URL=redis://:<password>@<host>:<port>/0`

## Decisione Rate Limiting Produzione

Scelta validata:

1. Sviluppo/local: limiter in-memory integrato (gia' attivo).
2. Produzione: usare reverse proxy + header real IP (`UPLOAD_RATE_LIMIT_TRUST_PROXY_HEADERS=true`).
3. Evoluzione opzionale: migrazione a SlowAPI/Redis se servono quote condivise su istanze multiple.

Nota: il limiter in-memory non e' condiviso tra processi/istanze multiple.

## Decisione Persistenza Sessioni su Render

Scelta validata:

1. Strategia scelta: Redis come unico backend di persistenza sessioni.
2. Configurare `REDIS_URL` in Render (Redis gestito o servizio compatibile).
3. Senza `REDIS_URL`, l'app usa fallback in-memory solo per sviluppo locale.

Stima costi orientativa:

1. Redis gestito: costo maggiore ma migliore per multi-instance/concorrenza.

## Troubleshooting minimo

- Errore porta occupata: cambia porta (`--port 8002`)
- Modulo non trovato: verifica venv attiva e riesegui `pip install -r requirements.txt`
- Errore permessi script PowerShell:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
