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
