Contesto: Ho un'app FastAPI (PEFFORT) che analizza file FIT di ciclismo. Uso ruptures (Pelt algorithm) per rilevare effort (intervalli ad alta intensità) da dati di potenza.
Pipeline attuale:
python# RupturesConfig params:
model = "l2"              # l2 / rbf / l1
penalty = 10.0            # basso=molti segmenti, alto=pochi
min_segment_sec = 15      # granularità Pelt (min_size)
smooth_window_sec = 20    # rolling mean pre-Pelt
min_cp_pct = 100.0        # soglia above/below (% CP)
merge_gap_sec = 30        # gap max per merge adiacenti
merge_power_diff_pct = 15 # Δ potenza max per merge
min_effort_sec = 60       # post-merge: scarta se troppo corto...
sprint_threshold_pct = 200 # ...a meno che non superi questa % CP
Pipeline:

Smooth (rolling mean smooth_window_sec)
Downsample a 1Hz
Pelt → breakpoints
Remap indici originali
Label above/below min_cp_pct
Merge adiacenti: gap ≤ merge_gap_sec AND Δpwr ≤ merge_power_diff_pct%
Filter: mostra se duration >= min_effort_sec OR avg_power >= cp * sprint_threshold_pct / 100

Obiettivo: Trovare i parametri ottimali per un file FIT reale (CP=235W, ~12000 samples, ~3.5h) confrontando il risultato con effort scelti manualmente tramite visual inspection.
Dato disponibile: CSV o array numpy con colonne time_sec, power — posso incollarlo o descrivere il pattern degli effort che voglio rilevare.
Domanda: Come faccio a calibrare i parametri in modo sistematico? Posso condividere i dati grezzi e gli effort "gold" che voglio rilevare, e voglio capire quali parametri devo alzare/abbassare per avvicinarmi al risultato.






2.0:
1) salvare in cache i valori delle celle di opener ecc (non vengono ora...)
2) lavoriamo su modello reale funzionante. Ora ci sta comunque









1)
aggiustamenti hover mini alt (doppio per selezione, trascinamento ON)




il ratio, viene semplicemente calcolato come 1a metà e 2a metà. Voglio che sia configurabile (in quersto caso il numero di "sezioni è 2). Voglio un mini button, sotto a stream. Qui, si apre una nuova finestra simile a stream. Qua, inserisco il valore di sezioni e mi mostrerà in tabella, le varie sezioni. Se metto 8, mi farà 8 sezioni di uguale durata della parte di mappa selezionata. Vedrò i watt in tabella ma anche altre metriche interessanti, per ora metti 2-3 esempi liberi, ci lavorerò in un secondo momento
TABELLA CON VARIE SEZIONI


**Cosa aggiungere:**

- **Dashboard multi-sessione**: caricare più file FIT in parallelo e visualizzarli sovrapposti sullo stesso grafico altimetrico/potenza, allineati per distanza o tempo.
- **Confronto identico segmento**: selezionare un segmento (es. una salita) e confrontare le prestazioni dell'atleta su date diverse. Mostra delta di potenza, VAM, HR per lo stesso tratto geografico.


## 4. Sezioni Configurabili (Analisi Pacing)

La feature menzionata nel ROADMAP.md ("il ratio, viene semplicemente calcolato come 1a metà e 2a metà").

**Cosa aggiungere:**

- **Pacing Analysis Modal**: dato un effort o una selezione manuale sull'altimetria, apre una finestra dove si imposta il numero di sezioni (N = 2, 3, 4, 8...). Il sistema divide l'intervallo in N parti di uguale durata e mostra una tabella con: potenza media, W/kg, HR media, VAM, cadenza, velocità per ogni sezione.
- **Visualizzazione grafica del pacing**: grafico a barre orizzontali dove ogni sezione è colorata per zona, così si vede subito se l'atleta è partito troppo forte o ha accelerato.
- **Indice di pacing**: un singolo numero (deviazione standard normalizzata delle N sezioni) che sintetizza quanto l'atleta ha distribuito lo sforzo in modo uniforme.

---

## 6. Report PDF Automatico

Oggi esiste l'export HTML interattivo, ma per comunicare con atleti o staff serve un documento stampabile.

**Cosa aggiungere:**

- **Report PDF per sessione**: genera automaticamente un PDF con: copertina con nome atleta e data, KPI riepilogativo (NP, IF, TSS, distanza, dislivello), grafico altimetrico con effort colorati, tabella effort con tutte le metriche, tabella sprint, curva MMP della sessione. Usando `weasyprint` o `reportlab`.
- **Template personalizzabile**: il coach carica il logo del team, sceglie quali sezioni includere.
- **Report comparativo**: PDF che mette affiancati due sessioni dello stesso atleta o due atleti sullo stesso percorso.

## 8. Note e Annotazioni sugli Effort

Un coach ha bisogno di contestualizzare i numeri.

**Cosa aggiungere:**

- **Note testuali per effort**: campo di testo libero associabile a ogni effort. "Scalata del Grappa, vento contrario" oppure "recupero dopo 4h di gara". Le note sono salvate nel JSON di export e reimportate.
- **Tag predefiniti**: sistema di tag rapidi (Recovery, Test, Race, Interval, All-Out) applicabili con un click, colorano diversamente l'effort nella legenda.
- **Commento sessione**: campo note a livello di sessione intera, incluso nel report PDF.

---

## 9. Integrazione con Dati Esterni

- **Temperatura e meteo**: arricchisce automaticamente la sessione con i dati meteo (OpenMeteo API, gratuita) in base a coordinate GPS e timestamp. Utile per contestualizzare prestazioni in condizioni climatiche diverse.

---

## 10. Gestione Persistente delle Sessioni

Il punto più critico per l'uso remoto in viaggio.

**Cosa aggiungere:**

- **Persistenza su disco con SQLite**: le sessioni non devono svanire al riavvio del server. Serializzare DataFrame in Parquet/pickle e metadati in SQLite. Al riavvio, le sessioni vengono ricaricate lazy (solo su richiesta).
- **Archivio sessioni**: pagina dedicata che lista tutte le sessioni salvate con data, nome file, KPI principali, con possibilità di eliminare o riaprire.
- **Limite di retention configurabile**: il coach configura quante sessioni conservare (es. ultime 100) con pulizia automatica delle più vecchie.
- **Backup/export dell'archivio**: scarica un archivio ZIP con tutti i JSON di export di tutte le sessioni.
