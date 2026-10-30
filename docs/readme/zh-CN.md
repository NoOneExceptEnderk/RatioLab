# RatioLab

![RatioLab](../../src/ratiolab_resources/branding/ratiolab-logo-dark.png)

**设计齿轮和减速器，探索其运动，并导出用于 CAD 或 3D 打印的模型。**

[下载](#download-and-install) · [用户指南（英文）](../user-guide.md) · [English](../../README.md) · [Italiano](../../README.it.md) · [报告问题](https://github.com/NoOneExceptEnderk/RatioLab/issues) · [Discord](https://discord.gg/G8NVHNg6J)

**语言:** [English](../../README.md) · [Italiano](../../README.it.md) · [Español](es.md) · [Français](fr.md) · [Deutsch](de.md) · [Português (Portugal)](pt.md) · [Русский](ru.md) · **简体中文** · [தமிழ்](ta.md)

![RatioLab 工作区](../../assets/screenshots/workspace.png)

<a id="download-and-install"></a>

## 下载与安装

**请下载下方的安装包，其中已包含 Python、GTK 和所需的库。**
无需下载源代码，也无需安装开发工具。

当前版本：**0.1.2**。

各平台安装包通过原生 CI 检查后才会发布。平台验证结果请参阅发布说明，签名限制见下文。

| 你的计算机 | 下载 | 操作步骤 |
|---|---|---|
| Windows 11，64 位 Intel/AMD | [Windows 安装程序](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.2/RatioLab-0.1.2-windows-x86_64-setup.exe) | 打开安装程序，然后从“开始”菜单启动 RatioLab。 |
| macOS 15+，Apple Silicon（M1 或更新型号） | [Apple Silicon DMG](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.2/RatioLab-0.1.2-macos-arm64.dmg) | 打开 DMG，将 RatioLab 拖入“应用程序”文件夹。 |
| macOS 15+，Intel | [Intel DMG](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.2/RatioLab-0.1.2-macos-x86_64.dmg) | 打开 DMG，将 RatioLab 拖入“应用程序”文件夹。 |
| Ubuntu 24.04+ / 兼容的 Linux，x86-64 | [Debian/Ubuntu 软件包](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.2/ratiolab_0.1.2_amd64.deb) · [其他 Linux 安装程序](https://github.com/NoOneExceptEnderk/RatioLab/releases/download/v0.1.2/RatioLab-0.1.2-linux-x86_64.run) | 使用系统的软件安装工具打开 `.deb`。对于 `.run`，请按照安装指南操作。 |

Linux 需要 glibc 2.39 或更新版本。所有系统都需要兼容的显卡驱动程序。
Windows 安装程序未签名；macOS 版本采用临时签名（ad-hoc signing），未经 Apple 公证。
系统可能会显示“未知发布者”警告或阻止启动。

[安装指南、系统要求与卸载（英文）](../installation.md) · [所有发布文件与校验和](https://github.com/NoOneExceptEnderk/RatioLab/releases/tag/v0.1.2)

## 功能

- 创建十类齿轮和传动机构：直齿、斜齿、双斜齿、行星、摆线、谐波、蜗杆、平行轴、内齿轮，以及腕部或经典配置的锥齿轮差速器。
- 编辑参数，查看带动画的 3D 模型，并选择组件、进行基于采样的测量。
- 保存项目、撤销更改、搜索有限的参数组合，并执行离散干涉检查。
- 导出 STEP、STL、SVG/DXF、组件清单、计算报告或完整文件包。
- 将模型发送至 SolidCraft 或 [Autodesk Fusion（英文指南）](../fusion360.md)；Fusion 通过随附的插件接收 STEP 实体及 RatioLab 参数元数据。
- 使用随附的离线 [MCP 配套工具（英文指南）](../mcp.md)与智能体协作。CAD 集成是可选功能；无需 CAD 应用程序也能独立导出。

## 开始设计

1. 打开 RatioLab，选择齿轮或减速器类型。
2. 设置尺寸和装配选项，查看预览及所报告的结果。
3. 保存项目，然后选择 **Export…**，导出用于 CAD 或打印的文件。

更多信息请参阅[用户指南（英文）](../user-guide.md)和[示例项目](../../examples/)。
应用程序界面为英文。

## 当前限制

RatioLab 生成尺寸几何与理想运动。文档中的结构检查和数值采样限制并不认证强度、使用寿命或制造就绪程度。干涉检查与测量使用采样表面；谐波传动采用规定的变形，而非弹性求解。使用导出设计前，请阅读[精度与限制（英文）](../user-guide.md#accuracy-and-limitations)。

## 社区

加入 [RatioLab Discord](https://discord.gg/G8NVHNg6J)，提问、反馈并讨论项目。

## 参与贡献

代码位于 [`src/`](../../src/)，自动化测试位于 [`tests/`](../../tests/)，文档位于 [`docs/`](../)。
环境设置、架构和检查方法请参阅 [CONTRIBUTING.md（英文）](../../CONTRIBUTING.md)，
版本变更请参阅 [CHANGELOG.md（英文）](../../CHANGELOG.md)。

发现问题？请[提交 issue](https://github.com/NoOneExceptEnderk/RatioLab/issues)，
并附上你的系统信息、RatioLab 版本、复现步骤及相关项目文件。

## 许可证

版权所有 © 2026 **NoOneExceptEnderk**。采用[仅限 GNU GPL 第 3 版](../../LICENSE)
（`GPL-3.0-only`）许可。署名与声明请参阅 [COPYRIGHT](../../COPYRIGHT)。
第三方组件保留各自的许可证。
