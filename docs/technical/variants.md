# Doppia elica, viti cilindriche e strain wave

Revisione del 23 ottobre 2026. Modelli dimensionali e di studio; nessuna certificazione di resistenza o producibilità del riduttore completo.

## Doppia elica: unite e separate

- **Eliche unite**: gola zero, le due mani si incontrano al centro. Un solo corpo continuo.
- **Eliche separate**: gola centrale regolabile e mozzo continuo sotto la gola. Un solo corpo, non due ingranaggi disconnessi.

Per l’ingranaggio singolo si sceglie direttamente la variante. Per planetary, bistadio planetary, assi paralleli, composto e corona interna, il menu **Costruzione doppia elica** appare quando è selezionata una dentatura doppia.

La gola è nascosta e forzata a zero nelle eliche unite; deve essere positiva nelle separate. I vecchi JSON con `gap: 0` vengono riconosciuti come uniti e quelli con gola positiva come separati. Il ricoprimento assiale continua a usare la larghezza di una singola metà attiva, senza contare la gola come dentatura. La cancellazione della spinta assiale richiede una ripartizione simmetrica del carico.

## Vite senza fine: ZA e ZI

Sono implementate due famiglie geometriche reali:

| Variante | Definizione del fianco della vite |
|---|---|
| Cilindrica ZA | Rettilineo nella sezione assiale; sezione trasversale a spirale di Archimede |
| Cilindrica ZI | Evolvente nella sezione trasversale; superficie elicoidale evolvente |

