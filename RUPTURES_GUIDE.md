# PEFFORT — Guida al sistema Ruptures

## Cosa è cambiato rispetto alla versione precedente

La versione precedente rilevava gli effort tramite **finestre mobili**: si scorreva il segnale di potenza con una finestra di N secondi, si calcolava la media, e si etichettava come "effort" ogni finestra sopra soglia. Il risultato dipendeva molto dalla larghezza della finestra e da parametri di merge/extend difficili da intuire.

La nuova versione usa **changepoint detection** (libreria `ruptures`): il segnale stesso decide dove cambia stato. Non c'è finestra da impostare — ci sono soglie di sensibilità.

---

## Come funziona ruptures

### Il concetto di changepoint

Un *changepoint* è un istante in cui le proprietà statistiche del segnale cambiano in modo significativo. Per la potenza ciclistica, è il momento in cui passi da pedalata tranquilla a sforzo, o viceversa.

```
Potenza (W)
320 │        ╔══════╗              ╔═════════╗
270 │        ║      ║              ║         ║
220 │        ║      ║    ╔════╗    ║         ║
150 │────────╝      ╚════╝    ╚════╝         ╚────
     0      500    1500  2000 3000 5000      6000   t (s)
              ↑      ↑    ↑    ↑    ↑         ↑
           bkp    bkp  bkp  bkp  bkp        bkp   ← breakpoints
```

### Algoritmo: Pelt

`ruptures` usa l'algoritmo **Pelt** (Pruned Exact Linear Time). Data la sequenza di potenza, trova la suddivisione in segmenti che minimizza un costo totale più una penalità per ogni segmento aggiunto:

```
costo totale = Σ costo(segmento_i) + penalty × numero_segmenti
```

- **Costo basso** = segmento omogeneo (poca varianza interna)
- **Penalty alta** = preferisce pochi segmenti lunghi
- **Penalty bassa** = tollera molti segmenti corti

---

## Parametri del form — spiegazione dettagliata

### Modello (`ruptures_model`)

Definisce come si misura la "distanza" tra un punto e la media del suo segmento.

| Modello | Formula | Quando usarlo |
|---------|---------|---------------|
| **l2** | varianza dei residui | sempre come punto di partenza, velocissimo |
| **rbf** | kernel gaussiano | quando il segnale ha distribuzioni non-gaussiane (es. sprint frequenti), ma è lento su file lunghi |
| **l1** | mediana dei residui assoluti | quando ci sono molti outlier (es. picchi di potenza isolati), molto lento |

**Consiglio pratico:** usa `l2` sempre. Passa a `rbf` solo se vedi troppi segmenti spuri su tratti con molte variazioni brevi.

**Perché l2 è molto più veloce?**  
`l2` ha complessità O(n log n). `rbf` costruisce una matrice kernel O(n²) in memoria — su 10 000 campioni occupa ~800 MB e richiede minuti.

---

### Penalty

Il parametro più importante. Controlla la granularità della segmentazione.

```
penalty bassa (es. 3)          penalty alta (es. 30)
─────────────────────          ─────────────────────
│ seg1 │seg2│ seg3 │ ...       │    segmento 1      │ ...
 molti segmenti corti           pochi segmenti lunghi
 rischio: over-segmentation     rischio: effort fusi insieme
```

**Come scegliere:**

| Tipo di uscita | Penalty consigliata |
|----------------|---------------------|
| Gara / criterium con cambi rapidi | 3 – 8 |
| Allenamento strutturato (intervalli) | 8 – 15 |
| Fondo / gran fondo | 15 – 30 |
| Vuoi vedere solo i blocchi principali | > 30 |

Inizia sempre con **10** e regola in base a quanti segmenti vedi nell'altimetria.

---

### Durata minima segmento (`ruptures_min_seg`, secondi)

Segmenti più corti di questo valore vengono ignorati **anche se sopra soglia**. Serve a filtrare i micro-cambiamenti di potenza (accelerazioni brevi, semafori, vento in faccia per 10 secondi).

