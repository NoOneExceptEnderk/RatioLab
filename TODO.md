# Roadmap del generatore di ingranaggi e riduttori

## Direzione del prodotto

Applicazione autonoma per creare ingranaggi e riduttori destinati ai software
CAD. SolidCraft è una delle integrazioni attualmente implementate, non
l'identità del prodotto. Il nome pubblico è **RatioLab**. È stato scelto il
monogramma RL compatto nella versione B bicolore, con dettagli verde acqua e
base della L allungata; gli asset per app e GitHub sono in `assets/branding/`.

Obiettivo: ridurre il superfluo, rendere chiaro e affidabile il percorso
**scegli il modello → imposta le dimensioni → controlla l'anteprima → esporta**,
preparare il progetto per GitHub e in seguito riscriverlo in Rust.
Non ampliare ora il catalogo dei riduttori o la preparazione alla stampa.
La gestione dei materiali, le verifiche di resistenza e i parametri di
produzione sono esclusi dal progetto.

## Prossimo lavoro, in ordine

- [x] **1. Semplificare il prodotto e rifare la UI** — scelto e applicato il
  Workspace tecnico: parametri a sinistra, anteprima dominante, barra del moto
  unica, risultati geometrici, export nell'intestazione e CAD nel proprio menu.
  - Dare priorità a famiglia/variante, parametri geometrici, anteprima,
    rapporto effettivo, dimensioni principali e avvisi pertinenti.
  - Usare un pannello parametri a sinistra e anteprima centrale. Mostrare
    solo i parametri applicabili alla famiglia scelta, con unità e
    raggruppamenti coerenti.
  - Riunire riproduzione e velocità in una sola barra del moto; mantenere
    viste, sezione, esploso e visibilità vicini all'anteprima.
  - Rendere **Esporta** l'azione conclusiva principale. Spostare connessione,
    stato e invio a SolidCraft in un'area di integrazione CAD secondaria.
  - Rendere carichi nominali, distinta e report accessibili da sezioni avanzate;
    cuscinetti, giochi e fissaggi restano disponibili nell'assieme.
  - Rimuovere comandi duplicati, testi ripetitivi e riepiloghi senza utilità
    nel flusso principale. La rimozione di interi moduli sarà valutata
    separatamente.
  - Distinguere nel catalogo i modelli geometrici di studio (attualmente
    strain wave e vite/corona) dai modelli con profili più completi.
  - Verificare la UI su finestre ridotte, navigazione da tastiera, errori di
    input e configurazioni già salvate, senza cambiare le geometrie.
- [ ] **2. Rendere solido il percorso di generazione ed esportazione** —
  misurare dove si perde tempo, evitare rigenerazioni inutili e migliorare
  i casi realmente lenti. Separare la scelta del formato dall'integrazione
  con uno specifico CAD; verificare solidi, fori, unità e coordinate con
  esempi riproducibili. L'esportazione STEP autonoma va verificata e resa
  esplicita: la presenza di asset STEP nel pacchetto attuale non equivale
  a un comando di esportazione STEP completo per ogni componente.
- [ ] **3. Completare la gestione minima dei progetti** — modifiche non
  salvate, annulla/ripristina dei parametri, file recenti e salvataggio
  affidabile; mantenere compatibili le configurazioni JSON esistenti.
- [ ] **4. Preparare la prima pubblicazione su GitHub** — nome e identità
  RatioLab definiti; scegliere la licenza con il proprietario e verificare provenienza di codice,
  cataloghi e risorse; aggiungere istruzioni di installazione da un clone
  pulito, screenshot aggiornati e guida ai contributi. Rendere portabili
  avvio e collegamento desktop (oggi contiene percorsi personali), separare
  i dati utente dai sorgenti e predisporre controlli automatici con test
  geometrici separati dai test che richiedono GTK/OpenGL. Pubblicare il
  repository quando questi elementi sono pronti.
- [ ] **5. Riscrivere in Rust dopo aver stabilizzato il flusso** — fissare
  esempi e risultati di riferimento della versione Python; definire un
  nucleo per parametri, validazione, geometria ed esportazione indipendente
  dalla UI. Portare e confrontare una famiglia alla volta, poi collegare
  anteprima, interfaccia e adattatori CAD. Scegliere il toolkit grafico dopo
  aver verificato i requisiti della nuova UI; la riscrittura deve conservare
  la compatibilità dei progetti e dimostrare i benefici con misure.

## Rimandato: nuove funzioni da rivalutare dopo la semplificazione

- [ ] **Ricerca guidata delle dimensioni** — proporre combinazioni valide
  nella famiglia scelta a partire da rapporto, ingombro e parametri bloccati.
- [ ] **Recupero automatico della configurazione** — dopo la gestione minima
  dei progetti e dei dati utente.
- [ ] **Esportazione dedicata alla stampa** — scelta dei componenti,
  esclusione della ferramenta, posa sul piano e formato 3MF multioggetto.
