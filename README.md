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
- **多零件模型**: 支持 STEP 文件中包含多个实体（零件），每个零件可独立分配材料
- **测试梁生成**: 通过"文件 > 生成测试梁"创建内置测试梁，无需导入外部模型即可快速体验分析流程

### 🔲 网格划分
- **自动网格划分**: 使用 Gmsh 生成高质量四面体网格，一键完成网格生成
- **网格密度控制**: 通过滑块调节网格粗细，平衡精度与计算效率
- **多零件网格合并**: 自动合并多零件模型的网格，保持零件间的连接关系

### 🧪 材质与分析
- **材质数据库**: 内置100+种材质，涵盖铝、钢、铜、橡胶、尼龙等常用工程材料
- **材料库文件夹选择**: 支持从外部文件夹加载自定义材质库（多个JSON文件）
- **多材料分析**: 每个零件可分配不同材料，支持多材料混合分析
- **线性静态分析**: 精确求解位移场和应力分布
- **安全系数**: 基于屈服强度的安全系数自动计算，直观评估结构安全性

### 📊 可视化与输出
- **3D可视化**: 渲染位移和应力ISO等高线图，支持交互式旋转、缩放
- **用户坐标系**: 在自定义坐标系下输出位移结果，满足特定分析需求
- **面/零件颜色标记**: 支持为特定面或零件添加自定义颜色标记
- **探测模式**: 点击模型查看任意点的位移和应力数值
- **载荷箭头显示**: 可视化显示载荷方向和大小

### 🚀 求解器后端
- **内置求解器**: Python/SciPy 实现的 Tet4 线弹性求解器，无需外部依赖
- **CalculiX 支持**: 支持导出 CalculiX/Abaqus 格式输入文件并调用外部求解器

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

1. **📥 导入数模**: 点击"文件 > 导入 STEP 数模..."加载CAD模型，或使用"文件 > 生成测试梁"快速体验。支持多零件模型，每个零件会自动编号。
2. **🔬 设置材质**: 
   - 在材料库面板选择目标零件（多零件模型时）
   - 从材质分类树中选择合适的工程材料
   - 点击"应用材质到零件"完成分配
   - 支持通过"选择材质库文件夹"加载外部自定义材质库
3. **🔧 调整网格**: 在分析设置面板中通过滑块调节网格密度，点击"网格划分"生成四面体网格
4. **🔒 定义固定约束**: 点击"拾取固定面"，在3D视图中点击需要固定的面（可多选）
5. **⚡ 施加载荷**: 
   - 点击"拾取加压面"，在3D视图中点击受载面
   - 在弹窗中选择载荷类型（法向压力或指定方向力）并输入载荷大小
6. **📐 定义坐标系**: 通过"解析坐标系"菜单设置自定义分析坐标系，用于输出位移分量
7. **⚙️ 选择求解器**: 在分析设置面板中选择内置求解器或CalculiX外部求解器
8. **▶️ 运行分析**: 点击"运行仿真"执行FEA求解器，求解过程在后台线程运行，不阻塞界面
9. **👀 查看结果**: 
   - 自动显示位移ISO图，可切换到应力ISO图
   - 使用"探测模式"点击模型查看任意点的详细位移和应力数值
   - 结果面板显示最大位移、最大应力、安全系数和载荷面位移报告
10. **🎨 自定义显示**: 
    - 使用面颜色和零件颜色功能标记特定区域
    - 支持原始视图、网格视图、位移图、应力图等多种显示模式

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
