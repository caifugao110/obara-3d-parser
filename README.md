<p align="center">
  <h1 align="center">obara-3d-parser</h1>
  <p align="center">
    <img src="https://img.shields.io/badge/python-%3E%3D3.13-green" alt="python">
    <img src="https://img.shields.io/badge/license-MIT-yellow" alt="license">
    <img src="https://img.shields.io/badge/platform-Windows-lightgrey" alt="platform">
  </p>
  <p align="center">
    <i>A lightweight, open-source 3D Finite Element Analysis (FEA) simulation software, inspired by SolidWorks Simulation.</i>
  </p>
</p>

---

## 📖 简介

**obara-3d-parser** 是一款专为工程师和开发者打造的轻量级、开源3D有限元分析（FEA）仿真软件。灵感来源于SolidWorks Simulation，致力于提供简洁易用的界面和强大的分析能力，让有限元仿真不再是复杂的专业技能。

🌟 **项目亮点**
- 🎯 **零门槛上手**: 直观的图形界面，无需专业CAE知识即可完成仿真分析
- 📦 **轻量高效**: 纯Python实现，资源占用低，运行速度快
- 🔓 **完全开源**: MIT协议，代码透明，支持二次开发和定制
- 🎨 **精美可视化**: 基于PyVista的高质量3D渲染，直观展示分析结果

| 项目信息 |                                                              |
| -------- | ------------------------------------------------------------ |
| 作者     | **Tobin**                                                    |
| 项目地址 | [github.com/caifugao110/obara-3d-parser](https://github.com/caifugao110/obara-3d-parser) |
| 开源协议 | MIT                                                          |
| 版本     | vYY-MM-DD-α（自动使用当前日期）                               |

---

## ✨ 功能特性

### 📂 文件导入
- **STEP 文件导入**: 支持导入 STEP 格式的3D CAD数模，兼容主流CAD软件

### 🔲 网格划分
- **自动网格划分**: 使用 Gmsh 生成高质量四面体网格，一键完成网格生成

### 🧪 材质与分析
- **材质数据库**: 内置100+种材质，涵盖铝、钢、铜、橡胶、尼龙等常用工程材料
- **线性静态分析**: 精确求解位移场和应力分布
- **安全系数**: 基于屈服强度的安全系数自动计算，直观评估结构安全性

### 📊 可视化与输出
- **3D可视化**: 渲染位移和应力ISO等高线图，支持交互式旋转、缩放
- **用户坐标系**: 在自定义坐标系下输出位移结果，满足特定分析需求

---

## 🚀 快速开始

### 📋 环境要求

- Python >= 3.13
- Windows 操作系统

### 📝 直接运行源码

```bash
# 克隆仓库
git clone https://github.com/caifugao110/obara-3d-parser.git
cd obara-3d-parser

# 安装依赖
pip install -r requirements.txt

# 运行应用
python run.py
```

### 💻 Windows

从 [releases](https://github.com/caifugao110/obara-3d-parser/releases) 下载最新版本，无需配置，直接运行！

---

## 📖 使用方法

1. **📥 导入数模**: 点击"文件 > 导入 STEP"加载CAD模型，或使用"生成测试梁"快速体验
2. **🔬 设置材质**: 从材质数据库面板选择合适的工程材料
3. **🔒 定义固定约束**: 点击面定义固定（零位移）约束条件
4. **⚡ 施加载荷**: 点击面施加压力载荷
5. **📐 定义坐标系**: 设置分析坐标系，自定义输出方向
6. **▶️ 运行分析**: 点击"运行仿真"执行FEA求解器
7. **👀 查看结果**: 查看位移值和应力等高线，评估结构性能

---

## 🔧 技术细节

### 📦 依赖

- Python 3.13+
- PySide6 (Qt6 GUI框架)
- Gmsh 4.15 (STEP解析和网格生成)
- PyVista + VTK (3D可视化)
- SciPy (稀疏矩阵求解器)
- NumPy (数值计算)

### 🧮 求解器

内置FEA求解器实现：

- 线性四面体单元 (Tet4)
- 基于Lame参数的线弹性理论
- 稀疏直接求解器
- von Mises应力恢复
- 安全系数 = 屈服强度 / 最大von Mises应力

### 📏 单位系统

- 内部：SI单位（米、帕斯卡、牛顿）
- 输入/输出：毫米、MPa（标准工程单位）

---

## 📦 构建

### 💻 Windows

```powershell
# 运行构建脚本
.\build.ps1
```

或直接使用 PyInstaller：

```powershell
pyinstaller --noconfirm --distpath dist --workpath build obara-3d-parser.spec
```

### 🤖 GitHub Actions

项目包含GitHub Actions工作流，在每次标签推送时自动构建并发布Windows可执行文件。

---

## 🤝 贡献

欢迎贡献！无论是功能建议、Bug报告还是代码提交，都非常感谢您的参与！

- 📝 提交 issues 反馈问题或提出改进建议
- 🔧 提交 pull requests 贡献代码
- 📖 完善文档，帮助更多用户

---

## 🙏 致谢

- [Gmsh](https://gmsh.info/) - 3D有限元网格生成器
- [PyVista](https://docs.pyvista.org/) - 3D绘图和网格分析
- [SciPy](https://scipy.org/) - 科学计算
- [PySide6](https://doc.qt.io/qtforpython/) - Qt6 Python绑定

---

## 📄 License

MIT © Tobin