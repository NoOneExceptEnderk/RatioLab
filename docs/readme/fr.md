# RatioLab

![RatioLab](../../src/ratiolab_resources/branding/ratiolab-logo-dark.png)

**Concevez des engrenages et des réducteurs, explorez leur mouvement et exportez des modèles pour la CAO ou l'impression 3D.**

[Télécharger](#download-and-install) · [Guide d'utilisation (en anglais)](../user-guide.md) · [English](../../README.md) · [Italiano](../../README.it.md) · [Signaler un problème](https://github.com/NoOneExceptEnderk/RatioLab/issues) · [Discord](https://discord.gg/G8NVHNg6J)

**Langues:** [English](../../README.md) · [Italiano](../../README.it.md) · [Español](es.md) · **Français** · [Deutsch](de.md) · [Português (Portugal)](pt.md) · [Русский](ru.md) · [简体中文](zh-CN.md) · [தமிழ்](ta.md)

![Espace de travail de RatioLab](../../assets/screenshots/workspace.png)

<a id="download-and-install"></a>

## Télécharger et installer

**Téléchargez l'un des programmes d'installation ci-dessous. Python, GTK et les bibliothèques nécessaires sont inclus.**
Vous n'avez pas besoin de télécharger le code source ni d'installer des outils de développement.

Version actuelle : **0.1.11**.

Les paquets sont publiés après la réussite des contrôles CI natifs. Consultez les notes de version pour les résultats par plateforme et les limites de signature indiquées ci-dessous.

| Votre ordinateur | Téléchargement | Marche à suivre |
|---|---|---|
| Windows 11, Intel/AMD 64 bits | [Programme d'installation Windows](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.11/RatioLab-0.1.11-windows-x86_64-setup.exe) | Ouvrez le programme d'installation, puis lancez RatioLab depuis le menu Démarrer. |
| macOS 15+, Apple Silicon (M1 ou plus récent) | [DMG pour Apple Silicon](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.11/RatioLab-0.1.11-macos-arm64.dmg) | Ouvrez le DMG et faites glisser RatioLab dans Applications. |
| macOS 15+, Intel | [DMG pour Intel](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.11/RatioLab-0.1.11-macos-x86_64.dmg) | Ouvrez le DMG et faites glisser RatioLab dans Applications. |
| Ubuntu 24.04+ / Linux compatible, x86-64 | [Paquet Debian/Ubuntu](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.11/ratiolab_0.1.11_amd64.deb) · [Autre programme d'installation Linux](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.11/RatioLab-0.1.11-linux-x86_64.run) | Ouvrez le fichier `.deb` avec votre gestionnaire d'installation de logiciels. Pour le fichier `.run`, suivez le guide d'installation. |

Linux nécessite glibc 2.39 ou une version ultérieure. Un pilote graphique compatible est nécessaire sur tous les systèmes.
Le programme d'installation Windows n'est pas signé ; macOS utilise une signature ad hoc sans notarisation Apple.
Votre système peut afficher un avertissement concernant un éditeur inconnu ou bloquer le lancement.

[Guide d'installation, configuration requise et désinstallation (en anglais)](../installation.md) · [Tous les fichiers de la version et leurs sommes de contrôle](https://github.com/NoOneExceptEnderk/RatioLab/releases/tag/v0.1.11)

## Ce que vous pouvez faire

- Construire dix familles d’engrenages et de transmissions : à denture droite, hélicoïdaux, à double hélice, planétaires, cycloïdaux, à onde de déformation, à vis sans fin, à arbres parallèles, à denture intérieure et différentiels coniques avec configurations de poignet ou classiques.
- Modifier les paramètres et examiner un modèle 3D animé avec sélection des composants et mesures par échantillonnage.
- Enregistrer des projets, annuler des modifications, rechercher parmi des combinaisons finies de paramètres et effectuer des contrôles discrets d'interférence.
- Exporter des fichiers STEP, STL, SVG/DXF, des listes de composants, des rapports de calcul ou des ensembles complets.
- Envoyer des modèles à SolidCraft ou à [Autodesk Fusion](../fusion360.md) (guide en anglais) ; Fusion reçoit des solides STEP accompagnés des métadonnées de paramètres RatioLab grâce au complément inclus.
- Utiliser le [compagnon MCP](../mcp.md) inclus, qui fonctionne hors ligne, pour travailler avec un agent (guide en anglais). Les intégrations CAO sont facultatives ; les exports autonomes fonctionnent sans application de CAO.

## Commencer une conception

1. Ouvrez RatioLab et choisissez une famille d'engrenages ou de réducteurs.
2. Définissez les dimensions et les options d'assemblage ; examinez l'aperçu et les résultats affichés.
3. Enregistrez votre projet, puis choisissez **Export…** pour obtenir des fichiers destinés à la CAO ou à l'impression.

Consultez le [guide d'utilisation (en anglais)](../user-guide.md) et les [exemples de projets](../../examples/) pour plus de détails.
L'interface de l'application est en anglais.

## Limites actuelles

RatioLab génère une géométrie dimensionnelle et un mouvement idéal. Les contrôles de construction et les limites numériques documentés ne certifient ni la résistance, ni la durée de vie, ni l’aptitude à la fabrication. Les contrôles d’interférence et les mesures utilisent des surfaces échantillonnées ; la déformation du mécanisme à onde est prescrite, sans solution élastique. Avant d’utiliser les modèles exportés, consultez la [précision et les limites (en anglais)](../user-guide.md#accuracy-and-limitations).

## Communauté

Rejoignez le [Discord de RatioLab](https://discord.gg/G8NVHNg6J) pour poser des questions, donner votre avis et discuter du projet.

## Contribuer

Le code se trouve dans [`src/`](../../src/), les tests automatisés dans [`tests/`](../../tests/) et la documentation
dans [`docs/`](../). Consultez [CONTRIBUTING.md (en anglais)](../../CONTRIBUTING.md) pour la configuration de l'environnement, l'architecture
et les vérifications, ainsi que [CHANGELOG.md (en anglais)](../../CHANGELOG.md) pour les changements de chaque version.

Vous avez trouvé un problème ? [Ouvrez un ticket](https://github.com/NoOneExceptEnderk/RatioLab/issues)
en précisant votre système, la version de RatioLab, les étapes pour le reproduire et le fichier de projet concerné.

## Licence

Copyright © 2026 **NoOneExceptEnderk**. Distribué sous [GNU GPL version 3 uniquement](../../LICENSE)
(`GPL-3.0-only`). Consultez [COPYRIGHT](../../COPYRIGHT) pour les attributions et les mentions légales.
Les composants tiers conservent leurs propres licences.
