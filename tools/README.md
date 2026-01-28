# 第三方工具说明 (Third-Party Tools)

`tools/` 目录存放 Ludiglot 依赖的第三方工具。

---

## FModelCLI (自动管理)

### 用途
从虚幻引擎游戏的 PAK 文件中提取 ConfigDB、TextMap 和音频资源。

### 许可证
GPL-3.0 - https://github.com/Herselfta/FModelCLI

### 安装说明
**无需手动安装**。Ludiglot 会自动完成以下操作：

1. 检测 `tools/FModelCLI.exe` 是否存在。
2. 如果不存在，检查本地开发环境（如 `E:/FModelCLI`）。
3. 如果本地没有，自动从 [GitHub Releases](https://github.com/Herselfta/FModelCLI/releases) 下载最新的预编译版本。

### 技术细节
- 基于 [FModel](https://github.com/4sval/FModel) 和 [CUE4Parse](https://github.com/FabianFG/CUE4Parse)
- 自包含的 .NET 8.0 单文件可执行程序
- **自动初始化**: 首次运行时会自动下载 `vgmstream`、`Oodle` 等必要组件到 `tools/.data/` 目录。

---

## vgmstream (由 FModelCLI 管理)

### 许可证
ISC License

### 说明
原本需要手动下载，现在由 `FModelCLI` 自动管理并下载到 `tools/.data/`。Ludiglot 会自动在 `.data` 目录中寻找 `vgmstream-cli.exe`。

---

## wwiser

### 许可证
MIT License

### 用途
解析 Wwise `.bnk` 文件，提取音频事件与 Hash 的映射关系。

### 下载
- **GitHub**: https://github.com/bnnm/wwiser

### 安装说明
已包含在项目根目录的 `tools/` 文件夹下：`tools/wwiser.pyz`

---

## 许可证兼容性

| 工具 | 许可证 | 管理方式 | 备注 |
|------|--------|----------|------|
| **FModelCLI** | GPL-3.0 | 自动下载 | 遵循 GPL-3.0，二进制独立运行 |
| **vgmstream** | ISC | 自动安装 | 由 FModelCLI 自动下载 |
| **wwiser** | MIT | 包含在仓库 | 无额外要求 |

---

## 目录结构

```
tools/
├── .data/                 # 自动生成：核心依赖 (vgmstream, oodle 等)
├── FModelCLI.exe          # 自动生成：核心解包程序
├── wwiser.pyz             # 已包含：Wwise 解析脚本
└── README.md              # 本文档
```
