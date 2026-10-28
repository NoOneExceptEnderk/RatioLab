# Hardware standard e lavorazioni collegate

Nel pannello **Hardware e montaggio** scegli **Montaggio con componenti standard**. Puoi attivare separatamente Seeger, linguette, viteria e rasamenti, scegliere M3/M4/M5/M6 e lo spessore dei rasamenti. Le configurazioni precedenti conservano il comportamento senza hardware aggiuntivo.

## Cosa viene generato

| Categoria | Componenti acquistabili | Lavorazioni / comportamento |
|---|---|---|
| Seeger esterni | Springmasters EXT0060, EXT0080, EXT0100, EXT0120, per alberi nominali 6/8/10/12 mm | Gola con diametro, larghezza e margine di estremità collegati alla scheda del componente |
| Seeger interni | American Ring DIN472-013/016/019/022/026/028/030/032 | Due gole nella sede di ciascun cuscinetto di catalogo; larghezze e spessori delle parti vengono aumentati quando serve |
| Linguette | Designazioni DIN 6885-1 B: sezioni 2×2, 3×3, 4×4 mm; lunghezza scelta in base allo spazio | Cava localizzata nell’albero; cava passante nel mozzo collegato. Estremità piane, senza assegnare automaticamente una classe di accoppiamento |
| Viti e dadi | ISO 4762 M3–M6, dadi ISO 4032 e rondelle ISO 7089 | Quattro collegamenti passanti tra flange/coperchi esterni, con distanziali tubolari. Lunghezza calcolata sulla presa, rondelle, dado e sporgenza di almeno due passi |
| Rasamenti | KIPP K1151, DIN 988; spessori 0,1 / 0,2 / 0,5 / 1 mm | Quote e quantità collegate agli arresti. Il diametro interno disponibile viene scelto per non interferire con l’albero |
| Distanziali tubolari | Parti da realizzare, con codice interno SC-… | Colmano gli spazi fra ingranaggio e anelli interni dei cuscinetti, mantengono i rasamenti fuori dagli occhielli dei Seeger, oppure separano le flange dei tiranti |

I dati sono in `catalogo-hardware.json`, con fonti e data di verifica. I codici Springmasters, American Ring e KIPP identificano le rispettive voci di catalogo. Le sigle DIN/ISO delle linguette e della viteria sono **designazioni dimensionali**, non SKU di un produttore: materiale, classe di resistenza e finitura devono ancora essere selezionati. Le lunghezze delle viti sono una serie nominale del generatore; disponibilità del prodotto completo da verificare presso il fornitore scelto.

Le gole interne seguono le quote del catalogo metrico American Ring indicato, comprese le cifre arrotondate pubblicate; non rappresentano una tabella DIN universale valida per qualsiasi fornitore. Il margine di estremità adottato dal generatore per queste gole è indicato nei dati ed è da verificare sotto carico. Non vengono copiate le capacità di carico di un anello su un’altra geometria.

## Applicazione ai modelli

- **Ingranaggio singolo, quote libere:** albero aggiunto, linguetta con cave su albero e ingranaggio, rasamenti e Seeger esterni. Per aggiungere la viteria del telaio scegli il modo cuscinetti **a supporto dell’albero**, che fornisce le due flange da collegare.
- **Ingranaggio con cuscinetti a supporto dell’albero:** cave e linguetta, Seeger interni nei portacuscinetti, arresti esterni, rasamenti e distanziali della catena assiale. La viteria collega i due portacuscinetti.
- **Ingranaggio con cuscinetto nel foro:** ritenuta dell’anello esterno nel mozzo e distanziali sull’albero. La linguetta fra quel mozzo e quell’albero viene omessa: il cuscinetto deve consentire la rotazione relativa.
- **Planetary:** cave e linguette fra alberi e solari, una per stadio quando lo spazio lo permette; cava e linguetta sull’estremità di uscita; arresti interni nei supporti/cuscinetti selezionati e fermo terminale dell’uscita. La ritenuta dei perni satelliti nelle flange resta esplicitamente da completare.
- **Cycloidal:** ritenuta interna dei cuscinetti selezionati, cava/linguetta e fermo sull’estremità di uscita, viteria del carter. Il collegamento definitivo di camme, perni e flangia viene ancora segnalato fra i requisiti aperti.

