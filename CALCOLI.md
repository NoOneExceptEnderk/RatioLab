# Calcoli nominali e riferimenti tecnici

Revisione del 23 ottobre 2026. Le formule sono state implementate nel progetto, senza copiare codice o tavole dai riferimenti. `engineering.py` contiene i calcoli; `geometry.py`, `assemblies.py` e `geartrains.py` producono le geometrie.

## Convenzioni

Quote in mm, forze in N, coppia in N·m, velocità in rpm e potenza in W. Il rapporto firmato è **i = n ingresso / n uscita**: negativo significa versi opposti. La coppia d’uscita è riportata come modulo, non come vettore di reazione.

Il rendimento è un dato ipotizzato dall’utente, non un risultato del modello. Non sono implementati dimensionamento a fatica, pressione hertziana, verifiche ISO 6336/AGMA, durata dei cuscinetti o simulazione elastica. Quindi una coppia impostata non rappresenta una coppia ammissibile. Harmonic e vite-corona restano studi geometrici.

## Dentature cilindriche: geometria normale e trasversale

Per elicoidali e doppia elica il modulo e l’angolo di pressione immessi sono **normali**:

```
mt = mn / cos β
αt = atan(tan αn / cos β)
d = z mt
db = d cos αt
da = d + 2 mn (ha* + x)
df = d − 2 mn (hf* − x)
sn = mn (π/2 + 2 x tan αn)
```

Per i denti diritti β = 0. L’addendum e il dedendum usano mn, anche negli elicoidali: la revisione precedente usava erroneamente mt nelle altezze. Per una corona non corretta, il diametro di testa interno è d − 2mn e il diametro di fondo è d + 2,5mn.

