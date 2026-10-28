# Verifica del catalogo a nove famiglie — 27 ottobre 2026

Il programma usa un solo percorso di configurazione. La tendina contiene, nell’ordine: spur, helical, double, planetary, cycloidal, harmonic, worm, parallel e internal. Gli altri generatori e i relativi preset non fanno parte del programma.

## Verifiche precedenti alla semplificazione

- 146 test automatici superati: profili, geometrie condivise, montaggi, cinematiche, materiali, processi, albero cicloidale FDM, hardware, STL, ricerca GTK, avvisi geometrici e protocollo CAD simulato.
- Confronto con la versione precedente su 46 configurazioni delle famiglie mantenute: parametri, parti e dati di calcolo identici. Sono comprese varianti e schemi cinematici alternativi.
- La GUI è stata avviata sul display locale: nove elementi nella tendina, tre schede, nessun selettore di modalità. Verificate tutte le varianti disponibili, navigazione durante le scelte di materiale, errori e recupero, configurazioni JSON e riproduzione.
- Esportazioni STL e pacchetto completo eseguite in una cartella temporanea. Nessun documento CAD reale è stato modificato.
- I vecchi file JSON delle nove famiglie restano caricabili. Le famiglie non supportate sono respinte senza sostituire il modello corrente.

I test confrontano la geometria e i calcoli nominali implementati: non certificano resistenza, durata, montaggio o contatto durante l’intero moto. I file storici già esportati rimangono in `outputs/` e nelle cartelle scelte dall’utente.

Schermata: `outputs/ui-nine-reducers.png`. Script di verifica e confronto: `work/catalog-nine-20261027/`.

## Manutenzione successiva — 27 ottobre 2026

- Corretta la visualizzazione del sottotaglio per gli ingranaggi singoli: l'interfaccia usa i dati geometrici, senza cercare prefissi di testo tradotti. Visibili anche gli avvisi di interferenza interna dei planetari. Quattro nuovi test coprono sottotaglio, correzione del profilo, interferenza interna e modelli concettuali.
- Aggiunti 26 test del client CAD: token e autenticazione, chiusura delle risorse, connessione interrotta, timeout, risposte non valide, recupero delle operazioni in corso senza reinvio, batch atomici, import STEP, ripristino confermato o fallito, sketch attivo ed errori della timeline. Socket, risposte e avvio del CAD sono simulati; questi test non attestano la compatibilità con una specifica versione del CAD reale.
- Corretta la chiusura del socket se la creazione dello stream fallisce o se la chiusura dello stream solleva un errore. Il messaggio di connessione mostra la porta effettivamente configurata.
- Resi più leggibili il client CAD e l'aggiornamento dell'interfaccia. Nuovo confronto su 46 configurazioni: parametri, geometrie delle parti e dati di calcolo identici al riferimento precedente.
- Verifica dell'app sulle 22 varianti: navigazione, materiali, errori e recupero, avvisi di sottotaglio e interferenza, configurazioni JSON, riproduzione, STL e pacchetto completo. Esportazioni e PNG in una cartella temporanea; per la cattura PNG lo script ha forzato un frame OpenGL perché la finestra in background non riceveva frame automatici. Script locale: `work/maintenance-20261027/check_gui.py`.
- Creato il primo commit Git con sorgenti, cataloghi, documentazione ed esempi. Esportazioni generate, file temporanei, preferenze e librerie materiali personali restano locali.


## Rimozione materiali e produzione — 27 ottobre 2026

