# RatioLab

![RatioLab](../../src/ratiolab_resources/branding/ratiolab-logo-dark.png)

**Zahnräder und Getriebe entwerfen, ihre Bewegung untersuchen und Modelle für CAD oder den 3D-Druck exportieren.**

[Herunterladen](#download-and-install) · [Benutzerhandbuch (Englisch)](../user-guide.md) · [English](../../README.md) · [Italiano](../../README.it.md) · [Problem melden](https://github.com/NoOneExceptEnderk/RatioLab/issues) · [Discord](https://discord.gg/G8NVHNg6J)

**Sprachen:** [English](../../README.md) · [Italiano](../../README.it.md) · [Español](es.md) · [Français](fr.md) · **Deutsch** · [Português (Portugal)](pt.md) · [Русский](ru.md) · [简体中文](zh-CN.md) · [தமிழ்](ta.md)

![RatioLab-Arbeitsbereich](../../assets/screenshots/workspace.png)

<a id="download-and-install"></a>

## Herunterladen und installieren

**Lade eines der folgenden Installationsprogramme herunter. Python, GTK und die erforderlichen Bibliotheken sind enthalten.**
Du musst weder den Quellcode herunterladen noch Entwicklungswerkzeuge installieren.

Aktuelle Version: **0.1.2**.

Die Pakete werden nach erfolgreichen nativen CI-Prüfungen veröffentlicht. Plattformnachweise stehen in den Versionshinweisen; die Einschränkungen der Signierung sind unten aufgeführt.

| Dein Computer | Download | Vorgehen |
|---|---|---|
| Windows 11, 64-Bit Intel/AMD | [Windows-Setup](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.2/RatioLab-0.1.2-windows-x86_64-setup.exe) | Öffne das Installationsprogramm und starte RatioLab anschließend über das Startmenü. |
| macOS 15+, Apple Silicon (M1 oder neuer) | [DMG für Apple Silicon](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.2/RatioLab-0.1.2-macos-arm64.dmg) | Öffne das DMG und ziehe RatioLab in den Ordner „Programme“. |
| macOS 15+, Intel | [DMG für Intel](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.2/RatioLab-0.1.2-macos-x86_64.dmg) | Öffne das DMG und ziehe RatioLab in den Ordner „Programme“. |
| Ubuntu 24.04+ / kompatibles Linux, x86-64 | [Debian/Ubuntu-Paket](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.2/ratiolab_0.1.2_amd64.deb) · [Anderes Linux-Installationsprogramm](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.2/RatioLab-0.1.2-linux-x86_64.run) | Öffne die `.deb`-Datei mit deiner Softwareverwaltung. Folge für die `.run`-Datei der Installationsanleitung. |

Linux benötigt glibc 2.39 oder neuer. Auf allen Systemen ist ein kompatibler Grafiktreiber erforderlich.
Das Windows-Setup ist nicht signiert; macOS verwendet eine Ad-hoc-Signatur ohne Apple-Notarisierung.
Dein System zeigt möglicherweise eine Warnung zu einem unbekannten Herausgeber an oder blockiert den Start.

[Installationsanleitung, Anforderungen und Deinstallation (Englisch)](../installation.md) · [Alle Dateien der Veröffentlichung und Prüfsummen](https://github.com/NoOneExceptEnderk/RatioLab/releases/tag/v0.1.2)

## Was du tun kannst

- Zehn Zahnrad- und Getriebefamilien erzeugen: Stirnräder, Schrägverzahnungen, Doppelschrägverzahnungen, Planeten-, Zykloiden-, Wellen-, Schnecken-, Parallelwellen- und Innenzahnradgetriebe sowie Kegelraddifferentiale mit Handgelenk- oder klassischer Anordnung.
- Parameter bearbeiten und ein animiertes 3D-Modell mit Komponentenauswahl und Messungen anhand von Stichproben untersuchen.
- Projekte speichern, Änderungen rückgängig machen, endliche Parameterkombinationen durchsuchen und diskrete Kollisionsprüfungen ausführen.
- STEP, STL, SVG/DXF, Komponentenlisten, Berechnungsberichte oder vollständige Pakete exportieren.
- Modelle an SolidCraft oder [Autodesk Fusion](../fusion360.md) senden (Anleitung auf Englisch); Fusion erhält über das enthaltene Add-in STEP-Volumenkörper mit RatioLab-Parametermetadaten.
- Den enthaltenen, offline nutzbaren [MCP-Begleiter](../mcp.md) verwenden, um mit einem Agenten zu arbeiten (Anleitung auf Englisch). CAD-Integrationen sind optional; eigenständige Exporte funktionieren ohne CAD-Anwendung.

## Einen Entwurf beginnen

1. Öffne RatioLab und wähle eine Zahnrad- oder Getriebefamilie.
2. Lege Abmessungen und Baugruppenoptionen fest; untersuche die Vorschau und die angezeigten Ergebnisse.
3. Speichere dein Projekt und wähle anschließend **Export…**, um Dateien für CAD oder den Druck zu erzeugen.

Weitere Einzelheiten findest du im [Benutzerhandbuch (Englisch)](../user-guide.md) und in den [Beispielprojekten](../../examples/).
Die Benutzeroberfläche der Anwendung ist auf Englisch.

## Aktuelle Einschränkungen

RatioLab erzeugt maßhaltige Geometrie und ideale Bewegung. Die dokumentierten Konstruktionsprüfungen und numerischen Abtastgrenzen bescheinigen weder Festigkeit noch Lebensdauer oder Fertigungsreife. Kollisionsprüfungen und Messungen verwenden abgetastete Oberflächen; beim Wellengetriebe ist die Verformung vorgegeben, keine elastische Lösung. Lies vor der Verwendung exportierter Entwürfe die [Genauigkeit und Einschränkungen (Englisch)](../user-guide.md#accuracy-and-limitations).

## Community

Tritt dem [RatioLab-Discord](https://discord.gg/G8NVHNg6J) bei, um Fragen zu stellen, Rückmeldungen zu geben und über das Projekt zu diskutieren.

## Mitwirken

Der Code liegt in [`src/`](../../src/), automatisierte Tests in [`tests/`](../../tests/) und die Dokumentation
in [`docs/`](../). Hinweise zur Einrichtung, Architektur und zu Prüfungen findest du in [CONTRIBUTING.md (Englisch)](../../CONTRIBUTING.md),
Änderungen der Veröffentlichungen in [CHANGELOG.md (Englisch)](../../CHANGELOG.md).

Ein Problem gefunden? [Erstelle einen Fehlerbericht](https://github.com/NoOneExceptEnderk/RatioLab/issues)
mit Angaben zu deinem System, der RatioLab-Version, den Schritten zum Reproduzieren und der zugehörigen Projektdatei.

## Lizenz

Copyright © 2026 **NoOneExceptEnderk**. Lizenziert unter der [GNU GPL, ausschließlich Version 3](../../LICENSE)
(`GPL-3.0-only`). Namensnennungen und Hinweise findest du in [COPYRIGHT](../../COPYRIGHT).
Komponenten von Drittanbietern behalten ihre eigenen Lizenzen.
