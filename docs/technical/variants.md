# Doppia elica, viti cilindriche e strain wave

Dimensional geometry and ideal motion; no strength or production-readiness certification of a complete reducer.

## Doppia elica: unite e separate

- **Eliche unite**: gola zero, le due mani si incontrano al centro. Un solo corpo continuo.
- **Eliche separate**: gola centrale regolabile e mozzo continuo sotto la gola. Un solo corpo, non due ingranaggi disconnessi.

Per l’ingranaggio singolo si sceglie direttamente la variante. Per planetary, bistadio planetary, assi paralleli, composto e corona interna, il menu **Costruzione doppia elica** appare quando è selezionata una dentatura doppia.

La gola è nascosta e forzata a zero nelle eliche unite; deve essere positiva nelle separate. I vecchi JSON con `gap: 0` vengono riconosciuti come uniti e quelli con gola positiva come separati. Il ricoprimento assiale continua a usare la larghezza di una singola metà attiva, senza contare la gola come dentatura. La cancellazione della spinta assiale richiede una ripartizione simmetrica del carico.

## Cylindrical worm: ZA and ZI

ZA retains straight axial screw flanks; ZI retains a transverse involute screw.
The wheel now uses the matching helicoid envelope, including the swept hob-tip
root transition and backlash, rather than a helical-gear surrogate. Both hands,
1–4 starts, separate bores and optional journals remain available. Unsupported
or unresolved geometries are rejected explicitly.

See the [worm equations, original references, supported domain and numerical
validation](worm.md). The ideal rigid generated envelope and discrete clearance
checks do not certify a manufactured transmission, strength or self locking.

## Strain wave: cup, flat cup e silk hat

La geometria precedente era un semplice anello deformato. Ora sono disponibili:

- **Cup**: corpo a coppa con diaframma anulare sul fondo.
- **Flat cup**: stessa architettura a coppa, con lunghezza iniziale ridotta e regolabile.
- **Silk hat**: corpo aperto con flangia anulare rivolta verso l’esterno.

Cup e flat cup includono un foro di uscita indipendente da quello della camma. Silk hat consente di scegliere la larghezza radiale della flangia. Il corpo flessibile è sempre **un unico solido** comprendente parete, diaframma/flangia e fascia dentata; la sezione passa gradualmente da circolare a deformata. Spessore parete, lunghezza corpo e spessore diaframma/flangia sono distinti.

Queste architetture sono documentate nei [modelli ufficiali Harmonic Drive Systems: CSF, CSD e SHF](https://www.hds.co.jp/english/products/model/). I nomi descrivono l’architettura; non vengono riprodotte quote di uno specifico prodotto commerciale o assegnati codici d’ordine.

L’ellisse primitiva usa a = rp + ampiezza; b è risolto numericamente affinché il perimetro sia 2πrp. La verifica indipendente usa 4096 punti. Il passo dei denti è ora uniforme sull’arco della linea primitiva, risolvendo l’integrale della velocità ellittica con otto armoniche e inversione di Newton. Gli offset radiali del profilo di riferimento diventano offset sulla normale locale all’ellisse, orientando i denti. La transizione assiale interpola la mappa circolare e quella ellittica; il moto usa identiche coordinate materiali immutabili e coefficienti nello shader. Il dominio numericamente verificato è q=(a²−b²)/(a²+b²)≤0,25. The ring is generated from the matching complete tooth sweep under this map; perimeter and pitch conservation alone are not its conjugacy check. Deformation remains prescribed, without an elastic solution.

Il generatore d’onda e l’involucro del suo cuscinetto seguono il vano deformato con spessore e giochi radiali espliciti. Il cuscinetto è classificato come **sagoma da definire**, non come acquisto di catalogo. The flexible tooth reference is mapped with the local ellipse normal; the rigid ring uses its full generated outer swept envelope, including all branches and corners. Reference backlash and derived numerical enclosure relief are reported separately. This does not reproduce an industrial S-tooth profile or establish fatigue capacity. See [the equations, original references, sampled verification and remaining limits](strain-wave.md).

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
