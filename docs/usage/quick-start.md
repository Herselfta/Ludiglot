# 🚀 快速开始 (Quick Start)

本文档旨在帮助新用户在 Windows 环境下从零开始搭建并运行 Ludiglot。

## ✅ 1. 环境准备

在开始之前，请确保您的电脑已安装以下软件：

1.  **Git**：用于克隆项目。([下载 Git](https://git-scm.com/downloads))
2.  **Python 3.10+**：项目运行环境。([下载 Python](https://www.python.org/downloads/))
    *   *安装时请勾选 "Add Python to PATH"*

> **注意**：Pak 解包器采用自包含发布，用户无需安装 .NET SDK。

## 📥 2. 获取项目

打开 PowerShell 或终端，执行以下命令：

```powershell
# 克隆项目代码
git clone https://github.com/yourusername/Ludiglot.git
cd Ludiglot
```

## 🛠️ 3. 一键初始化 (核心步骤)

我们提供了一个自动化脚本来完成虚拟环境创建、依赖安装和配置文件生成。

**请务必运行此步骤：**

```powershell
# 在 Ludiglot 根目录下运行
.\setup.ps1
```

> **脚本做了什么？**
> *   构建 Python 虚拟环境 (`.venv`)
> *   安装所有必要的依赖库 (OCR, GUI 等)
> *   自动生成 `config/settings.json` 配置文件

## ⚙️ 4. 配置游戏路径

初始化完成后，编辑 `config/settings.json`，设置游戏安装目录：

```json
{
  "use_game_paks": true,
  "game_install_root": "D:/Games/Wuthering Waves Game",
  "game_platform": "Windows",
  "game_server": "OS",
  "game_languages": ["en", "zh-Hans"],
  "game_audio_languages": ["zh"],
  "extract_audio": true
}
```

> **提示**：`game_install_root` 应指向包含 `Client` 文件夹的游戏根目录。

## ▶️ 5. 启动程序

使用以下命令启动：

```powershell
.\run.ps1
```

或者直接双击根目录下的 `run.bat` 文件。

## 📦 6. 解包游戏数据

首次启动后，点击覆盖层右上角菜单按钮 **≡** → **Update Database**。

程序将自动：
1. 从 GitHub 获取最新 AES 密钥
2. 从游戏 Pak 解包文本数据（ConfigDB, TextMap）
3. 解包语音资源（如启用）
4. 提取游戏字体到 `data/Fonts/`
5. 构建本地搜索数据库

> 也可通过命令行执行：`python -m ludiglot pak-update`

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

**Q: 解包时提示 AES 密钥获取失败？**
A: 可能是网络问题。程序会自动使用本地缓存，如果是首次运行，请检查网络连接。

**Q: 如何更新数据？**
A: 在覆盖层菜单点击 "Update Database"，或运行 `python -m ludiglot pak-update`。
