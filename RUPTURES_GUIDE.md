# Guida Completa alla Rilevazione degli Effort con Ruptures (PELT) in PEFFORT

## Introduzione

L'obiettivo della pipeline è identificare automaticamente gli **effort** (intervalli di lavoro) all'interno di una registrazione FIT di ciclismo utilizzando il rilevamento di **change point** tramite la libreria `ruptures`.

A differenza di un approccio basato esclusivamente su soglie (es. >95% CP), il Change Point Detection cerca di individuare i momenti in cui il comportamento della serie temporale cambia significativamente, segmentando l'attività in porzioni statisticamente omogenee.

Questo approccio permette di:

- Rilevare intervalli strutturati.
- Identificare variazioni di intensità.
- Ridurre la dipendenza da soglie rigide.
- Gestire workout complessi con recuperi e transizioni.

---

# Cos'è il Change Point Detection

Dato un segnale temporale:

```
Potenza (W)
320 │        ╔══════╗              ╔═════════╗
270 │        ║      ║              ║         ║
220 │        ║      ║    ╔════╗    ║         ║
150 │────────╝      ╚════╝    ╚════╝         ╚────
     0      500    1500  2000 3000 5000      6000   t (s)
              ↑      ↑    ↑    ↑    ↑         ↑
             CP      CP  CP   CP    CP        CP   ← ChangePoints
```

esiste un punto in cui la distribuzione statistica del segnale cambia.

Questo punto viene chiamato:

> Change Point (CP)

Nel ciclismo può rappresentare:

- Inizio intervallo
- Fine intervallo
- Transizione recupero/lavoro
- Cambio di ritmo
- Sprint
- Inizio salita
- Fine salita

L'obiettivo dell'algoritmo è trovare automaticamente questi punti.

---

# La libreria Ruptures

`ruptures` è una libreria Python specializzata nel rilevamento offline dei Change Point.

Implementa diversi algoritmi:

| Algoritmo | Complessità | Utilizzo |
|------------|------------|-----------|
| PELT | Molto efficiente | Consigliato |
| Dynp | Ottimale ma lento | Dataset piccoli |
| Binseg | Veloce | Approssimazione |
| BottomUp | Veloce | Approssimazione |
| Window | Locale | Segnali rumorosi |

PEFFORT utilizza:

```python
rpt.Pelt()
```

---

# Teoria del PELT

PELT significa:

> Pruned Exact Linear Time

È uno degli algoritmi più utilizzati per il Change Point Detection perché offre un eccellente compromesso tra accuratezza e velocità.

L'obiettivo è minimizzare:

```math
Cost = Σ SegmentCost + βK
```

dove:

- `SegmentCost` = errore interno di ogni segmento
- `K` = numero di Change Point
- `β` = penalty

---

## Interpretazione intuitiva

PELT cerca il miglior equilibrio tra:

### Troppi segmenti

```text
300
302
301
299
300
301
```

Ogni piccola oscillazione genera un breakpoint.

### Troppo pochi segmenti

```text
150W recupero
300W lavoro
150W recupero
```

Tutto viene interpretato come un unico segmento.

La `penalty` controlla questo compromesso.

---

# Pipeline di PEFFORT

```text
FIT
 ↓
Power Extraction
 ↓
Rolling Mean Smoothing
 ↓
Downsample a 1 Hz
 ↓
PELT
 ↓
Breakpoints
 ↓
Classificazione Above/Below CP
 ↓
Merge Segmenti
 ↓
Filtri Finali
 ↓
Efforts
```

---

# Parametri Configurabili

## `smooth_window_sec`

```python
smooth_window_sec = 20
```

### Scopo

Applicare una media mobile prima della segmentazione.

### Esempio

Segnale originale:

```text
320
340
290
350
310
```

Dopo smoothing:

```text
322
323
321
324
322
```

### Effetti

#### Valori bassi (5-10 s)

- Maggiore sensibilità.
- Più breakpoint.
- Migliore rilevazione di effort brevi o cambi di ritmo.

#### Valori alti (20-30 s)

- Segnale più stabile.
- Meno breakpoint.
- Migliore per intervalli lunghi.