- Rimossi catalogo/editor materiali, verifiche di resistenza delle sezioni, selettore di tecnologia, parametri e preset di produzione. Eliminati i relativi moduli, test dedicati, documentazione ed esempi specifici; la roadmap esclude queste funzioni.
- Le configurazioni precedenti conservano geometria, varianti e cinematica. I campi obsoleti vengono ignorati dal generatore e non sono riportati in nuovi salvataggi, report o metadati CAD.
- Conservati carichi nominali, potenza, rapporti, forze d'ingranamento, distinta, cuscinetti e ferramenta. Verificati l'albero cicloidale con due viti passanti e l'uscita housing per disco singolo e doppio.
- Superati 122 test del motore e 3 test GTK di ricerca sul display locale. Quattro test coprono l'assenza dei moduli rimossi, compatibilità dei vecchi parametri su tutte le famiglie, costruzione con viti passanti e pulizia degli export.
- La GUI/OpenGL è stata avviata su tutte le nove famiglie e le tre schede: nessun controllo materiali/produzione, JSON precedente caricato senza campi obsoleti, riproduzione e uscita housing funzionanti. Nessun documento CAD reale è stato modificato.
- Il test di ricerca ora controlla anche la presenza effettiva del display: viene saltato quando GTK si inizializza senza una connessione grafica, evitando il crash di libgtk in ambiente senza display. La ricerca rimane coperta dai test sul display locale.

Log: `work/remove-materials/core-tests.log`, `search-tests.log`, `gui.log`. La schermata `outputs/ui-nine-reducers.png` è aggiornata alla UI senza materiali e produzione. Le esportazioni storiche e gli eventuali dati personali già salvati restano file indipendenti.

## Workspace tecnico — 28 ottobre 2026

- Applicata la prima direzione approvata: pannello parametri a sinistra, anteprima dominante, risultati geometrici in una fascia continua, esportazione nell'intestazione e integrazione SolidCraft nel proprio menu. Nome pubblico ancora da scegliere: `[Project Name]` nella finestra.
- Unificati riproduzione, RPM precisi, regolazione e posa iniziale in una sola barra. Il popover Adjust contiene soltanto regolazione e informazioni. Gli assi X/Y/Z seguono l'orientamento effettivo della vista.
- Raggruppate geometria, alberi/fori e collegamento d'uscita. Alloggiamento, flange e costruzione dell'albero eccentrico sono in Assembly; carichi nominali e avanzati sono richiudibili. Le quote collegate indicano l'origine e permettono di aprirla.
- Gli errori mantengono il testo immesso anche quando GTK aggiorna il campo alla perdita del focus. Esportazione e invio CAD sono bloccati; l'ultima geometria valida della stessa famiglia resta visibile con avviso esplicito. La validazione include l'ingresso RPM; un cambio di sola velocità valida conserva la fase cinematica.
- Superata la suite completa di **133 test**, inclusi otto nuovi controlli di risultati/workspace. Ulteriori controlli mirati coprono ricerca GTK, avvisi, messaggi di errore e mantenimento dello scorrimento su un cicloidale con pannello lungo.
- Verificate sul display locale tutte le 22 varianti delle nove famiglie: navigazione, recupero da errori, JSON, collegamenti ai cuscinetti, reset/annullamento, animazione, STL e pacchetto completo. Le esportazioni di prova usano cartelle temporanee; nessun documento CAD reale è stato modificato.
- Catturate le schermate reali a **1600×1000** e **1280×800**, anche con cicloidale a doppio disco, avanzati ed errore. L'anteprima misura rispettivamente 1249×633 e 929×433 px nel caso planetario. Verificata l'apertura dei popover nativi Export e CAD integrations dopo il completamento del layout.

Riferimento aggiornato: `outputs/ui-nine-reducers.png`.
Schermate aggiuntive: `outputs/ui-workspace-technical.png`,
`outputs/workspace-technical-1280.png`, `outputs/workspace-cycloidal-1280.png`,
`outputs/workspace-error-1280.png` e `outputs/workspace-advanced-1280.png`.
Log e script locali: `work/workspace-technical-20261028/`.
Il codice dei generatori, dei calcoli, della cinematica e dell'export resta
quello precedente al riordino dell'interfaccia.

## Identità RatioLab — 28 ottobre 2026

