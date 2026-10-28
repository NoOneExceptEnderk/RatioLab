# Modalità cinematica

Sopra il visualizzatore 3D, **Avvia movimento / Pausa** e **Posa iniziale** sono accessibili direttamente. Premi il pulsante con il valore della velocità e **Regola**: si apre una palette compatta in stile CAD, con testata grigia, pulsante di chiusura, stato, **Avvia / Pausa / Riprendi**, ritorno alla posa iniziale e slider **RPM d’ingresso**. Rimane aperta mentre ruoti il modello; chiuderla non arresta il moto. I dettagli sono espandibili.



La riproduzione usa gli RPM effettivi: 60 rpm corrispondono a un giro al secondo dell’ingresso. Rapporti e versi restano quelli dello schema scelto. A velocità elevate il campionamento dello schermo può far apparire i denti fermi o invertiti: abbassa gli RPM per ispezionare il movimento. Con tutti gli ingressi a zero il modello resta fermo.



Parametri errati fermano l’animazione; correggili per riavviarla. Avvia disattiva la vista esplosa. Camera, sezione e visibilità rimangono disponibili durante il moto.

## Movimenti rappresentati

- Ingranaggi, treni, vite e riduttori: rotazioni dei membri con velocità e assi propri.
- Cicloidale: orbita eccentrica e rotazione del disco. Il disco è un organo interno orbitante, anche quando l’uscita è fissa.
- Harmonic: deformazione radiale illustrativa del flexspline, orientata dal generatore d’onda, con rotazione del materiale e fondo della coppa solidale alla flangia. Non rappresenta un’analisi elastica.


## Esportazione

L’animazione modifica soltanto il rendering dell’anteprima: geometria, parametri, distinta e comandi CAD conservano la posa di montaggio. STEP e STL rimangono coerenti con il modello nominale. **Esporta file… → Pacchetto completo** ripristina la posa iniziale prima di salvare anche il PNG.

È una visualizzazione cinematica: non verifica collisioni durante il ciclo, contatto coniugato, carichi, elasticità, attrito o durata; non crea giunti animati nel documento SolidCraft.
