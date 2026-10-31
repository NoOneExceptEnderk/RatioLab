# RatioLab

![RatioLab](src/ratiolab_resources/branding/ratiolab-logo-dark.png)

**Progetta ingranaggi e riduttori, osservane il movimento ed esporta i modelli per CAD o stampa 3D.**

[Download](#scarica-e-installa) · [Manuale in inglese](docs/user-guide.md) · [English](README.md) · [Segnala un problema](https://github.com/NoOneExceptEnderk/RatioLab/issues) · [App web](https://ratiolab.dev/app/) · [Guida web (in inglese)](docs/web-app.md) · [Discord](https://discord.gg/G8NVHNg6J)

**Lingue:** [English](README.md) · **Italiano** · [Español](docs/readme/es.md) · [Français](docs/readme/fr.md) · [Deutsch](docs/readme/de.md) · [Português (Portugal)](docs/readme/pt.md) · [Русский](docs/readme/ru.md) · [简体中文](docs/readme/zh-CN.md) · [தமிழ்](docs/readme/ta.md)

![Area di lavoro di RatioLab](assets/screenshots/workspace.png)

## Scarica e installa

**Gli installer includono Python, GTK e le librerie necessarie.** Non devi
scaricare i sorgenti o installare strumenti di sviluppo.

Versione disponibile: **0.1.12**.

I pacchetti vengono pubblicati dopo il superamento dei controlli CI nativi. Consulta le note di rilascio per le verifiche delle piattaforme e i limiti di firma indicati sotto.

| Il tuo computer | Download | Installazione |
|---|---|---|
| Windows 11, Intel/AMD a 64 bit | [Setup Windows](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.12/RatioLab-0.1.12-windows-x86_64-setup.exe) | Apri il file scaricato; al termine avvia RatioLab dal menu Start. |
| macOS 15+, Apple Silicon (M1 o successivi) | [DMG Apple Silicon](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.12/RatioLab-0.1.12-macos-arm64.dmg) | Apri il DMG e trascina RatioLab in Applicazioni. |
| macOS 15+, Intel | [DMG Intel](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.12/RatioLab-0.1.12-macos-x86_64.dmg) | Apri il DMG e trascina RatioLab in Applicazioni. |
| Ubuntu 24.04+ / Linux compatibile, x86-64 | [Pacchetto Debian/Ubuntu](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.12/ratiolab_0.1.12_amd64.deb) · [Installer per altri Linux](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.12/RatioLab-0.1.12-linux-x86_64.run) | Apri il `.deb` con il gestore software; per il `.run` segui la guida. |

Linux richiede glibc 2.39 o successiva. Serve un driver grafico compatibile.
L’installer Windows non ha ancora una firma del produttore; l’app macOS ha
firma ad-hoc e non è notarizzata da Apple. Il sistema può mostrare un avviso o bloccare l’avvio.

[Guida all’installazione e alla disinstallazione](docs/installation.md) · [Tutti i file e i checksum](https://github.com/NoOneExceptEnderk/RatioLab/releases/tag/v0.1.12)

## Cosa puoi fare

- Generare undici famiglie di ingranaggi e trasmissioni, inclusi differenziali conici in configurazione polso o classica e riduttori Wolfrom a due dentature diritte.
- Modificare i parametri, osservare l’anteprima 3D animata e selezionare i componenti.
- Salvare progetti, annullare modifiche, cercare combinazioni e controllare le interferenze con campionamento discreto.
- Esportare STEP, STL, SVG/DXF, distinte, relazioni di calcolo e pacchetti completi.
- Inviare modelli a SolidCraft o [Autodesk Fusion](docs/fusion360.md); Fusion riceve solidi STEP e metadati dei parametri tramite il modulo aggiuntivo incluso.
- Collegare un agente tramite il [companion MCP incluso](docs/mcp.md), senza aprire la GUI.

L’interfaccia dell’app e il manuale completo sono in inglese.
Le integrazioni CAD sono facoltative: gli export autonomi non richiedono un CAD installato.

## Primo progetto

1. Apri RatioLab e scegli una famiglia.
2. Imposta le dimensioni e le opzioni di assemblaggio; controlla anteprima e risultati.
3. Salva il progetto e usa **Export…** per creare i file.

Trovi altre indicazioni nel [manuale](docs/user-guide.md) e nei [progetti di esempio](examples/).

## Limiti attuali

RatioLab genera geometrie dimensionali e moto ideale. I controlli costruttivi e
i limiti numerici sono riportati nel modello e nella relazione di calcolo;
non certificano resistenza, durata o idoneità alla produzione. Misure e
interferenze usano superfici campionate. Consulta i
[limiti documentati](docs/user-guide.md#accuracy-and-limitations) e le equazioni
per [vite e corona](docs/technical/worm.md) e
[differenziali conici](docs/technical/differential.md) e
[strain wave](docs/technical/strain-wave.md).

## Community

Entra nel [Discord di RatioLab](https://discord.gg/G8NVHNg6J) per domande, feedback e discussioni sul progetto.

## Contribuire e licenza

Il codice è in [`src/`](src/), i test in [`tests/`](tests/) e la documentazione
in [`docs/`](docs/). [CONTRIBUTING.md](CONTRIBUTING.md) spiega come contribuire;
[CHANGELOG.md](CHANGELOG.md) riporta le novità.

Copyright © 2026 **NoOneExceptEnderk**. Licenza [GNU GPL versione 3 only](LICENSE)
(`GPL-3.0-only`), con [attribuzioni e avvisi](COPYRIGHT).
Le dipendenze mantengono le proprie licenze.