- **Default: 30 s** — filtra tutto ciò che dura meno di mezzo minuto
- Per vedere anche gli scatti in salita: abbassa a 10–15 s
- Per vedere solo blocchi strutturati: alza a 60–120 s

---

### Smoothing pre-detection (`ruptures_smooth`, secondi)

Prima di passare il segnale a ruptures, viene applicata una **media mobile centrata** di questa durata. Riduce i picchi istantanei di potenza che altrimenti genererebbero falsi breakpoints.

```
Segnale raw:     ─/\/\/\──────────────/\/\/\─
                  noise  ↑ vero effort ↑ noise

Segnale smooth:  ─────────────────────────────
                         ╔═══════════╗
                         ║           ║         ← solo il cambio vero
```

- **Default: 15 s** — buono per la maggior parte dei casi
- Abbassare a 5 s: più reattivo, più breakpoints da rumore
- Alzare a 30 s: solo cambiamenti di stato lenti/netti
- **0**: nessun smoothing (sconsigliato su FIT con rumore sensore)

---

### Soglia intensità (% CP)

Dopo che ruptures ha segmentato il segnale, ogni segmento viene classificato:

```
media_potenza_segmento ≥ CP × (min_cp_pct / 100)  →  EFFORT (mostrato)
media_potenza_segmento  <  soglia                   →  ignorato (resto/facile)
```

Con CP=280 W e soglia=100%:
- segmento a 295 W media → **effort** ✓
- segmento a 260 W media → scartato

**Esempi:**
- `100%` = solo segmenti almeno a CP (zona 4+)
- `80%`  = include anche zone 3 (Tempo)  
- `120%` = solo segmenti in zona VO2max+
- `50%`  = quasi tutto (utile per capire la struttura completa della gara)

---

## Pipeline completa — dall'upload all'effort

```
FIT file
   │
   ▼
parse_fit()                   ← legge tutti i record (potenza, GPS, HR, quota)
   │  DataFrame: 10264 righe
   ▼
smooth (rolling mean 15s)     ← riduce rumore sensore
   │
   ▼
downsample a 1 Hz             ← se FIT è a 4Hz: 40000 → 10000 campioni
   │                             mantiene precisione per effort ≥ 30s
   ▼
Pelt(model, min_size, pen)    ← trova breakpoints nel segnale
   │  lista di indici temporali
   ▼
remap → indici originali      ← breakpoint in spazio downsampled → riga df
   │
   ▼
filtra per soglia % CP        ← scarta segmenti troppo facili
   │
   ▼
List[(start, end, avg_power)] ← identico all'output della versione precedente
   │
   ├──→ altimetria_d3
   ├──→ map2d
   ├──→ map3d
   └──→ inspection
```

Il downsampling è il passaggio chiave per la performance: ruptures lavora su ~10 000 campioni invece di 40 000+, riducendo il tempo da minuti a meno di 1 secondo.

---

## Sprint detection — invariata

Gli sprint vengono ancora rilevati con soglia fissa:

```
power[t] ≥ sprint_min_power  per almeno sprint_min_duration secondi
```

Questa logica è deliberatamente separata dalla changepoint detection perché gli sprint sono eventi brevi e ad alta intensità dove la forma del cambiamento è meno importante della sua entità assoluta.

---

## Tuning rapido

**Vedo troppi segmenti spezzettati:**
→ alza penalty (da 10 a 20–30) o alza smooth (da 15 a 25)

**Vedo troppo pochi effort, effort lunghi che includono recupero:**
→ abbassa penalty (da 10 a 5) o abbassa soglia % CP

**Il segnale sembra "sporco" con breakpoints su ogni piccola variazione:**
→ alza smooth a 20–30 s

**Voglio vedere anche le salite in zone 3:**
→ abbassa soglia % CP a 75–80

**Il parsing è lento (>3 secondi):**
→ usa sempre modello `l2`, mai `rbf` su file >1 ora