- Nome pubblico **RatioLab** e descrizione **Parametric gear and reducer generator** applicati a finestra, intestazione, collegamento desktop, README e metadati dei nuovi STEP.
- Identità scelta: **B bicolore**, monogramma RL compatto con dettagli verde acqua. La base orizzontale della L è stata allungata su richiesta del proprietario. Icona, loghi per sfondo chiaro e scuro, riferimento originale scelto e manifest sono salvati in `assets/branding/`; prompt, sorgenti generati e versioni precedenti in `design/branding/production-2026-10-28/`.
- Il collegamento sulla Scrivania è ora `RatioLab.desktop`; quello precedente è conservato in `work/branding-20261028/desktop-shortcut-before.desktop`. Il formato delle configurazioni e l'identificatore interno dell'applicazione sono conservati.
- Verifica reale su display a **1600×1000** e **1280×800**: titolo, nome applicazione, ricerca dell'icona, dimensione dell'icona nell'intestazione, geometria e rendering corretti. Schermate in `outputs/ratiolab-1600.png`, `outputs/ratiolab-1280.png`; aggiornato `outputs/ui-nine-reducers.png`.
- Superati i quattro test delle superfici/STEP e sette degli otto test del workspace sul display locale. Il test `test_panel_rebuild_keeps_scroll_and_advanced_section` fallisce nel controllo della posizione di scorrimento. Un confronto senza le modifiche di branding, ripristinando in memoria la precedente intestazione senza logo, riproduce lo stesso errore. Non viene quindi dichiarata una suite completa verde per questa verifica; il problema di scorrimento rimane separato dal cambio di identità.
- Le prove non esportano verso un documento CAD reale. Script di controllo e log locali in `work/branding-20261028/`.

### Registrazione della barra GNOME — 28 ottobre 2026

- Il collegamento sulla Scrivania non era sufficiente per associare nome e icona alla finestra nella barra GNOME. Installato `~/.local/share/applications/local.solidcraft.reducers.desktop`, con nome **RatioLab**, icona selezionata e identificatore corrispondente alla `Gtk.Application`.
- Aggiunto `install_desktop.py`: registra il launcher nel catalogo applicazioni dell’utente, aggiorna il collegamento nella cartella Desktop XDG e rigenera il database desktop. `--dry-run` permette di controllare i percorsi prima dell’installazione. Attivate le notifiche di avvio del launcher.
- Verificati con `Gio.DesktopAppInfo` il nome RatioLab, l’identificatore, la classe della finestra e il percorso dell’icona; il launcher installato supera `desktop-file-validate`. Confermato che l’app aperta proviene da questa cartella del progetto. La finestra già in esecuzione non è stata chiusa automaticamente, per conservare i parametri correnti.

## Installazione su altri computer — 28 ottobre 2026

- Generati artefatti Python reali: `dist/ratiolab-0.1.0.tar.gz` e
  `dist/ratiolab-0.1.0-py3-none-any.whl`. Il wheel è stato costruito dai sorgenti
  estratti dall’sdist, non direttamente dal checkout. I 43 membri del wheel e
  i 145 dell’sdist superano `scripts/verify-artifacts.py`, inclusa la scansione
  dei contenuti per percorsi assoluti dell’utente/checkout. Nessuna preferenza,
  credenziale, cartella `work/`, `design/`, `outputs/`, `.git` o modello generato
  viene incluso. L’identità B, i cataloghi e le istruzioni di installazione sono
  risorse del wheel. `RatioLab.desktop` è un template generico senza percorsi
  locali; il generatore registra il Python e l’icona dell’installazione scelta.
- Preferenze UTF-8 e asset STEP predefiniti ora usano directory dell’utente.
  Provati migrazione in lettura delle preferenze del checkout, salvataggio
  atomico, conservazione del file precedente in caso di errore, rifiuto dei
  percorsi risorsa esterni e percorsi con spazi/Unicode. Restano invariati
  `solidcraft-riduttori/1` e `local.solidcraft.reducers`.
- Il loader OpenGL usa i puntatori dati `epoxy_gl*` della stessa libreria nativa
  usata da GTK, con ABI Windows e dimensione dei puntatori esplicite. I test
  verificano puntatori reali, round trip della chiamata, lifetime della libreria
  e rifiuto di simboli mancanti/puntatori non validi. La diagnostica richiede
  GTK 4.12+, shader reali e pixel non uniformi nel framebuffer; non considera
  sufficiente la sola apertura della finestra.
