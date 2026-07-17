# 构建与发布指南

本文说明如何将项目打包为 Windows 可执行程序，以及 GitHub Actions 发布流程。

## 本地构建

项目提供 PowerShell 构建脚本：

```powershell
.\build.ps1
```

脚本会执行：

1. 检查 Python 3.13+。
2. 创建或复用 `.venv`。
3. 安装 `.[build,dev]` 依赖。
4. 清理旧的 `dist/` 和 `build/`。
5. 使用 `obara-3d-parser.spec` 调用 PyInstaller。
6. 验证 `obara-3d-parser.exe` 是否生成。
7. 尝试启动程序并随后关闭。
8. 清理中间构建目录。

## 构建产物

默认输出目录：

```text
dist/obara-3d-parser/
```

包含：

- `obara-3d-parser.exe`：主程序
- `material_data/sldmaterials.json`：材料库
- `assets/app_icon.ico`：应用图标
- 依赖库和资源文件

## 构建配置

PyInstaller 配置文件：`obara-3d-parser.spec`

关键配置：

- 单文件模式：`--onefile`
- 窗口模式：`--windowed`
- 应用图标：`assets/app_icon.ico`
- 资源文件：`material_data/` 和 `assets/`
- 运行时钩子：`hooks/`

## 环境要求

- Python 3.13+
- PowerShell 5+ 或 PowerShell 7+
- Git
- 最新显卡驱动（用于构建后测试）

## 手动构建

如果需要自定义构建参数，可以手动运行：

```powershell
python -m PyInstaller obara-3d-parser.spec
```

## GitHub Actions 发布

项目使用 GitHub Actions 自动构建和发布：

### 触发条件

- 推送标签到 `main` 分支
- 手动触发工作流

### 工作流步骤

1. 检出代码。
2. 设置 Python 环境。
3. 安装依赖。
4. 运行测试。
5. 构建可执行程序。
6. 创建 GitHub Release。
7. 上传构建产物。

### 发布版本

版本号格式：`v<year>-<month>-<day>-<alpha/beta/release>`

例如：`v26-07-15-alpha`

### 发布步骤

1. 创建标签：

```powershell
git tag v26-07-15-alpha
git push origin v26-07-15-alpha
```

2. GitHub Actions 会自动触发构建。
3. 构建完成后，在 GitHub Releases 页面查看发布。

## 构建注意事项

### 中间目录清理

根据项目约定，构建脚本会自动清理中间构建目录（`build/`），只保留最终产物（`dist/`）。

### 依赖版本

确保使用正确版本的依赖：

```powershell
pip install -e ".[build,dev]"
```

### 测试失败

如果构建脚本中的测试失败，构建会停止。需要先修复测试问题。

### 杀毒软件警告

某些杀毒软件可能会误报 PyInstaller 打包的程序。可以将 `dist/obara-3d-parser/` 添加到信任列表。

## 常见问题

### 构建失败

- 检查 Python 版本是否为 3.13+。
- 检查依赖是否安装正确。
- 检查 `obara-3d-parser.spec` 是否存在且格式正确。
- 查看构建日志中的错误信息。

### 程序无法启动

- 检查 `dist/obara-3d-parser/` 目录是否完整。
- 检查 `material_data/sldmaterials.json` 是否存在。
- 检查显卡驱动是否最新。
- 尝试从命令行启动，查看错误输出。

### 资源文件缺失

- 检查 `obara-3d-parser.spec` 中的资源文件配置。
- 确保 `material_data/` 和 `assets/` 目录存在。
- 运行构建脚本前不要删除资源文件。