Linguette e Seeger esterni partono dai diametri nominali 6, 8, 10 e 12 mm. Se un albero non è coperto, il programma segnala la scelta mancante nella distinta senza inventare un codice. La linguetta B minima inclusa è lunga 8 mm e richiede almeno 9 mm di mozzo. La cava di uscita è un’interfaccia: il mozzo dell’accessorio da collegare non viene inventato.

La viteria passa **all’esterno dell’ingombro rotante**. Il generatore allarga le flange/coperchi e aggiunge quattro distanziali: il diametro complessivo aumenta ed è riportato nei risultati. Le teste sono sporgenti; non vengono dichiarati fori filettati o lamature che non esistono. I fori passanti adottano giochi diametrali di progetto: 0,4 mm per M3, 0,5 mm per M4/M5, 0,6 mm per M6. Se la vite necessaria supera 120 mm, la combinazione viene rifiutata.

## Geometria e distinta

Gole, cave e fori sono presenti nei solidi, nella preview e nel CAD. Le parti modificate usano il trasferimento STEP BRep condiviso con la preview; non sono soltanto annotazioni nella distinta. Sezioni a gradino e cave con estremità piane non vengono raccordate da un loft liscio.

Gli anelli sono sagome montate a C, senza occhielli; viti e dadi hanno gli ingombri principali ma non filetti fisici o impronte dettagliate. Non usare queste sagome per produrre la viteria: sono componenti da acquistare. I distanziali terminali tengono i rasamenti grandi fuori dai piani dei Seeger interni. I distanziali e i rasamenti non modellano le piste dei cuscinetti: verificare l’appoggio sul solo anello previsto.

La distinta distingue **ACQUISTARE**, **REALIZZARE** e **DA DEFINIRE**. Nel TXT appare la sezione **Lavorazioni presenti nel modello**; il JSON include le operazioni e viene affiancato da `.lavorazioni.json`. Le quote Z delle lavorazioni sono locali alla rispettiva parte. Gole, cave e fori compaiono anche nei metadati del componente CAD `local.solidcraft.machining`; le quantità sono aggregate nella distinta nativa.

Esempi completi: `esempi/doppia-elica-hardware.config.json`, `esempi/planetary-hardware.config.json`, `esempi/cycloidal-hardware.config.json`, con distinte e documenti in `esempi/cad/`.

## Fonti primarie

- [Springmasters — EXT0060 e relativa gola](https://www.springmasters.com/shop/ext0060/), [EXT0080](https://www.springmasters.com/shop/ext0080/), [EXT0100](https://www.springmasters.com/shop/ext0100/), [EXT0120](https://www.springmasters.com/shop/ext0120/).
- [American Ring — DIN 472, tabella metrica](https://www.americanring.com/products/ringseries.aspx?series=DIN472&units=metric).
- [Ganter — cave DIN 6885-1](https://www.ganternorm.com/fileadmin/user_upload/downloads/technischer%20anhang/technical_information/6885-1.pdf), [Gardette — linguette tipo B](https://gardette.com/en/catalog/parallel-key-b).
- [KIPP — rasamenti DIN 988](https://www.kippusa.com/en-us/products/METRIC/Machine-and-fixture-components/Screws-nuts-washers/Shim-washers-DIN-988/p/agid.32243).
- [N.S. Socket Screws — ISO 4762](https://stock-api.socketscrews.co.uk/files/Final%20ISO%204762%20Website.pdf), [Böllhoff — dadi ISO 4032](https://eshop.boellhoff.de/out/media/pdf/ISO_4032_Stahl_8___en.pdf), [India Fastener Parts — rondelle ISO 7089](https://www.indiafastenersparts.com/documents/India_Specs/Metric_Flatwasher_ISO7089.pdf).

Verifica dei dati: 23 ottobre 2026. Restano da dimensionare carichi, materiali, tolleranze, serraggi e collegamenti dichiarati aperti. I modelli di studio harmonic e vite-corona non ricevono questo montaggio automatico.