- Installazione pulita eseguita in una venv Python 3.14 fuori dal checkout,
  usando GTK del sistema: `site-packages` e cartelle delle risorse in modalità
  `555`, file in `444`. Da una cartella neutra, lo smoke test ha caricato i
  cataloghi e il branding installati, generato STEP e STL autonomi, riletto una
  configurazione e salvato preferenze in un profilo temporaneo. Superati 45 test
  mirati portabilità/protocollo/scena 3D (un test GUI saltato nel sandbox senza
  display). Superati inoltre gli 80 test del motore selezionati e la serie di
  47 controlli comprendente tutte le esportazioni STL predefinite/varianti
  (un test GUI saltato).
- La review indipendente ha ripetuto l’installazione in un secondo percorso con
  spazi e pacchetti in sola lettura. Ha verificato 27 moduli installati, loghi
  byte-identici, tutte le nove famiglie, diagnostica grafica OpenGL 4.6 e
  caricamento/salvataggio dal workspace completo. PNG, STL, STEP, distinta e
  relazioni sono stati esportati in un percorso con spazi e caratteri Unicode;
  gli hash dell’installazione prima/dopo sono identici. I 44 test installati di
  portabilità, protocollo e ricerca GTK eseguiti sul display passano senza skip.
  La suite completa di quella revisione contava 137 test superati e tre skip
  per indisponibilità del display nel sandbox. Il successivo delta di
  preparazione delle DLL prima di PyGObject supera nuovamente i 45 test mirati.
- Il confronto indipendente su 73 configurazioni (esempi, famiglie e varianti)
  non rileva differenze in parti, parametri, analisi, metriche, note o requisiti
  rispetto alla baseline precedente al lavoro. Il `geometry.py` corrispondente
  è stato verificato byte per byte anche nel wheel.
- La connessione CAD è opzionale: provati riuso della connessione, eseguibile
  configurato con spazi su rami Windows/macOS simulati, directory token
  esplicita, opzioni di processo corrette e mancato avvio in assenza di
  configurazione. Nessun documento CAD reale è stato modificato. Queste prove
  non dimostrano l’esistenza di una distribuzione SolidCraft per ogni sistema.
- Aggiunti script di installazione Linux, MSYS2 UCRT64 e Homebrew, verificati
  sintatticamente, e workflow nativi che costruiscono dall’sdist e verificano un
  wheel installato fuori repository. Su macOS viene scelto un Python Homebrew
  che carica effettivamente la formula PyGObject; su Windows si usa solamente
  Python UCRT64 con le relative DLL. **Windows/macOS e i nuovi workflow non
  sono stati eseguiti qui**. Non vengono dichiarati bundle `.exe`, `.app`,
  `.dmg` o AppImage pronti né supporto grafico già provato su quei sistemi.

Il problema preesistente di scorrimento
`test_panel_rebuild_keeps_scroll_and_advanced_section`, descritto nella sezione
Identità RatioLab, rimane distinto da questo lavoro e non viene dichiarato
risolto. I test che richiedono display non sono conteggiati come verificati
quando vengono saltati.

Istruzioni ripetibili: `INSTALL.md`. Log locali:
`work/portable-build.log`, `work/portable-installed-final.log`,
`work/portable-core-tests.log`, `work/portable-tests.log`,
`work/portable-dll-delta-tests.log`. Evidenze della review indipendente:
`work/portable-review-20261028/`.

## Installer con runtime incluso — 28 ottobre 2026

- Aggiunta una vera build nativa PyInstaller **onedir**, con Python, GTK4,
  PyGObject/Cairo e foreign converter, libepoxy, typelibs, schemi compilati,
  icone Adwaita/hicolor e font DejaVu con copyright originali. Il manifest
  inventaria hash, versione, architettura e baseline del sistema. Le notices
  attribuiscono binari, typelibs e icone ai pacchetti effettivi e includono i
  testi delle licenze comuni Debian richiamati; provenienza o testi mancanti
  fanno fallire la build. Non sono distribuiti driver GPU del produttore.