Fonte industriale: [HPC Europe, Precision gears — Technical information, pagina 132](https://hpceurope.com/docFichesTechniques/PrecisionGears.pdf). La correzione x e i coefficienti ha*/hf* sono disponibili per gli ingranaggi singoli. Nelle nuove coppie esterne x1 = x e x2 = −x: la somma nulla conserva l’interasse teorico, pur modificando spessori e altezze. Per planetary, corone interne e studi non si espone una correzione indipendente che renderebbe incompatibili le coppie.

Il gioco tangenziale impostato è il gioco totale nominale della coppia, ripartito fra le due ruote. Il profilo evolvente ha un raccordo al piede semplificato: x non genera automaticamente il raccordo trocoidale dell’utensile.

## Contatto e interasse

Per coppie esterne bilanciate si può aumentare l’interasse di lavoro:

```
a0 = (d1 + d2)/2
αw = acos(a0 cos αt / a)
g1 = sqrt(ra1² − rb1²)
g2 = sqrt(ra2² − rb2²)
εα = (g1 + g2 − a sin αw) / (π mt cos αt)
εβ = b attiva |sin β| / (π mn)
ε totale = εα + εβ
Δj = 2a [inv(αw) − inv(αt)], dove inv(α) = tan α − α
j lavoro = j nominale × a/a0 + Δj
```

Per una coppia interna a0 = (d2 − d1)/2 e il numeratore di εα diventa g1 − g2 + a sin αw; ra2 è il raggio di testa interno. I calcoli assumono che il tratto attivo arrivi alla testa: sottotaglio, smussi e raccordi possono ridurlo. Non sono un’analisi del contatto sotto carico. Fonte: [Drivetrain Hub, Geometry / Helical Gears, sezioni Gear Mesh e Contact Ratio](https://drivetrainhub.com/notebooks/gears/geometry/Chapter%203%20-%20Helical%20Gears.html).

Il generatore rifiuta ricoprimento totale < 1 e interferenza evolvente nelle nuove coppie. Nella doppia elica b attiva è **(larghezza − gola)/2**, anche se la gola è zero: le due metà non sono trattate come un’unica elica continua. Δj è aggiuntivo rispetto al gioco già impostato.

## Sottotaglio e interferenza interna

La condizione indicativa da dentiera standard è x minimo = ha* − zv sin²αn / 2, con zv = z per denti diritti e zv ≈ z/cos³β per elicoidali. Il controllo con denti virtuali è un’approssimazione di progetto; non sostituisce la generazione dell’utensile. Fonte per il limite standard e il ruolo della correzione: [KHK, Technical Data, sezioni 3.5–3.6](https://d2t1xqejof9utc.cloudfront.net/files/227482/gear_guide1.pdf?1634738312=).

Nelle nuove coppie interne si richiede differenza denti > 9, oltre al controllo del cerchio di base. Questo è un filtro conservativo del generatore; la nota KHK sul limite 9 riguarda dentature standard a 20°, non costituisce una garanzia per altri angoli. Interferenza di taglio e profilo dell’utensile restano da verificare. Fonte: [KHK, Internal ring gears — design and considerations](https://khkgears.us/media/beqhhrye/gear-solutions_khk_internal-ring-gears-design-and-considerations.pdf).

Il vecchio preset planetary 18/18/54 diritto può entrare nella zona sotto il cerchio di base nella coppia satellite-corona. È conservato per compatibilità, con avviso esplicito e ricoprimento teorico nel report. Non è dichiarato privo di interferenze. Una combinazione 24/24/72 evita questo specifico avviso e conserva il rapporto 4:1; non è per questo un progetto dimensionato a resistenza.

## Cinematica e forze

```
Coppia esterna: i = −z2/z1
Coppia interna ad assi fissi: i = +z2/z1
Composto a due stadi esterni: i = (z2/z1)(z4/z3)
Planetary corona fissa: i = 1 + zr/zs
P ingresso = T ingresso × n ingresso × 2π/60
n uscita = n ingresso / i
|T uscita| = T ingresso × |i| × η complessivo
Ft = 2000 |T| / d lavoro
Fr = Ft tan αw
Fa = Ft tan β
```

Nel composto, η stadio = √η complessivo è un’ipotesi esplicita per stimare la coppia intermedia. La variante coassiale richiede interassi uguali; gli alberi ingresso e uscita sono separati assialmente. Le due ruote intermedie devono essere solidali, ma il collegamento meccanico non è ancora progettato. Fonti didattiche: [JNTUA/JNTUK, Gear Trains, lezioni del prof. N. Mohan Rao](https://www.jntua.ac.in/gate-online-classes/registration/downloads/material/a159033042164.pdf), [University of Arkansas, Introduction to Mechanical Design and Manufacturing — Gearing Systems](https://uark.pressbooks.pub/mechanicaldesign/chapter/gearing-systems/). Quest’ultima usa talvolta il reciproco come convenzione del rapporto; qui è sempre esplicitato i = n ingresso/n uscita.

Le forze sono riferimenti nominali sulla ruota motrice, non reazioni complete dei supporti. Fr e Ft sono moduli; il segno Fa segue la mano di riferimento del pignone e non determina da solo la direzione della reazione nel montaggio. Per doppia elica il valore Fa è il riferimento conservativo a piena coppia di un’elica singola; la cancellazione complessiva richiede carichi simmetrici. Esempio di controprova: T = 100 N·m, d = 40 mm, αw = 21,515° → Ft = 5000 N, Fr ≈ 1971,1 N. Fonte: [Drivetrain Hub, Strength / Force Analysis](https://drivetrainhub.com/notebooks/gears/strength/Chapter%201%20-%20Force%20Analysis.html).

Per il planetary sono conservate le condizioni di coassialità, equispaziamento e distanza fra satelliti. Sono riportati i ricoprimenti solare-satellite e satellite-corona di ogni stadio; non si inventa una ripartizione del carico dividendo semplicemente la coppia per il numero di satelliti. Riferimento: [Drivetrain Hub, Geometry / Planetary Gears](https://drivetrainhub.com/notebooks/gears/geometry/Chapter%204%20-%20Planetary%20Gears.html).

## Cicloidale

Il profilo resta l’offset normale interno della traiettoria dei centri dei rulli. Si distinguono **gioco del profilo**, **gioco dei fori uscita**, **gioco assiale del montaggio** e **distanza fra i due dischi**. Il foro uscita ha raggio r perno + eccentricità + gioco uscita. Se una vecchia configurazione non specifica i nuovi valori, si usano rispettivamente il vecchio gioco del profilo e il vecchio gioco assiale.

Il campionamento adattivo confronta metà e quarti di ogni intervallo con la corda. È una soglia numerica, non una tolleranza di fabbricazione né un limite globale dimostrato. Il controllo di curvatura usa almeno 4096 campioni e un margine del 2% contro le cuspidi dell’offset; non è una prova analitica di assenza di cuspidi per qualunque parametro. Il rapporto è −(N rulli − 1).

La distinzione dei giochi è motivata da [Chen et al., ASME Journal of Mechanical Design, 2017, Analysis of a Cycloid Speed Reducer Considering Tooth Profile Modification and Clearance-Fit Output Mechanism](https://doi.org/10.1115/1.4035541). Le modifiche normali del profilo sono discusse in [A New Tooth Profile Modification Method of Cycloidal Gears in Precision Reducers for Robots, Applied Sciences 2020](https://www.mdpi.com/2076-3417/10/4/1266). Non è implementata la loro ottimizzazione né il modello di ripartizione elastica: il solo gioco non permette di stimare stress o precisione sotto carico.

## Vite e strain wave

Nello studio vite-corona **m è assiale della vite**, non normale: avanzamento L = π m principi, γ = atan(m principi / d vite), mn = m cos γ, αn = atan(tan αassiale cos γ). La ruota approssimata usa mn e β = γ, mantenendo il diametro primitivo m z. Sono selezionabili mano della vite e foro indipendente della ruota. Fonte: [KHK, Calculation of gear dimensions, sezione Worm Gear Pairs](https://khkgears.net/gear-knowledge/gear-technical-reference/calculation-gear-dimensions/?ad=semD&am=broad&an=msn_s&askid=d51ae89b-b1e4-4e19-a5c3-c9a2931dd7a0-0-ab_msb&l=sem&o=29593&q=bevel+gear+tooth+profile&qsrc=999). Non si deducono rendimento o irreversibilità dalla sola geometria.

Per lo strain wave a due lobi resta differenza di due denti: i = −z flex/2 con corona fissa, oppure i = +(z flex+2)/2 con flexspline fisso e uscita corona. La revisione successiva include coppa e cuscinetto sagoma, con una linea primitiva ellittica a perimetro numerico conservato. Il fattore d’onda modifica la deformazione illustrativa; non è una soluzione elastica né un profilo coniugato. Dettagli in [VARIANTI.md](VARIANTI.md). Riferimento del principio cinematico: [Harmonic Drive Systems, Principle of HarmonicDrive](https://www.hds.co.jp/english/products/hd_theory/).

## Consultazione ed esportazione

**Configurazioni e file → Relazione di calcolo** mostra i risultati e gli avvisi. Ogni esportazione della distinta produce anche `.calcoli.txt` e `.calcoli.json`. Il JSON della distinta e i metadati del gruppo CAD conservano la sezione `analysis`. I dati di esercizio sono raccolti nel pannello espandibile **Esercizio e carichi** e non modificano la geometria.


## Schemi cinematici

Il rapporto è ingresso/uscita. Planetary, cicloidale e strain wave risolvono le sei permutazioni dei membri con velocità nulla del membro fissato. Il planetary bistadio propaga velocità e segno tra i due stadi. Le coppie ad assi paralleli, a corona interna e vite consentono l’inversione di ingresso e uscita; per la vite questo non garantisce la retroazionabilità. Vedi [MODELLI-IO.md](MODELLI-IO.md).
