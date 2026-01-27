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

1. 检测 `tools/FModelCLI.exe` 是否存在
2. 如果不存在，自动从 GitHub 克隆 FModelCLI 仓库
3. 自动编译并部署到 `tools/` 目录

如果你想手动管理，可以：
- 从 [Releases](https://github.com/Herselfta/FModelCLI/releases) 下载预编译版本
- 放置到 `tools/FModelCLI.exe`

### 技术细节
- 基于 [FModel](https://github.com/4sval/FModel) 和 [CUE4Parse](https://github.com/FabianFG/CUE4Parse)
- 自包含的 .NET 8.0 单文件可执行程序
- 支持多 AES 密钥、多语言资源提取

---

## vgmstream

### 许可证
ISC License（需保留版权声明）

### 用途
将 `.wem` 格式的 Wwise 音频转换为 `.wav`/`.ogg` 格式。

### 下载
- **官方 GitHub**: https://github.com/vgmstream/vgmstream
- **预编译版本**: https://vgmstream.org

### 安装说明
1. 下载 `vgmstream-cli`
2. 解压到 `tools/vgmstream/` 目录
3. 确保 `tools/vgmstream/vgmstream-cli.exe` 存在
4. **重要**: 保留 `tools/vgmstream/COPYING` 文件

---

## wwiser

### 许可证
MIT License

### 用途
解析 Wwise `.bnk` 文件，提取音频事件与 Hash 的映射关系。

### 下载
- **GitHub**: https://github.com/bnnm/wwiser

### 安装说明
已包含在项目中：`tools/wwiser.pyz`

---

## 许可证兼容性

| 工具 | 许可证 | 分发方式 | 备注 |
|------|--------|----------|------|
| **FModelCLI** | GPL-3.0 | 自动构建 | 从源码编译，不分发二进制 |
| **vgmstream** | ISC | 用户下载 | 必须保留 COPYING 文件 |
| **wwiser** | MIT | 包含在仓库 | 无额外要求 |

---

## 目录结构

```
tools/
├── FModelCLI.exe          # 自动生成（gitignored）
├── FModelCLI_src/         # 自动克隆（gitignored）
├── vgmstream/
│   ├── vgmstream-cli.exe  # 用户下载
│   └── COPYING            # 必须保留
├── wwiser.pyz             # 已包含
└── README.md              # 本文档
```