Riferimenti: [Gear Technology, Ask the expert — Worm gears, descrizione delle forme DIN 3975](https://www.geartechnology.com/ext/resources/issues/1013x/worm_gears.pdf) e [Litvin e Fuentes, Gear Geometry and Applied Theory, capitolo Worm-Gear Drives with Cylindrical Worms, estratto tecnico](https://www.globalspec.com/reference/62679/203279/html-head-chapter-19-worm-gear-drives-with-cylindrical-worms). È consultata la descrizione pubblica del capitolo, non dichiarata la lettura dell’intero libro.

Il vecchio profilo trasversale era una stella con raccordi approssimati. Ora la ZA viene ricavata dalla condizione sul fianco assiale. Con modulo assiale mx, numero principi s, raggio primitivo rp, gioco assiale totale j e k = mx s/2:

```
Avanzamento L = π mx s
γ = atan(mx s / d vite)
mn = mx cos γ
αn = atan(tan αassiale cos γ)
θ mezzo dente(r) = π/(2s) − (r − rp) tan αassiale / k − j/(4k)
```

Un’intersezione a piano assiale fisso soddisfa x = −kθ: il fianco ha quindi pendenza dx/dr = tan αassiale. Lo spessore assiale primitivo di ciascuna vite è πmx/2 − j/2. Il gioco nominale della coppia è ripartito fra vite e ruota.

Per la ZI si usa un’evolvente trasversale di modulo d vite/s e angolo trasversale ricavato da β vite = 90° − γ. Il gioco trasversale equivalente della vite è j/tan γ; non è uguale al gioco assiale j. Le altezze radiali sono mx e 1,25mx nella convenzione assiale adottata. Non è una certificazione della geometria completa secondo DIN/ISO.

La mano sinistra è una riflessione della destra, comprese le diagonali della triangolazione, sia sulla vite sia sulla ruota: le due versioni hanno lo stesso volume numerico. Con vite sull’asse +X, ruota sull’asse +Z e centro ruota sul semiasse Y negativo, i=mano×z/principi: la mano sinistra inverte il verso ruota anche nell’animazione e nei port cinematici. Le facce sono condivise fra preview e STEP. Sono disponibili 1–4 principi, mano, foro vite e foro ruota indipendenti, lunghezza del filetto, diametro e lunghezza dei codoli. I codoli si possono eliminare impostandone la lunghezza a zero; devono altrimenti stare fra foro e fondo filetto con materiale residuo.

Il limite precedente di quattro giri è sostituito da un limite di complessità di 250000 facce. Il passo angolare della vite è scelto per una freccia nominale massima di 0,02 mm; la discretizzazione non coincide con una tolleranza di lavorazione.

**La ruota ha ora una gola dall’inviluppo del cilindro di testa vite, con fianchi elicoidali approssimati.** Δ(z)=Rw−sqrt(Rw²−z²), Rw=d vite/2+mx; il dominio richiede metà larghezza <0,95Rw. Si discretizza la gola con soglia di corda assiale 0,01 mm. Questo migliora la superficie effettiva della ruota ma non risolve l’inviluppo coniugato del filetto/hob. La vite ha ora il profilo geometrico dichiarato, ma la coppia completa rimane uno studio: contatto, interferenze e utensile della ruota devono ancora essere risolti. Il programma non deduce irreversibilità o rendimento dalla sola geometria.

Esistono anche ZN, ZK, ZC e soluzioni globoidali/doppio avvolgimento. Sono documentate, ma non esposte come varianti generate: richiedono definizione dell’utensile o superfici e ruote coniugate dedicate. Riferimento sulle forme cilindriche: [Technology of Manufacturing of ZC Cylindrical Worm, descrizione dei tipi ZA/ZN/ZI/ZK/ZC](https://pdfs.semanticscholar.org/88c7/49b0b4fa5e9308bc700b2cebf16cdea6e61f.pdf).

## Strain wave: cup, flat cup e silk hat

La geometria precedente era un semplice anello deformato. Ora sono disponibili:

- **Cup**: corpo a coppa con diaframma anulare sul fondo.
- **Flat cup**: stessa architettura a coppa, con lunghezza iniziale ridotta e regolabile.
- **Silk hat**: corpo aperto con flangia anulare rivolta verso l’esterno.

Cup e flat cup includono un foro di uscita indipendente da quello della camma. Silk hat consente di scegliere la larghezza radiale della flangia. Il corpo flessibile è sempre **un unico solido** comprendente parete, diaframma/flangia e fascia dentata; la sezione passa gradualmente da circolare a deformata. Spessore parete, lunghezza corpo e spessore diaframma/flangia sono distinti.

Queste architetture sono documentate nei [modelli ufficiali Harmonic Drive Systems: CSF, CSD e SHF](https://www.hds.co.jp/english/products/model/). I nomi descrivono l’architettura; non vengono riprodotte quote di uno specifico prodotto commerciale o assegnati codici d’ordine.

L’ellisse primitiva usa a = rp + ampiezza; b è risolto numericamente affinché il perimetro sia 2πrp. La verifica indipendente usa 4096 punti. Il passo dei denti è ora uniforme sull’arco della linea primitiva, risolvendo l’integrale della velocità ellittica con otto armoniche e inversione di Newton. Gli offset radiali del profilo di riferimento diventano offset sulla normale locale all’ellisse, orientando i denti. La transizione assiale interpola la mappa circolare e quella ellittica; il moto usa identiche coordinate materiali immutabili e coefficienti nello shader. Il dominio numericamente verificato è q=(a²−b²)/(a²+b²)≤0,25. Conservare perimetro e passo non risolve elasticità o coniugazione.

Il generatore d’onda e l’involucro del suo cuscinetto seguono il vano deformato con spessore e giochi radiali espliciti. Il cuscinetto è classificato come **sagoma da definire**, non come acquisto di catalogo. I denti restano evolventi mappate di studio, con possibili interferenze; non riproducono il profilo industriale S tooth e non costituiscono un flexspline dimensionato a fatica.

### Due schemi cinematici

Con zf denti sul flexspline e zc = zf + 2 sulla corona, ingresso al generatore d’onda:

```
Corona fissa, uscita flexspline: i = zf / (zf − zc) = −zf/2
Flexspline fisso, uscita corona: i = zc / (zc − zf) = +(zf+2)/2
```

La geometria è la stessa; cambiano vincolo, uscita, rapporto firmato e relazione di calcolo. I vincoli sono descritti, senza creare giunti cinematici automatici nel CAD. Fonte: [Harmonic Drive LLC, Engineering Data, pagine 10–11 sui rapporti e configurazioni](https://global.harmonicdrive.net/_hd/content/documents1/CSG-CSF_GearUnits.pdf).

**Pancake non è un sinonimo di flat cup**: è un’architettura distinta con due circular spline. È documentata nella stessa fonte, ma non viene simulata rinominando una coppa corta. Non è inclusa nelle varianti di questa revisione.

## Verifiche e file

Test: `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test*.py'`. Sono controllati profili ZA, spessori, mani speculari, continuità, limiti dei codoli, perimetro d’onda, rapporti, giochi e identità delle facce preview/STEP anche per ZI sinistra e silk hat. La distinta tiene conto delle sezioni assiali nel codice del pezzo e nell’ingombro, per distinguere flange di dimensioni diverse.

Configurazioni in [`examples/`](../../examples/). Distinte, relazioni e documenti CAD vengono creati nella cartella di esportazione scelta dall’utente. Per carichi nominali, unità e limiti generali vedere [CALCULATIONS.md](calculations.md).