- Build Linux reale in un rootfs ufficiale Ubuntu 24.04 isolato, con Python
  3.12.3, GTK 4.14.5 e glibc 2.39. Il primo bundle verificato contava 1167 file
  e 74 componenti nativi, prima dell'estensione delle notices ai dati. Superati
  self-test, nove famiglie, lettura/scrittura UTF-8, STL/STEP, pixel OpenGL 4.5
  llvmpipe e prove del workspace completo. Lo stesso bundle è stato eseguito
  sul desktop Ubuntu 26.04 con OpenGL 4.6. Il confronto geometrico precedente
  resta valido: questi interventi non modificano i generatori.
- Creati installer Linux reali `.run`, `.tar.gz` e `.deb` in `dist/installers`.
  Il `.deb` è stato installato con APT nel rootfs Ubuntu 24.04 e avviato mentre
  Python, libpython, GTK, typelibs, schemi e icone del sistema erano mascherati
  tramite mount. La diagnostica usa libepoxy e Gtk typelib del bundle; rendering,
  nove famiglie ed esportazioni PNG/STL/STEP/configurazione/distinta sono passati.
  La rimozione del pacchetto conserva le sentinelle di preferenze e progetti.
  L'installer `.run` ha superato installazione, aggiornamento ed eliminazione
  in un profilo temporaneo con spazi e Unicode, incluso il controllo grafico.
- L'installazione utente Linux aggiorna/rimuove soltanto i file inventariati:
  conserva anche progetti o altri file non inventariati salvati per errore nella
  cartella dell'applicazione. Sette test dedicati verificano installazione,
  aggiornamento, disinstallazione e rifiuto di cartelle estranee. I launcher
  continuano a usare `local.solidcraft.reducers`.
- Il bundle finale conta **1218 file e 84 componenti nativi**. Ripetute sul
  risultato finale sia installazione/aggiornamento/rimozione `.run` sul desktop,
  sia installazione APT/rimozione `.deb` nel rootfs con GTK e Python del sistema
  mascherati: rendering e tutte le esportazioni del workspace passano.
- Superati **58 test mirati** dopo l'ultimo delta: 13 sul lancio di programmi
  esterni, 12 su integrità/bootstrap/notices, 26 sul protocollo CAD e 7 sugli
  installer Linux. Sono provati
  ripristino di `LD_LIBRARY_PATH_ORIG` e PATH, conservazione dell'ambiente globale,
  valori GTK/font originali, Gio child context, apertura Linux con `xdg-open`,
  collegamenti NSK senza espansione shell o doppio handler GTK,
  ABI delle API Windows e ripristino della directory DLL anche su eccezione.
  L'inventario respinge file aggiunti/modificati e link esterni; le regressioni
  delle licenze coprono usrmerge Debian e nomi SPDX MSYS2.
- Sono configurati installer Windows reali con Inno Setup e un `.app`/DMG macOS
  creato con PyInstaller, `codesign` e `hdiutil`. Il workflow nativo comprende
  installazione/rimozione Windows e mount/copia/verifica macOS per Intel e ARM.
  La firma usa solo identità fornite dal manutentore; la notarizzazione richiede
  un suo profilo già configurato. Il minimo macOS è verificato sui load command
  dei Mach-O, senza attribuire a un deployment target la capacità di abbassare
  il requisito di librerie Homebrew precompilate. **Windows, macOS, firma,
  notarizzazione e workflow remoto non sono stati eseguiti su questo host**:
  non esistono ancora binari Windows/macOS convalidati da consegnare.

Evidenze Linux indipendenti: `work/installer-linux-ubuntu24-build.log`,
`work/installer-linux-deb-real.log`, `work/installer-linux-deb-proof.json`,
`work/installer-linux-run-real.log`, `work/installer-linux-run-proof.json`.
Prove finali: `work/installer-linux-run-final-proof.json` e
`work/installer-linux-deb-final-proof.json`.
I problemi di scorrimento già descritti rimangono separati e non sono dichiarati
risolti. Le prove CAD usano mock o generano file: nessun documento CAD reale
è stato modificato.
