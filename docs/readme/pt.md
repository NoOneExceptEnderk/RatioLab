# RatioLab

![RatioLab](../../src/ratiolab_resources/branding/ratiolab-logo-dark.png)

**Crie engrenagens e redutores, explore o seu movimento e exporte modelos para CAD ou impressão 3D.**

[Transferir](#download-and-install) · [Guia do utilizador (em inglês)](../user-guide.md) · [English](../../README.md) · [Italiano](../../README.it.md) · [Comunicar um problema](https://github.com/NoOneExceptEnderk/RatioLab/issues) · [Discord](https://discord.gg/G8NVHNg6J)

**Idiomas:** [English](../../README.md) · [Italiano](../../README.it.md) · [Español](es.md) · [Français](fr.md) · [Deutsch](de.md) · **Português (Portugal)** · [Русский](ru.md) · [简体中文](zh-CN.md) · [தமிழ்](ta.md)

![Área de trabalho do RatioLab](../../assets/screenshots/workspace.png)

<a id="download-and-install"></a>

## Transferir e instalar

**Transfira um dos instaladores abaixo. Python, GTK e as bibliotecas necessárias estão incluídos.**
Não precisa de transferir o código-fonte nem de instalar ferramentas de desenvolvimento.

Versão atual: **0.1.9**.

Os pacotes são publicados após passarem nas verificações nativas de CI. Consulte as notas da versão para os resultados por plataforma e as limitações de assinatura indicadas abaixo.

| O seu computador | Transferência | O que fazer |
|---|---|---|
| Windows 11, Intel/AMD de 64 bits | [Instalador para Windows](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.9/RatioLab-0.1.9-windows-x86_64-setup.exe) | Abra o instalador e depois inicie o RatioLab a partir do menu Iniciar. |
| macOS 15+, Apple Silicon (M1 ou mais recente) | [DMG para Apple Silicon](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.9/RatioLab-0.1.9-macos-arm64.dmg) | Abra o DMG e arraste o RatioLab para Aplicações. |
| macOS 15+, Intel | [DMG para Intel](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.9/RatioLab-0.1.9-macos-x86_64.dmg) | Abra o DMG e arraste o RatioLab para Aplicações. |
| Ubuntu 24.04+ / Linux compatível, x86-64 | [Pacote Debian/Ubuntu](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.9/ratiolab_0.1.9_amd64.deb) · [Outro instalador para Linux](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.9/RatioLab-0.1.9-linux-x86_64.run) | Abra o ficheiro `.deb` com o seu instalador de software. Para o ficheiro `.run`, siga o guia de instalação. |

O Linux requer glibc 2.39 ou mais recente. Todos os sistemas requerem um controlador gráfico compatível.
O instalador para Windows não está assinado; o macOS utiliza uma assinatura ad hoc sem notarização da Apple.
O sistema pode apresentar um aviso de editor desconhecido ou bloquear o início da aplicação.

[Guia de instalação, requisitos e desinstalação (em inglês)](../installation.md) · [Todos os ficheiros da versão e somas de verificação](https://github.com/NoOneExceptEnderk/RatioLab/releases/tag/v0.1.9)

## O que pode fazer

- Criar dez famílias de engrenagens e transmissões: de dentes retos, helicoidais, de dupla hélice, planetárias, cicloidais, de onda de deformação, de parafuso sem-fim, de eixos paralelos, de dentado interno e diferenciais cónicos com configurações de punho ou clássicas.
- Editar parâmetros e inspecionar um modelo 3D animado com seleção de componentes e medições por amostragem.
- Guardar projetos, anular alterações, pesquisar combinações finitas de parâmetros e executar verificações discretas de interferências.
- Exportar STEP, STL, SVG/DXF, listas de componentes, relatórios de cálculo ou pacotes completos.
- Enviar modelos para o SolidCraft ou o [Autodesk Fusion](../fusion360.md) (guia em inglês); o Fusion recebe sólidos STEP com metadados dos parâmetros do RatioLab através do suplemento incluído.
- Utilizar o [assistente MCP](../mcp.md) incluído, que funciona sem ligação à Internet, para trabalhar com um agente (guia em inglês). As integrações CAD são opcionais; as exportações autónomas funcionam sem uma aplicação CAD.

## Iniciar um projeto

1. Abra o RatioLab e escolha uma família de engrenagens ou redutores.
2. Defina as dimensões e as opções de montagem; inspecione a pré-visualização e os resultados apresentados.
3. Guarde o projeto e escolha **Export…** para obter ficheiros para CAD ou impressão.

Consulte o [guia do utilizador (em inglês)](../user-guide.md) e os [projetos de exemplo](../../examples/) para obter mais detalhes.
A interface da aplicação está em inglês.

## Limitações atuais

O RatioLab gera geometria dimensional e movimento ideal. As verificações construtivas e os limites numéricos documentados não certificam resistência, vida útil ou aptidão para fabrico. As verificações de interferências e as medições utilizam superfícies amostradas; a deformação do mecanismo de onda é prescrita, não uma solução elástica. Antes de utilizar os projetos exportados, consulte a [precisão e as limitações (em inglês)](../user-guide.md#accuracy-and-limitations).

## Comunidade

Junte-se ao [Discord do RatioLab](https://discord.gg/G8NVHNg6J) para fazer perguntas, dar sugestões e conversar sobre o projeto.

## Contribuir

O código encontra-se em [`src/`](../../src/), os testes automatizados em [`tests/`](../../tests/) e a documentação
em [`docs/`](../). Consulte [CONTRIBUTING.md (em inglês)](../../CONTRIBUTING.md) para saber mais sobre a configuração do ambiente, a arquitetura
e as verificações, e [CHANGELOG.md (em inglês)](../../CHANGELOG.md) para conhecer as alterações de cada versão.

Encontrou um problema? [Abra uma ocorrência](https://github.com/NoOneExceptEnderk/RatioLab/issues)
com o seu sistema, a versão do RatioLab, os passos para reproduzir o problema e o ficheiro de projeto relevante.

## Licença

Copyright © 2026 **NoOneExceptEnderk**. Licenciado sob a [GNU GPL, apenas versão 3](../../LICENSE)
(`GPL-3.0-only`). Consulte [COPYRIGHT](../../COPYRIGHT) para as atribuições e os avisos.
Os componentes de terceiros mantêm as suas próprias licenças.
