# RatioLab

Anteprima pubblica, con licenza **GNU GPL v3.0 only**. Gli installer con le
dipendenze incluse sono in [GitHub Releases](https://github.com/NoOneExceptEnderk/RatioLab/releases).
I nomi dei file e i commenti del codice sono in inglese; questa guida resta
disponibile in italiano. Per contribuire vedere [CONTRIBUTING.md](CONTRIBUTING.md).

![RatioLab](assets/branding/ratiolab-logo-dark.png)

**Generatore parametrico di ingranaggi e riduttori.**

Include anche un server **MCP locale per gli agenti**, con 13 strumenti per
progetti, parametri, Undo/Redo, componenti/BOM, ricerca, interferenze ed export.
Gli installer contengono il programma `RatioLab-MCP` (`.exe` su Windows):
non richiede dipendenze aggiuntive e lavora senza aprire la GUI. Progetti e
file restano nella cartella assegnata; le revisioni impediscono modifiche
basate su uno stato superato. Collegamento a Codex e altri client in [MCP.md](MCP.md).

Applicazione autonoma per generare ingranaggi e riduttori, visualizzarli ed
esportarne la geometria per i software CAD. SolidCraft è un'integrazione
disponibile; l'esportazione STL funziona anche senza collegarlo.

Per installarlo su un altro computer, seguire [INSTALL.md](INSTALL.md). Gli
installer nativi includono Python, GTK e le altre librerie: `.run`/`.deb` Linux,
Setup Windows 11 e `.app`/`.dmg` macOS per Intel e Apple Silicon. Le build native
verificano l'app installata e allegano i file ai job superati: vedere le
[build degli installer](https://github.com/NoOneExceptEnderk/RatioLab/actions/workflows/installers.yml)
e le versioni dei sistemi supportate in `INSTALL.md`.
Il percorso wheel/sorgenti rimane disponibile per sviluppo. Preferenze ed
esportazioni usano cartelle dell’utente.

Il programma usa il **Workspace tecnico** scelto: parametri a sinistra nelle schede **Dimensions**, **Motion** e **Assembly**, anteprima dominante, una sola barra del movimento e risultati geometrici sotto il modello. L’interfaccia rimane in inglese. Nome e icona sono RatioLab. La versione B bicolore del monogramma RL, con la base della L allungata, e i file per GitHub sono conservati in `assets/branding/`; la palette e la scelta sono registrate in `brand.json`.

Sono disponibili solo nove famiglie: ingranaggio diritto, elicoidale, doppia elica, planetary, cicloidale, strain wave, vite senza fine, **Parallel shaft reducer** e riduttore a corona interna. Gli altri generatori non sono disponibili.

Quote, cinematica, animazione, carichi nominali, cataloghi e hardware rimangono disponibili per le famiglie supportate. I parametri sono raggruppati; profili e giochi stanno negli avanzati e i carichi nominali in una sezione richiudibile di Motion. I risultati sono distinti dai campi modificabili. Le quote collegate spiegano l’origine e permettono di aprirla in Assembly. Scheda, avanzati e scorrimento rimangono stabili quando si cambia un’opzione. Le sezioni materiali, resistenza degli alberi e impostazioni di produzione restano escluse. I relativi campi nelle configurazioni precedenti vengono ignorati senza cambiare la geometria.

**Open… / Save…** e **Export…** sono sempre nell’intestazione. L’esportazione comprende STL, pacchetto completo o distinta e calcoli. Connessione, stato e **Create in SolidCraft** sono nel menu **CAD integrations**. Distinta, relazione e note sono nella barra inferiore. Gli errori restano visibili nei campi e bloccano l’export; l’ultima anteprima valida è esplicitamente segnalata. Il collegamento sulla Scrivania avvia `launch.sh` in questa cartella.

Le priorità sono in [TODO.md](TODO.md): semplificare le funzioni e rifare la UI intorno alla generazione, consolidare esportazione e progetti, preparare la pubblicazione open source su GitHub e poi migrare a Rust. Nuove famiglie e preparazione dedicata alla stampa sono rimandate.

I file già esportati rimangono disponibili; le configurazioni relative a famiglie non supportate vengono rifiutate senza modificare il modello aperto.

Per registrare nome e icona anche nella barra delle applicazioni Linux, eseguire `/usr/bin/python3 install_desktop.py`. Lo script installa il launcher nel menu applicazioni dell’utente e aggiorna il collegamento sulla Scrivania usando l’identificatore GTK corretto.

Documentazione completa: [README.md](README.md), [PRINTED-SHAFT.md](PRINTED-SHAFT.md), [CALCULATIONS.md](CALCULATIONS.md).

## Licenza

Copyright (C) 2026 NoOneExceptEnderk. RatioLab usa la [GNU GPL versione 3 only](LICENSE),
identificativo `GPL-3.0-only`. Sono consentiti uso commerciale, modifiche e fork.
Chi ridistribuisce il programma o versioni derivate deve conservare attribuzioni
e avvisi di licenza, mantenere la GPLv3 e fornire il relativo codice sorgente
secondo i suoi termini. Il programma è fornito senza garanzie. Le dipendenze
mantengono le proprie licenze. La licenza dell'app non si applica automaticamente
ai progetti indipendenti o ai pezzi realizzati dagli utenti.
