# RatioLab

![RatioLab](../../src/ratiolab_resources/branding/ratiolab-logo-dark.png)

**Diseña engranajes y reductores, explora su movimiento y exporta modelos para CAD o impresión 3D.**

[Descargar](#download-and-install) · [Guía de usuario (en inglés)](../user-guide.md) · [English](../../README.md) · [Italiano](../../README.it.md) · [Informar de un problema](https://github.com/NoOneExceptEnderk/RatioLab/issues) · [Discord](https://discord.gg/G8NVHNg6J)

**Idiomas:** [English](../../README.md) · [Italiano](../../README.it.md) · **Español** · [Français](fr.md) · [Deutsch](de.md) · [Português (Portugal)](pt.md) · [Русский](ru.md) · [简体中文](zh-CN.md) · [தமிழ்](ta.md)

![Área de trabajo de RatioLab](../../assets/screenshots/workspace.png)

<a id="download-and-install"></a>

## Descargar e instalar

**Descarga uno de los instaladores siguientes. Python, GTK y las bibliotecas necesarias están incluidos.**
No necesitas descargar el código fuente ni instalar herramientas de desarrollo.

Versión actual: **0.1.0 Preview 2** — una versión preliminar; tus comentarios son bienvenidos.

Las descargas para Windows y Linux incluyen la integración con Fusion; Linux se conecta
a Fusion ejecutado mediante Wine. Windows también incluye las correcciones gráficas.
Las descargas para macOS conservan la compilación original de Preview 2.

| Tu equipo | Descarga | Qué hacer |
|---|---|---|
| Windows 11, Intel/AMD de 64 bits | [Instalador de Windows](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.0-preview.2/RatioLab-0.1.0-windows-x86_64-setup.exe) | Abre el instalador y luego inicia RatioLab desde Inicio. |
| macOS 15+, Apple Silicon (M1 o posterior) | [DMG para Apple Silicon](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.0-preview.2/RatioLab-0.1.0-macos-arm64.dmg) | Abre el DMG y arrastra RatioLab a Aplicaciones. |
| macOS 15+, Intel | [DMG para Intel](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.0-preview.2/RatioLab-0.1.0-macos-x86_64.dmg) | Abre el DMG y arrastra RatioLab a Aplicaciones. |
| Ubuntu 24.04+ / Linux compatible, x86-64 | [Paquete Debian/Ubuntu](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.0-preview.2/ratiolab_0.1.0_amd64.deb) · [Otro instalador para Linux](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.0-preview.2/RatioLab-0.1.0-linux-x86_64.run) | Abre el archivo `.deb` con tu instalador de software. Para el archivo `.run`, sigue la guía de instalación. |

Linux requiere glibc 2.39 o posterior. Todos los sistemas requieren un controlador gráfico compatible.
El instalador de Windows no está firmado; macOS utiliza una firma ad hoc sin notarización de Apple.
Tu sistema puede mostrar una advertencia de editor desconocido o bloquear el inicio.

[Guía de instalación, requisitos y desinstalación (en inglés)](../installation.md) · [Todos los archivos de la versión y sus sumas de verificación](https://github.com/NoOneExceptEnderk/RatioLab/releases/tag/v0.1.0-preview.2)

## Qué puedes hacer

- Crear nueve familias de engranajes y reductores: engranajes rectos, helicoidales, de doble hélice, planetarios, cicloidales, de onda de deformación, de tornillo sin fin, de ejes paralelos y de dentado interior.
- Editar parámetros e inspeccionar un modelo 3D animado con selección de componentes y mediciones por muestreo.
- Guardar proyectos, deshacer cambios, buscar entre combinaciones finitas de parámetros y ejecutar comprobaciones discretas de interferencias.
- Exportar STEP, STL, SVG/DXF, listas de componentes, informes de cálculo o paquetes completos.
- Enviar modelos a SolidCraft o [Autodesk Fusion](../fusion360.md) (guía en inglés); Fusion recibe sólidos STEP con metadatos de parámetros de RatioLab mediante el complemento incluido.
- Utilizar el [asistente MCP](../mcp.md) incluido, que funciona sin conexión, para trabajar con un agente (guía en inglés). Las integraciones CAD son opcionales; las exportaciones independientes funcionan sin una aplicación CAD.

## Iniciar un diseño

1. Abre RatioLab y elige una familia de engranajes o reductores.
2. Define las dimensiones y las opciones de montaje; inspecciona la vista previa y los resultados indicados.
3. Guarda tu proyecto y elige **Export…** para obtener archivos para CAD o impresión.

Consulta la [guía de usuario (en inglés)](../user-guide.md) y los [proyectos de ejemplo](../../examples/) para obtener más detalles.
La interfaz de la aplicación está en inglés.

## Limitaciones actuales

Esta versión preliminar ofrece modelos para estudios geométricos y cinemáticos. No certifica
la resistencia, la vida útil ni la aptitud para la fabricación. Las comprobaciones de interferencias y
las mediciones utilizan superficies muestreadas; las construcciones de tornillo sin fin y de onda de deformación siguen siendo
modelos de estudio. Lee la sección sobre [precisión y limitaciones (en inglés)](../user-guide.md#accuracy-and-limitations)
antes de utilizar los diseños exportados.

## Comunidad

Únete al [Discord de RatioLab](https://discord.gg/G8NVHNg6J) para hacer preguntas, compartir comentarios y conversar sobre el proyecto.

## Contribuir

El código está en [`src/`](../../src/), las pruebas automatizadas en [`tests/`](../../tests/) y la documentación
en [`docs/`](../). Consulta [CONTRIBUTING.md (en inglés)](../../CONTRIBUTING.md) para conocer la configuración del entorno, la arquitectura
y las comprobaciones, y [CHANGELOG.md (en inglés)](../../CHANGELOG.md) para ver los cambios de cada versión.

¿Has encontrado un problema? [Abre una incidencia](https://github.com/NoOneExceptEnderk/RatioLab/issues)
e indica tu sistema, la versión de RatioLab, los pasos para reproducirlo y el archivo de proyecto correspondiente.

## Licencia

Copyright © 2026 **NoOneExceptEnderk**. Distribuido bajo la [GNU GPL, solo versión 3](../../LICENSE)
(`GPL-3.0-only`). Consulta [COPYRIGHT](../../COPYRIGHT) para ver las atribuciones y los avisos.
Los componentes de terceros conservan sus propias licencias.