### Raccomandazioni (da verificare con test)

| Scenario | Valore |
|-----------|----------|
| Sprint | 5-10 |
| HIIT | 10-15 |
| Threshold | 15-20 |
| Fondo | 20-40 |

---

## Downsampling a 1 Hz

Alcuni dispositivi registrano a:

```text
2 Hz
4 Hz
10 Hz
```

PELT non necessita di una frequenza elevata.

Ridurre a:

```text
1 campione al secondo
```

offre:

- Minore rumore.
- Elaborazione più veloce.
- Segmentazione più stabile.

---

## `model`

```python
model = "l2"
```

Definisce la funzione costo utilizzata da PELT.

---

### `model="l2"`

Minimizza:

```math
Σ(xᵢ − x̄)²
```

Assume che il cambiamento principale sia una variazione della media.

È generalmente il modello migliore per dati di potenza.

#### Esempio

```text
150W
150W
150W

↓

300W
300W
300W
```

---

### `model="l1"`

Minimizza:

```math
Σ|xᵢ − median|
```

Più robusto agli outlier.

Utile in presenza di:

- Spike del sensore.
- Errori di registrazione.
- Dati sporchi.

---

### `model="rbf"`

Utilizza kernel gaussiani.

Può rilevare:

- Cambi di media.
- Cambi di varianza.
- Cambi di distribuzione.

Più potente ma più costoso computazionalmente.

---

### Quando usare ciascun modello

| Modello | Utilizzo |
|----------|-----------|
| l2 | Default, va bene quasi sempre |
| l1 | Dati rumorosi, da meno importanza agli spike |
| rbf | Analisi avanzate, da fixare in alcuni file |

---

## `penalty`

```python
penalty = 10
```

È il parametro più importante dell'intera pipeline.

Controlla quanti breakpoint vengono generati.

---

### Penalty bassa

```python
penalty = 2
```

Effetto:

- Molti breakpoint.
- Segmentazione molto dettagliata.
- Possibile over-segmentation.

---

### Penalty alta

```python
penalty = 50
```

Effetto:

- Pochi breakpoint.
- Segmentazione conservativa.
- Possibile perdita di dettagli.

---

### Valori tipici (da verificare con test. Valori inferiori a 10 hanno dato buoni riscontri)

| Penalty | Effetto |
|-----------|-----------|
| 1-5 | Molti segmenti |
| 5-15 | Bilanciato |
| 15-30 | Conservativo |
| >30 | Molto conservativo (inutilizzabile?) |

---

## `min_segment_sec`

```python
min_segment_sec = 15
```

Passato a PELT come:

```python
min_size
```

### Significato

Nessun segmento può essere più corto di questa durata.

---

### Effetti

#### Valore basso

```python
5
```

- Maggiore dettaglio.
- Rileva sprint brevi.
- Più rumore.

#### Valore alto

```python
30
```

- Segmentazione più stabile.
- Meno frammentazione.
- Ignora eventi brevi.

---

## `min_cp_pct`

```python
min_cp_pct = 100
```

Utilizzato dopo la segmentazione.

Classifica i segmenti come:

- Above CP
- Below CP

Formula:

```math
Power%CP = (Power / CP) × 100
```

---

### Esempio

CP = 300W

Segmento:

```text
330W
```

```math
330 / 300 = 110%
```

Above CP.

---

Segmento:

```text
270W
```

```math
270 / 300 = 90%
```

Below CP.

---

### Valori tipici

| Obiettivo | % CP |
|------------|-------|
| Endurance | 70-85 |
| Sweet Spot | 85-95 |
| Threshold | 95-105 |
| VO₂max | 105-120 |
| Anaerobic | >120 |

---

## `merge_gap_sec`

```python
merge_gap_sec = 30
```

Utilizzato dopo la classificazione.

Permette di unire due segmenti se il recupero tra essi è breve.

---

### Esempio

```text
300W per 120 s

20 s recupero

295W per 100 s
```

Poiché:

```text
20 ≤ 30
```

i segmenti possono essere uniti.

---

### Obiettivo

Evitare che micro-recuperi interrompano artificialmente un effort continuo.

