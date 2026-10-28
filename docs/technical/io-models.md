# Modelli adattati ai collegamenti di ingresso e uscita

Il riquadro **Azionamento · ingresso e uscita** modifica anche i collegamenti geometrici degli schemi alternativi. Le configurazioni di base conservano i modelli e le compatibilità già esistenti.

## Cosa cambia

| Famiglia | Adattamento degli schemi alternativi |
|---|---|
| Planetary, anche doppia elica | Rimossi alberi e fermi che presupponevano corona fissa; mozzi indipendenti per solare, portatore e corona. I passaggi del portatore lasciano libero l’albero centrale. I vecchi coperchi che attraverserebbero i nuovi attacchi vengono rimossi |
| Planetary bistadio | Uscita del primo e ingresso del secondo collegati con due mozzi e una piastra intermedia: il collegamento cambia con i membri scelti. Gli attacchi esterni e i membri fissi restano indipendenti |
| Cicloidale mono/doppio disco | Collegamenti all’albero eccentrico, flangia perni e carter della corona. Eliminati i vecchi alberi e coperchi incompatibili con il carter mobile. La sede dei rulli segue il membro corona |
| Harmonic, cup/flat cup/hat | Attacco flexspline solo sul fondo/diaframma o sulla flangia rigida; albero del generatore e attacco anulare della corona sul lato aperto. La parte flessibile dentata non viene trattata come un mozzo rigido |


## Come leggere gli attacchi

- Arancio: ingresso, flangia con **4 fori nominali**.
- Verde: uscita, flangia con **6 fori nominali**.
- Grigio: membro da fissare, flangia con **8 fori nominali**.

I mozzi toccano la faccia del membro indicato oppure occupano il suo foro come un albero nominale. I collegamenti coassiali usano fasce radiali e posizioni assiali distinte. L’estensione deriva dalla quota albero della famiglia, se presente, oppure da 8 mm; flange e pareti derivano dalle quote del modello. Le geometrie seguono le variazioni dei parametri.

Quando scegli un nuovo schema con attacchi adattati, **Supporti** viene attivato per mostrarli. Puoi nasconderli nuovamente. Anteprima, STEP, STL e distinta usano gli stessi solidi; JSON e metadati mantengono gli identificatori degli schemi esistenti. La relazione JSON contiene `mount_interfaces`, con membro, ruolo, pezzo di appoggio, asse e quote; `interstage_mounting` descrive il collegamento fra i due stadi.

Per gli schemi alternativi planetary e cicloidali sono richieste quote manuali e hardware automatico disattivato: le vecchie sedi standard presuppongono la corona fissa. Il pannello offre il pulsante per passare alle quote manuali.

## Limiti meccanici

Questi sono **attacchi nominali**, non giunti industriali già dimensionati. I fori sono realmente presenti, ma non rappresentano una selezione di bulloni commerciali. Resta da definire il trasferimento della coppia fra albero e mozzo (linguetta, spline, serraggio o altro), con tolleranze, cuscinetti, arresti assiali e telaio. Una battuta fra due solidi non crea automaticamente un vincolo nel CAD.

Le flange fisse richiedono un telaio esterno; i carter mobili richiedono supporti adeguati. Non sono verificate portata, fatica, rigidezza o tutto l’inviluppo di movimento. Il controllo geometrico riguarda la posa di riferimento.

## Riferimenti

