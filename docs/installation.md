# 安装指南

本文说明如何在 Windows 上安装并运行 `obara-3d-parser`。

## 推荐环境

- Windows 10/11 x64
- Python 3.13+
- PowerShell 5+ 或 PowerShell 7+
- 最新显卡驱动，支持 OpenGL
- Git（用于克隆源码）

## 获取源码

```powershell
git clone https://github.com/caifugao110/obara-3d-parser.git
cd obara-3d-parser
```

## 创建虚拟环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

如果 PowerShell 阻止激活脚本，可在当前会话临时放宽策略：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 安装依赖

```powershell
pip install -e ".[dev]"
```

安装的主要依赖：

- PyQt6：UI 框架
- PyVista：3D 可视化
- Gmsh：网格生成
- SciPy：科学计算和稀疏矩阵求解
- pytest：测试框架
- PyInstaller：打包工具

## 启动程序

```powershell
python run.py
```

启动后会自动定位：

- `assets/app_icon.ico`
- `material_data/sldmaterials.json`

源码运行和 PyInstaller 打包运行都使用同一套资源查找逻辑。

## 功能特性

### 多零件模型支持

程序支持导入包含多个实体的 STEP 文件，每个实体会作为独立零件处理：

- 每个零件可独立分配不同材料
- 网格化时会自动合并所有零件的网格
- 支持多材料有限元分析

### 外部材料库

除了内置材料库，程序还支持从外部文件夹加载自定义材料库：

1. 在主菜单中选择"文件 > 选择材质库文件夹..."
2. 选择包含一个或多个 `*.json` 文件的文件夹
3. 程序会自动扫描并合并所有材料数据

外部材料库的 JSON 格式需与内置的 `sldmaterials.json` 兼容，详细格式参见 [materials.md](materials.md)。

## 可选：安装 CalculiX

如果需要使用 CalculiX 求解器后端，需要额外安装：

### 下载 CalculiX

从 [CalculiX 官网](http://www.calculix.de/) 下载 Windows 版本。

### 配置环境变量

设置 `OBARA_CALCULIX_CCX` 或 `CCX_PATH` 环境变量：

```powershell
$env:OBARA_CALCULIX_CCX = "C:\CalculiX\bin\ccx.exe"
```

或在系统环境变量中永久设置。

### 验证安装

```powershell
ccx -v
```

如果显示版本信息，说明安装成功。

## 卸载

1. 删除项目目录。
2. 删除虚拟环境目录（`.venv`）。

## 常见问题

### 安装失败

- 检查 Python 版本是否为 3.13+。
- 检查网络连接是否正常。
- 尝试使用国内 PyPI 镜像：

```powershell
pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 程序无法启动

- 检查显卡驱动是否最新。
- 检查虚拟环境是否激活。
- 尝试重新安装依赖：

```powershell
pip install -e ".[dev]" --upgrade
```

### Gmsh 错误

- 确保安装了正确版本的 Gmsh。
- 检查系统是否缺少 VC++ 运行时库。

### PyVista 错误

- 检查 OpenGL 版本是否支持。
- 更新显卡驱动。
- 尝试设置 `PYVISTA_OFF_SCREEN=true`：

```powershell
$env:PYVISTA_OFF_SCREEN = "true"
python run.py
```