---

## `merge_power_diff_pct`

```python
merge_power_diff_pct = 15
```

Seconda condizione necessaria per il merge.

Formula:

```math
ΔPower = |P₁ − P₂| / P₁ × 100
```

---

### Esempio

```text
300W
330W
```

Differenza:

```text
10%
```

Merge consentito.

---

```text
300W
400W
```

Differenza:

```text
33%
```

Merge negato.

---

### Obiettivo

Evitare di fondere intervalli fisiologicamente e meccanicamente differenti.

---

## `min_effort_sec`

```python
min_effort_sec = 60
```

Filtro finale.

Scarta gli effort troppo brevi.

---

### Esempio

```text
35 s @ 320W
```

Scartato.

---

```text
90 s @ 320W
```

Mantenuto.

---

### Obiettivo

Ridurre i falsi positivi.

---

## `opener_threshold_pct`

```python
opener_threshold_pct = 200
```

Eccezione alla regola precedente.

Permette di mantenere effort brevi ma molto intensi.

Formula:

```math
Power ≥ CP × 2
```

---

### Esempio

CP = 300W

```text
650W per 15 s
```

```math
650 / 300 = 217%
```

L'effort viene mantenuto nonostante sia più corto di `min_effort_sec`.

---

# Interazione tra Parametri

## Troppi Effort

Sintomi:

- Molti segmenti.
- Workout frammentato.

Possibili soluzioni:

```python
penalty += (raro)
smooth_window_sec += 
min_segment_sec += 
```

---

## Pochi Effort

Sintomi:

- Intervalli fusi insieme.

Possibili soluzioni:

```python
penalty -= (raro)
smooth_window_sec -=
min_segment_sec -=
```

---

## Aperte brevi Non Rilevate ma desiderate in analisi

Possibili soluzioni:

```python
smooth_window_sec -=
min_segment_sec -=
opener_threshold_pct -=
```

---

## Intervalli Spezzati

Possibili soluzioni:

```python
merge_gap_sec +=
merge_power_diff_pct +=
```

---

# Configurazioni Consigliate (PER ORA SOLO TEMPLATE, DA OSSERVARE)

## Fondo / Endurance

```python
model = "l2"
penalty = 15
smooth_window_sec = 30
min_segment_sec = 30
min_cp_pct = 85
```

---

## Threshold

```python
model = "l2"
penalty = 10
smooth_window_sec = 20
min_segment_sec = 15
min_cp_pct = 95
```

---

## VO₂max

```python
model = "l2"
penalty = 8
smooth_window_sec = 10
min_segment_sec = 10
min_cp_pct = 110
```

---

## Sprint

```python
model = "l2"
penalty = 5
smooth_window_sec = 5
min_segment_sec = 3
sprint_threshold_pct = 180
```

---

# Limiti dell'Approccio

PELT è un segmentatore statistico.

Non conosce:

- FTP
- Critical Power
- Zone di allenamento
- VO₂max
- W′
- Fisiologia dell'atleta

Identifica esclusivamente cambiamenti nella struttura del segnale.

L'interpretazione fisiologica viene introdotta successivamente attraverso:

- `min_cp_pct`
- Regole di merge
- Filtri finali

Per questo motivo la qualità finale degli effort dipende sia dalla segmentazione sia dalle regole di business applicate successivamente.

---

# Conclusioni

I parametri con il maggiore impatto pratico sono:

1. **`penalty`** → numero di segmenti generati.
2. **`smooth_window_sec`** → quantità di rumore percepita.
3. **`min_segment_sec`** → durata minima rilevabile.
4. **`min_cp_pct`** → classificazione fisiologica degli effort.
5. **`merge_gap_sec`** → aggressività del merge temporale.
6. **`merge_power_diff_pct`** → aggressività del merge per intensità.
7. **`min_effort_sec`** → filtro minimo di durata.
8. **`opener_threshold_pct`** → eccezione per sforzi esplosivi.

In PEFFORT, PELT agisce come **motore di segmentazione statistica**, mentre le regole successive trasformano tali segmenti in **effort ciclistici fisiologicamente significativi e interpretabili dall'utente finale**.