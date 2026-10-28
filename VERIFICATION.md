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
  Python UCRT64 con le relative DLL. Questa prima verifica locale precedeva
  l’esecuzione dei workflow remoti; gli esiti nativi successivi sono documentati
  nella sezione sugli installer. Non viene dichiarato supporto grafico già
  provato su Windows/macOS né un AppImage.

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
  cartella dell'applicazione. Otto test dedicati verificano installazione,
  aggiornamento, disinstallazione e rifiuto di cartelle estranee. I launcher
  continuano a usare `local.solidcraft.reducers`.
- Il bundle Linux della verifica locale conta **1218 file e 84 componenti nativi**. Ripetute sul
  risultato finale sia installazione/aggiornamento/rimozione `.run` sul desktop,
  sia installazione APT/rimozione `.deb` nel rootfs con GTK e Python del sistema
  mascherati: rendering e tutte le esportazioni del workspace passano.
- Superati **58 test mirati** nella prima revisione locale: 13 sul lancio di programmi
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
  il requisito di librerie Homebrew precompilate. Le successive esecuzioni
  native su GitHub sono documentate di seguito. La firma con identità del
  manutentore e la notarizzazione Apple richiedono credenziali reali e non
  sono state eseguite.

Evidenze Linux indipendenti: `work/installer-linux-ubuntu24-build.log`,
`work/installer-linux-deb-real.log`, `work/installer-linux-deb-proof.json`,
`work/installer-linux-run-real.log`, `work/installer-linux-run-proof.json`.
Prove finali: `work/installer-linux-run-final-proof.json` e
`work/installer-linux-deb-final-proof.json`.
I problemi di scorrimento già descritti rimangono separati e non sono dichiarati
risolti. Le prove CAD usano mock o generano file: nessun documento CAD reale
è stato modificato.


## Verifica nativa GitHub e pacchetti consegnati — 28 ottobre 2026

