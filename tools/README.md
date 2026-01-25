# 第三方工具说明 (Third-Party Tools)

本项目在 `tools/` 目录下使用了一些第三方工具，这些工具**不包含在 Git 仓库**中，需要用户自行下载。

---

## FModel

### 许可证
[GPL-3.0 License](https://github.com/4sval/FModel/blob/master/LICENSE)

### 用途
用于从虚幻引擎游戏中提取资源（.wem 音频文件、.bnk 事件文件等）。

### 下载
- **官方网站**: https://fmodel.app/
- **GitHub**: https://github.com/4sval/FModel

### 安装说明
1. 从官方网站下载最新版本的 FModel
2. 将 `FModel.exe` 放置到 `tools/` 目录下
3. 或者直接在系统其他位置安装，按需调用

### 使用步骤
详见 [DataManagement.md](../docs/DataManagement.md) 中的"音频资源"章节。

---

## vgmstream

### 许可证
**ISC License** (与MIT兼容，需保留版权声明)

完整许可证文本见: `tools/vgmstream/COPYING`

**版权所有者**:
```
Copyright (c) 2008-2025 Adam Gashlin, Fastelbja, Ronny Elfert, bnnm,
                        Christopher Snowhill, NicknineTheEagle, bxaimc,
                        Thealexbarney, CyberBotX, et al
```

**许可证要求**:
- ✅ 允许商业使用
- ✅ 允许修改和分发
- ⚠️ **必须保留版权声明和许可证文本**
- ✅ 无专利授权要求
- ✅ 不要求开源衍生作品

### 用途
将 `.wem` 格式的 Wwise 音频文件转换为 `.wav` / `.ogg` 格式。

### 下载
- **官方 GitHub**: https://github.com/vgmstream/vgmstream
- **自动构建**: https://vgmstream.org

### 安装说明
1. 下载预编译的 `vgmstream-cli`
2. 解压到 `tools/vgmstream/` 目录
3. 确保 `tools/vgmstream/vgmstream-cli.exe` 存在
4. **重要**: 保留 `tools/vgmstream/COPYING` 文件（许可证要求）

---

## wwiser

### 许可证
MIT License (兼容)

### 用途
解析 Wwise `.bnk` 文件，提取音频事件与 Hash 的映射关系。

### 下载
- **GitHub**: https://github.com/bnnm/wwiser

### 安装说明
已包含在项目中：`tools/wwiser.pyz`（Python 脚本打包版本）

---

## 法律合规说明

### 为什么 FModel.exe 不在仓库中？

**FModel 使用 GPL-3.0 许可证**，这是一个强 Copyleft 许可证。如果本项目直接包含 FModel.exe 二进制文件，根据 GPL-3.0 的传染性条款，**整个 Ludiglot 项目也必须采用 GPL-3.0**，这与我们的 MIT 许可证不兼容。

### 解决方案

1. **不分发 FModel 二进制文件**：将 `tools/FModel.exe` 加入 `.gitignore`
2. **提供下载链接**：用户从官方渠道自行下载
3. **弱耦合设计**：FModel 仅作为可选的资源提取工具，不是核心依赖

### 许可证兼容性

| 工具 | 许可证 | MIT 兼容性 | 分发方式 | 特殊要求 |
|------|--------|-----------|---------|---------|
| **FModel** | GPL-3.0 | ❌ 不兼容 | 用户自行下载 | 无 |
| **vgmstream** | ISC | ✅ 兼容 | 包含在仓库* | 必须保留COPYING文件 |
| **wwiser** | MIT | ✅ 兼容 | 包含在仓库 | 无 |

**注**: vgmstream 可以包含在仓库中，但必须保留其 `COPYING` 文件以满足ISC许可证要求。当前建议用户自行下载以减小仓库体积。

---

## 对用户的影响

### 首次设置需要额外步骤

用户需要手动下载 FModel 和 vgmstream，但这只需要做一次：

```bash
# 1. 克隆仓库
git clone https://github.com/yourusername/Ludiglot.git
cd Ludiglot

# 2. 下载第三方工具
# - 从 https://fmodel.app/ 下载 FModel.exe，放到 tools/
# - 从 https://github.com/vgmstream/vgmstream 下载 vgmstream-cli，解压到 tools/vgmstream/

# 3. 其余步骤与之前相同
.\setup.ps1
.\run.ps1
```

### 自动化脚本优化（TODO）

可以在 `setup.ps1` 中添加检测和提示逻辑：

```powershell
if (-not (Test-Path "tools/FModel.exe")) {
    Write-Warning "FModel.exe 未找到。请从 https://fmodel.app/ 下载并放置到 tools/ 目录。"
}

if (-not (Test-Path "tools/vgmstream/vgmstream-cli.exe")) {
    Write-Warning "vgmstream 未找到。请从 https://github.com/vgmstream/vgmstream 下载并解压到 tools/vgmstream/。"
}
```

---

## 参考文献

- [GPL-3.0 License](https://www.gnu.org/licenses/gpl-3.0.html)
- [MIT License Compatibility](https://choosealicense.com/licenses/mit/)
- [FModel GitHub Repository](https://github.com/4sval/FModel)
