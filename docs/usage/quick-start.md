# 🚀 快速开始 (Quick Start)

本文档旨在帮助新用户在 Windows 环境下从零开始搭建并运行 Ludiglot。

## ✅ 1. 环境准备

在开始之前，请确保您的电脑已安装以下软件：

1.  **Git**：用于克隆项目和数据。([下载 Git](https://git-scm.com/downloads))
2.  **Python 3.10+**：项目运行环境。([下载 Python](https://www.python.org/downloads/))
    *   *安装时请勾选 "Add Python to PATH"*

## 📥 2. 获取项目

打开 PowerShell 或终端，执行以下命令：

```powershell
# 1. 克隆项目代码
git clone https://github.com/yourusername/Ludiglot.git
cd Ludiglot

# 2. 准备数据目录 (推荐直接克隆 WutheringData)
# 注意：此仓库约 200MB，包含游戏文本和映射数据
git clone https://github.com/Dimbreath/WutheringData.git data/WutheringData
```

## 🛠️ 3. 一键初始化 (核心步骤)

我们提供了一个自动化脚本来完成虚拟环境创建、依赖安装和配置文件生成。

**请务必运行此步骤：**

```powershell
# 在 Ludiglot 根目录下运行
.\setup.ps1
```

> **脚本通过做什么？**
> *   构建 Python 虚拟环境 (`.venv`)
> *   安装所有必要的依赖库 (OCR, GUI 等)
> *   自动生成 `config/settings.json` 配置文件

## ⚙️ 4. 检查配置

初始化完成后，脚本会自动创建 `config/settings.json`。
通常情况下你**不需要修改**它，除非你的数据放在了非默认位置。

默认配置如下：
```json
{
  "data_root": "data/WutheringData",
  "ocr_mode": "auto",
  "play_audio": true
}
```

## ▶️ 5. 启动程序

一切就绪！使用以下命令启动：

```powershell
.\run.ps1
```

或者直接双击根目录下的 `run.bat` 文件。

---

## ❓ 常见问题

**Q: 运行 setup.ps1 提示 "在此系统上禁止运行脚本"？**
A: 这是 PowerShell 的安全策略。请以管理员身份运行 PowerShell，并执行：
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
然后重试。

**Q: 启动后提示找不到 OCR 语言包？**
A: Windows 原生 OCR 需要系统安装对应的语言包。
*   进入 **设置 > 时间和语言 > 语言和区域**。
*   确保已安装 **英语(美国)** 和 **中文(简体)**。

**Q: 如何更新数据？**
A: 进入 `data/WutheringData` 目录并运行 `git pull`，或者在程序托盘图标右键菜单中点击 "Update Database"。