Il workflow [Native installers #7](https://github.com/NoOneExceptEnderk/RatioLab/actions/runs/40617279239)
è terminato con **tutti e quattro i job superati**, sul commit
`461af0295a8336b3933dc3415081b2198cd994c9`. Anche il workflow
[Portable Python distribution](https://github.com/NoOneExceptEnderk/RatioLab/actions/runs/40617279229)
dello stesso commit supera i tre job Linux, Windows e macOS. La successiva
revisione della documentazione non cambia il codice dei runtime o dei builder.

| Runner nativo | Runtime incluso | Inventario | Prova del pacchetto scaricabile |
|---|---|---|---|
| Ubuntu 24.04 x86-64 | GTK 4.14.5; glibc 2.39 | 1234 file, 88 componenti nativi | `.run` installato, avviato e rimosso in percorso con spazi/Unicode; rendering OpenGL Mesa e workspace completo; runtime del `.deb` estratto e avviato |
| Windows Server 2025 x86-64 | GTK 4.24.1; destinazione Windows 11 build 22000+ | 1053 file, 54 componenti nativi | Setup Inno 6.7.1 compilato, installato, avviato senza MSYS2 sul PATH e disinstallato; report `bundled: true` |
| macOS 15 Apple Silicon | GTK 4.22.4; minimo macOS 15 verificato nei Mach-O | 354 file, 41 componenti nativi | DMG montato; app copiata con `ditto` in percorso con spazi/Unicode, avviata senza Homebrew sul PATH; firma ad hoc verificata con `codesign --deep --strict` |
| macOS 15 Intel | GTK 4.22.4; minimo macOS 15 verificato nei Mach-O | 354 file, 41 componenti nativi | Stesso ciclo DMG/copia/avvio/verifica firma dell’architettura ARM, eseguito su runner Intel |

Ogni runtime congelato supera tutte le nove famiglie, preferenze e
configurazioni UTF-8, STEP e STL. La build Linux esegue 41 test di
bundle/notices/lancio programmi/installer senza skip. Windows e ciascun macOS
eseguono 33 test con un solo skip esplicito per i testi di licenza comuni
Debian, assenti su quei sistemi. I controlli GUI/driver Windows e macOS non sono
stati richiesti e **non sono considerati verificati**. Il test grafico e le
esportazioni del workspace sono stati eseguiti su Linux; la preview 3D richiede
un driver OpenGL desktop 3.3+ sul computer di destinazione.

La suite locale mirata comprende 82 test (bundle 20, programmi esterni 13,
protocollo 26, installer Linux 8, portabilità 15), con uno skip GUI senza
display. Dopo l’ultima correzione delle sole fixture di percorsi, i 13 test sui
programmi esterni sono stati ripetuti dal revisore sia normalmente sia con
separatore Windows, senza errori. Le fixture rispettano il filesystem dell’host
anche quando simulano un’altra piattaforma; il codice di produzione è invariato.

La review indipendente delle notices MSYS2 verifica le ricette ufficiali dei
cinque pacchetti privi dei documenti installati, SHA-256 degli archivi upstream
e corrispondenza byte per byte degli otto testi originali selezionati. La
build accetta soltanto nomi, versioni e dichiarazioni di licenza esatte del
registro. `.gitattributes` conserva i byte delle notices anche su checkout
Windows. Le typelibs macOS rigenerate sono attribuite soltanto dopo verifica
della trasformazione esatta del GIR originale e del pacchetto proprietario.

I sei installer finali del run #7 sono stati scaricati in `dist/installers`:
`.run`, `.tar.gz`, `.deb`, Setup `.exe` e due `.dmg`. Il revisore ha verificato
ogni SHA-256 rispetto al file prodotto dal relativo job, firme di formato e
assenza di percorsi assoluti nei file checksum. `SHA256SUMS` riunisce i sei hash.
Sorgenti e wheel ricostruiti dall’sdist superano il controllo di contenuti e
assenza di cartelle private/generate.

Evidenze locali: `work/final-installer-evidence.json`,
`work/ci-40617279239-*.log`, `work/msys-notices-parent-review.json`,
`work/external-native-path-fixtures.log`,
`work/external-windows-path-fixtures.log`. I limiti già indicati sul problema
UI di scorrimento e sull’integrazione CAD reale rimangono validi. Il Setup è
privo di firma del produttore; l’app macOS ha firma ad hoc, senza identità
Developer ID né notarizzazione Apple.


## Aggiornamento delle sei funzioni e compatibilità grafica — 28 ottobre 2026

La consegna funzionale comprende STEP autonomi e profili SVG/DXF, progetti con
cronologia/recupero, profili dei denti migliorati, interferenze discrete 3D,
ricerca finita di combinazioni e selezione/misure/export dei componenti.
Dei 47 moduli runtime, 44 restano byte-identici alla snapshot funzionale
accettata; i tre adattati sono `preview3d.py` (compatibilità grafica),
`ratiolab_cli.py` (diagnostica) e `ratiolab_checks.py` (prove distribuite).
Nessun algoritmo geometrico o calcolo strutturale aggiunto in questa fase.

### Verifiche locali del revisore

- Suite completa: **310 test, zero errori, zero skip**, 231,931 s, con tutte le
  preview forzate su OpenGL ES reale; sorgenti runtime stabili durante la suite.
  Il confronto numerico transform feedback CPU/GPU del modello wave mantiene
  la tolleranza originale di 0,00015 mm. Il test usa ora MapBufferRange, comune
  a desktop GL ed ES, invece della lettura buffer disponibile solo su desktop.
- Le successive verifiche mirate contano **52 test superati** su bundle,
  renderer, lancio programmi e installer Linux, comprese le nuove regressioni
  di notice/provenienza ANGLE e conversione RGBA/ARGB su entrambe le endianess.
- Self-test grafico finale su OpenGL desktop 4.6 e OpenGL ES 3.2: tutte le sei
  aree funzionali, apertura dei tre strumenti, export del workspace e nove
  anteprime animate catturate in PNG e decodificate, senza immagini vuote.
  Vengono usati soltanto progetti/profili temporanei.
- Sdist e wheel ricostruita dall'sdist: rispettivamente 258 e 62 membri
  verificati, senza cartelle personali o di lavoro. I testi delle licenze
  ANGLE conservano i byte originali anche nei sorgenti distribuibili.

Il primo controllo grafico dell'installer Windows aggiornato ha rilevato una
vera dipendenza mancante: `libEGL not available`. Il bundle ora include
esplicitamente le DLL EGL/GLES di ANGLE, caricate dinamicamente da GTK.
Windows richiede OpenGL ES 3.0 tramite ANGLE/Direct3D; Linux e macOS mantengono
OpenGL desktop 3.3. Gli shader condividono la stessa matematica. La cattura
usa RGBA portabile, poi converte in Cairo ARGB32: la precedente lettura BGRA
non era garantita in ES. Errori shader, dipendenze mancanti, crash e PNG vuoti
non sono trattati come assenza di GPU del runner.

La review dei notice ANGLE verifica 18 testi mediante commit Git immutabili,
Git blob, SHA-256 del file originale e intervallo esatto di byte selezionato.
Il revisore ha ripetuto personalmente il verificatore online e i test.
La provenienza distingue i file Git verificati dall'archivio sorgenti completo
oltre 2 GB, che **non** è stato verificato: il suo hash è esplicitamente nullo.
La raccolta integra il LICENSE installato da MSYS2 anche quando già presente,
e rifiuta una versione/dichiarazione di licenza ANGLE non revisionata.

Prove locali: `work/updated-installers-es-suite-result.json`,
`work/updated-installers-es-full-tests.log`,
`work/updated-installers-final-package-tests.log`,
`work/updated-installers-desktop-nine-previews.json`,
`work/updated-installers-es-nine-previews.json`,
`work/angle-notices-parent-review/proof.json`.


### Nuovi installer nativi con le sei funzioni

Il [workflow installer aggiornati](https://github.com/NoOneExceptEnderk/RatioLab/actions/runs/40680620191)
sul commit `9a77c048d2e10b9ac5553acb2f874ca06118016a` supera **4/4 job**.
Anche la [distribuzione Python dello stesso codice](https://github.com/NoOneExceptEnderk/RatioLab/actions/runs/40680620325)
supera **3/3 job**. Queste prove sostituiscono, per le nuove funzioni e la GUI,
lo snapshot precedente degli installer #7.

| App installata | Rendering effettivo del runner | Risultato |
|---|---|---|
| Linux x86-64, Ubuntu 24.04 | OpenGL 4.5, llvmpipe/Mesa/Xvfb | Sei aree funzionali, nove PNG animati, workspace completo; `.run` installato e rimosso; runtime `.deb` estratto e avviato |
| Windows x86-64, Server 2025 | OpenGL ES 3.1, ANGLE/Direct3D11, Microsoft Basic Render Driver | Setup installato senza MSYS2 sul PATH, sei aree funzionali, nove PNG animati, workspace completo, disinstallazione |
| macOS 15 Apple Silicon | OpenGL 4.1, Apple Software Renderer | DMG montato, app copiata senza Homebrew sul PATH, sei aree funzionali, nove PNG animati, workspace completo e firma ad hoc verificata |
| macOS 15 Intel | OpenGL 4.1, Apple Software Renderer | Stesse prove complete, eseguite sul runner Intel |

Il Linux nativo supera 47 test mirati senza skip. Windows e ciascun macOS
superano 39 test con un solo skip del controllo dei common-license Debian,
non presenti su quei sistemi; **nessun controllo grafico è stato saltato**.
Le tre prove GUI delle app installate Windows/macOS hanno esito `passed`,
non `unavailable_on_runner`. Gli inventari comprendono 88 componenti Linux,
55 Windows e 41 per ciascun macOS, con testi delle licenze inclusi.

Le verifiche usano i renderer software disponibili sui runner ospitati.
Il pacchetto Windows è destinato a Windows 11 build 22000+, ma il runner di
build/test è Windows Server 2025: non è una prova su ogni versione Windows 11,
GPU o driver. L'assenza di firma Windows e di notarizzazione Apple resta un
limite di questa anteprima. Le interazioni con documenti CAD personali non
sono state eseguite. Valgono ancora i limiti geometrici discreti/campionati,
vite/wave e di assenza di verifiche strutturali dichiarati dal prodotto.

Log nativi completi: `work/ci-40680620191-*.log`. Report GUI e artefatti
originali: `work/final-installers-40680620191/`. Hash, dimensioni, job e
risultati grafici sintetici: `work/final-installer-evidence.json` e
`dist/installers/build-evidence.json`. I sei file della bozza e i due allegati
di verifica vengono confrontati con i digest SHA-256 restituiti da GitHub.

## Integrazione GUI del workspace — 28 ottobre 2026

- Intestazione con nome/stato del progetto, file, Undo/Redo, Export primario e CAD secondario; recenti scorrevoli con percorsi leggibili. Identità B conservata. Documenti e profili usati nelle prove sono temporanei.
- Componenti/misure, ricerca e interferenze sono nel pannello Tools ridimensionabile e richiudibile. Non aggiungono più tre righe permanenti alla barra di animazione. Parts/Measure separa la lista dalle coordinate e dalla distanza; risultati e report lunghi si aprono su richiesta. Il controllo interferenze mantiene copertura, pose e passo visibili durante l’ispezione.
- Export distingue ambito completo/selezionato e quantità, indipendentemente dalla visibilità. Le quote derivate hanno una casella riconoscibile. View permette testo al 100/125/150%; tastiera, focus e limiti dei pulsanti verificati anche al 150%.
- Corretta la corsa dello scorrimento tra aggiornamenti ravvicinati: una posizione appena scelta prevale sulla precedente richiesta ancora pendente, mentre gli eventi dell’utente interrompono il ripristino. Conservati pagina, sezioni, testo numerico incompleto, precisione e quote collegate.
- Smoke reale su tutte le nove famiglie e tre pagine, con Save, Undo/Redo, picking A/B e distanza 14.142136 mm, selezione/ispezione, ricerca con Apply unico Undo, interferenze e annullamento, sostituzione del documento durante entrambi i worker, pannelli lunghi e input invalido. Le prove a 1920×1080 impongono esplicitamente l’allocazione della finestra perché il window manager limita normalmente l’area utile a 1920×1048; l’intestazione rimane presente nelle catture. Verificate anche le azioni GTK di avanzamento del focus.
- Schermate, log macchina e resoconto dei flussi: [design/GUI-WORKSPACE.md](design/GUI-WORKSPACE.md), `outputs/gui-integration/`, `work/gui-integration-20261028/visual-verification.json` e `visual-verification.log`. Aggiornato `outputs/ui-nine-reducers.png`; la versione precedente è conservata nella cartella `before` delle prove.
- Nuovo modulo `workspace_tools.py` incluso in `pyproject.toml`. Sdist e wheel locali ricostruiti in una cartella distinta; **48 moduli** confrontati byte per byte con i sorgenti correnti e logo verificato. Installazione della wheel in venv temporaneo e prove da cartella neutra. Prove e checksum in `package-check/`, `package-check.log`, `wheel-install.log`, `installed-tests.log` e `tested-runtime.json` sotto la cartella delle verifiche.
- Nessuna modifica a generatori, algoritmi, writer, schema dei progetti o renderer: confronto con la copia iniziale in `source-preservation.json`. Rimangono i limiti preesistenti di campionamento, ricerca finita e modelli di studio. Esecuzione nativa Windows 11/ANGLE e macOS da verificare sui rispettivi sistemi; percorso OpenGL ES e conversione RGBA invariati. Push e aggiornamento delle release rimangono una fase separata.
- **Esito conclusivo: 320 test superati, zero skip, 280,277 s** dal sorgente; **67 test superati, zero skip, 111,353 s** dalla wheel realmente installata. Log: `final-tests.log` e `installed-tests.log`. Sette nuovi test coprono ciclo di vita del dock, conservazione di moduli/selezione, scroll sovrapposto, modalità, ambito export, copertura durante l’ispezione e layout/focus ingranditi. I due test del package mantengono le verifiche precedenti cercando la nuova etichetta “Export package”. I log intermedi sono conservati: comprendono l’adattamento delle etichette e una correzione del nuovo test, che ora confronta la copertura con il risultato reale anche quando il budget temporale è esaurito.

## MCP locale per agenti — 28 ottobre 2026

RatioLab espone 13 strumenti MCP locali per catalogo, progetti/revisioni,
Undo/Redo, componenti/BOM, ricerca finita, interferenze discrete ed export.
Il servizio usa gli stessi generatori e writer della GUI, senza nuove dipendenze
runtime. Supporta stdio MCP 2026-07-28 e la negoziazione legacy 2025-11-25.
I file sono confinati alla cartella esplicitamente assegnata, le modifiche
richiedono la revisione corrente e i risultati esistenti sono preservati.
La guida distribuibile e i contratti sono in [MCP.md](MCP.md).

Implementazione delegata all'agente con reasoning xHigh, seguita da lettura
diretta del codice e prove indipendenti del coordinatore. La review ha fatto
correggere il roundtrip dei parametri double_style, i campi cache del protocollo
moderno, gli errori JSON-RPC con id nullo, i file speciali/FIFO, i tipi numerici
booleani e l'esecuzione dei test da una wheel fuori dal checkout.

- Suite completa finale: **346 test, zero errori, zero skip**, 336,143 s,
  con preview forzate su OpenGL ES reale. I 50 moduli runtime sono rimasti
  byte-identici durante la suite. Comprende 23 regressioni MCP su tutte le
  famiglie/varianti e 3 nuove verifiche del lanciatore/standard streams.
- Client SDK ufficiali **1.30.0 e 2.3.0**: ciascuno supera **67 chiamate**, con
  12 errori attesi verificati. Prove ripetute con la wheel realmente installata
  e processo server avviato da cartella neutra; gli interpreti non hanno GTK.
  Verificati tutti i 13 tool, nove famiglie, preset FDM, Undo/Redo, aggiornamenti
  superati, conflitti su file modificati, scope del secondo componente,
  STEP/STL/SVG/DXF, pacchetti e hash, ricerca e copertura incompleta.
- Wheel installata in un ulteriore venv senza GTK/SDK: 23 test MCP superati
  da cartella esterna al checkout. Il verifier stdio supera entrambi i
  protocolli, salvataggio/apertura ed export reali. Sdist e wheel ricostruita
  dall'sdist: 267 e 66 membri verificati; documentazione MCP inclusa.
- Build frozen locale Linux: GUI completa, nove anteprime, sei aree funzionali
  e companion console MCP superati; runtime e inventario immutati dopo i test.
  La build locale usa le librerie dell'host: i pacchetti distribuibili devono
  essere ricostruiti sui quattro runner nativi con la baseline documentata.
- 50 controlli mirati di bundle/lancio programmi/installer Linux superati.
  Un errore nel nuovo verifier che risolveva il symlink di Python del venv è
  stato corretto prima del rilascio; ora conserva l'interprete configurato.

Il companion `RatioLab-MCP[.exe]` condivide il runtime dell'app e conserva
stdin/stdout anche su Windows. Le build e le prove dei pacchetti installati
eseguono `scripts/check-installed-mcp.py` con entrambi i protocolli e file veri.
Nessuna configurazione personale di Codex o altri client viene modificata.
I progetti del server sono indipendenti dalla finestra GUI e si scambiano JSON
compatibili. I pacchetti headless dichiarano l'assenza di screenshot.

Le risorse sono limitate in modo cooperativo: una singola operazione geometrica
può completarsi prima di osservare l'annullamento. La validazione dei percorsi
non costituisce un sandbox contro un proprietario ostile del filesystem.
Rimangono i limiti geometrici/campionati e di assenza di certificazione già
indicati dal prodotto. Nessun documento CAD personale usato nelle prove.

Prove: `work/mcp-review/full-tests-result.json`, `full-tests.log`,
`sdk-v1-wheel.log`, `sdk-v2-wheel.log`, `wheel-tests-outside.log`,
`wheel-stdio-proof.json`, `source-artifacts.log`, `host-build.log` e
`packaging-tests.log` nella cartella `work/mcp-review/`.

### Installer MCP verificati sui quattro target

Il [workflow nativo MCP](https://github.com/NoOneExceptEnderk/RatioLab/actions/runs/40693824197)
sul commit `52b2680e08160fa33f92ac87121af89d4ef9c33b` supera **4/4 job**.
La [distribuzione Python dello stesso codice](https://github.com/NoOneExceptEnderk/RatioLab/actions/runs/40693824402)
supera **3/3 job**, con test della wheel eseguiti fuori dal checkout.
I 50 moduli del codice distribuito coincidono con la suite completa da 346 test.

| Sistema nativo | App installata | Companion MCP installato |
|---|---|---|
| Ubuntu 24.04 x86-64 | GUI completa, 9 PNG, export, installazione/rimozione `.run`, runtime `.deb` | Entrambi i protocolli, 13 tool elencati, progetti/Undo, revisioni e percorsi, STEP selettivo con hash, ricerca e interferenze |
| Windows Server 2025 x86-64, target Windows 11 | Setup installato senza MSYS2 sul PATH, GUI ANGLE ES 3.1, 9 PNG, export e disinstallazione | Stesse prove attraverso il vero `RatioLab-MCP.exe` console, con standard streams preservati |
| macOS 15 Apple Silicon | DMG montato, app copiata senza Homebrew sul PATH, GUI OpenGL 4.1, 9 PNG, export e firma ad hoc | Stesse prove attraverso il companion dentro `Contents/MacOS/` |
| macOS 15 Intel | Stesso ciclo completo sul runner Intel | Stesse prove con entrambi i protocolli |

Il Linux nativo supera 50 test mirati senza skip. Windows e ciascun macOS
superano 42 test, con il solo skip dei common-license Debian. Nessuna prova
GUI o MCP degli installer è saltata. I report del companion sono allegati
ai job: `ratiolab-linux-verification` e i tre artifact GUI Windows/macOS.
`build-evidence.json` riporta risultati MCP e grafici di tutti e quattro i target.

Il revisore ha scaricato i sei installer, controllato hash e formati e letto
personalmente i quattro log completi. L'SDK ufficiale 2.3.0 supera anche le
67 chiamate al companion compilato locale. Un ulteriore audit dei sei tipi
errati/versione futura verifica sul runtime pubblicato gli errori JSON-RPC e
lo schema ufficiale UnsupportedProtocolVersionErrorData; nessuna modifica di
produzione era necessaria, perché la validazione era già presente.

Log: `work/ci-40693824197-*.log`, report originali sotto
`work/final-installers-40693824197/`, `work/mcp-review/sdk-v2-frozen.log` e
`protocol-types-parent-proof.json`. Al momento di queste prove il repository e la bozza erano ancora privati/non pubblicati;
gli otto asset sono verificati anche contro i digest SHA-256 restituiti da GitHub.
Le prove native usano renderer software e non coprono ogni GPU/driver personale.
Restano il Setup Windows senza firma del produttore e la firma ad hoc macOS,
senza notarizzazione Apple. Le successive variazioni di sola documentazione
non cambiano i runtime compilati in questo workflow.

### English filenames and first public preview preparation — 2026-10-28

The repository owner made the repository public and selected GPL-3.0-only.
`LICENSE`, `COPYRIGHT`, source-file SPDX notices and package metadata now
attribute the project to NoOneExceptEnderk. Dependency notices keep their own
licenses. Wheel and native resource allowlists include the exact project notices;
artifact verification rejects missing notices and inconsistent wheel metadata.

Repository documents, launch script, catalogs and examples use English names.
Exports use `.calculations.json`, `.calculations.txt` and `.machining.json`;
generated STEP assets use `solids/`. Existing configuration identifiers, parameter
keys and user exports are retained. `ui-preferences.json` takes precedence, with
fallback to the previous user preference file before a legacy source checkout;
new saves preserve older files. Tests exercise migration on all three OS paths
and verify that an invalid present new file does not resurrect stale settings.

An xHigh subagent translated runtime comments/docstrings and wrote
`CONTRIBUTING.md`. The parent compared executable ASTs against the prior public
source: all 49 runtime modules other than the deliberately changed preference
helper match after the approved filename substitutions and docstring removal.
The parent also repaired the local Linux shortcuts after detecting their old
source-launcher path. Full source-suite and refreshed native evidence follow
when those checks complete.

### Bounded event dispatch in installed GUI checks

The initial refreshed native run 40704451204 passed Linux, Windows and Apple
Silicon, but the Intel macOS GUI workspace check reached its existing 180-second
outer timeout after a successful bundled OpenGL diagnostic and headless feature
check. Inspection found an unbounded `while context.pending()` drain: a software
renderer with continuously ready frame events could prevent checking readiness
or the inner deadline. The child process supplied no stack, so this is a proven
event-loop defect rather than a claim that its exact timed-out phase was observed.

The installed workspace and wheel smoke checks now use one shared nonblocking
dispatch helper, revisiting readiness and the deadline after each iteration.
Two regressions cover continuously ready events and timeout enforcement. The
outer 180-second native GUI limit is unchanged; crashes, incomplete reports and
missing graphics checks remain failures. Temporary progress messages were used during local diagnosis and removed
before final packaging so the original JSON report format remains intact. An independent xHigh review and all five
focused event-loop/GUI-gate tests passed before rebuilding the native packages.

### Reproduced software-renderer export completion and frame synchronization

The parent reproduced the Linux capture failure with the same Ubuntu24.04,
GTK4.14.5, Mesa/llvmpipe and Xvfb stack, using an immutable source snapshot.
An explicit frame-clock `after-paint` barrier now waits for a later completed
frame, a mapped/nonzero GLArea and uploaded geometry after layout changes,
before export and each family screenshot. Three regressions cover the later
frame, invalid dimensions/timeout cleanup and a missing frame clock.

A separate timed probe showed that the full package was written in 0.573s,
while its GUI completion stayed pending for 30 s with `busy=True`. The independent
reviewer reproduced this with an immediate worker: a callback at default event
priority ran, while the default idle callback remained behind busy animation.
The brief background completion now uses `GLib.PRIORITY_DEFAULT`. A real GTK
regression with a continuously ready main-context source fails on the old code
and passes on the correction; all six export GUI tests passed independently.

The final source self-test in that same Ubuntu24/Xvfb environment passes the
complete package, all nine nonblank family PNGs and all six feature areas.
All original native GUI resource/time limits remain unchanged. The parent
retains the negative reproduction, worker timing and positive report under
`work/english-release-review/`; those local paths are not part of an installer.

The parent also exercised the unchanged installer entrypoint against the real
Ubuntu24/Xvfb GUI self-test after removing temporary Python progress output.
Its `--report` file parses directly as JSON and records all nine previews, six
feature areas and the complete package. The entrypoint intentionally captures
both Python streams for diagnostics; success must therefore emit only the
machine-readable report. The isolated ToolWorkspaceTests pass 7/7, including
the dock width, three text scales and scroll tests whose fixed-delay checks
were affected by the shared desktop display. No layout assertions were removed
or weakened. Final source-suite/native results are recorded below.

### Single-workspace GUI verification and native timeout diagnostics

Run 40713248331 passed Linux, Windows and Apple Silicon native installers and
all three Python distribution jobs, but the Intel macOS workspace process still
reached the existing 180-second limit. Its separate OpenGL diagnostic succeeded.
The GUI self-test now performs dependency checks without creating a preliminary
window, then obtains graphics metadata directly from the actual workspace after
all nine nonblank family captures and the full package export. This avoids a
second GTK/Cocoa window lifecycle in one process; the earlier Intel timeout had
no native stack, so that lifecycle remains a hypothesis rather than a proven cause.

Four focused regressions preserve the single-workspace path, actual-context
metadata, minimum desktop/ES versions and graphics errors. The independent
xHigh agent ran the real Ubuntu24/Xvfb self-test through the unchanged installer
entrypoint in 5.892 seconds: clean JSON, nine previews, six feature checks and
workspace export passed. The standalone GUI diagnostic remains unchanged.
The parent reviewed the code and passed 63 packaging/runtime tests.

The native GUI runner retains the 180-second pass/fail deadline. On macOS only,
a timeout now collects a bounded native process sample before killing the child,
in separate files alongside the JSON report. Four additional regressions cover
success, nonzero exits, sampling before kill, sampling errors and cleanup.
