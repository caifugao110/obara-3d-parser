# obara-3d-parser

一款轻量级、开源的3D有限元分析（FEA）仿真软件，灵感来源于SolidWorks Simulation。

**作者**: Tobin  
**协议**: MIT  
**版本**: v26-07-12-α

![obara-3d-parser](assets/app_icon.ico)

## 功能特性

- **STEP 文件导入**: 支持导入 STEP 格式的3D CAD数模
- **自动网格划分**: 使用 Gmsh 生成四面体网格
- **材质数据库**: 包含100+种材质，包括铝、钢、铜、橡胶、尼龙等
- **线性静态分析**: 求解位移和应力
- **可视化**: 3D渲染位移和应力ISO等高线图
- **安全系数**: 基于屈服强度的安全系数计算
- **用户坐标系**: 在用户定义的坐标系下输出位移结果

## 安装

### Windows

从 [releases](https://github.com/caifugao110/obara-3d-parser/releases) 下载最新版本。

### 从源代码安装

```bash
# 克隆仓库
git clone https://github.com/caifugao110/obara-3d-parser.git
cd obara-3d-parser

# 安装依赖
pip install -r requirements.txt

# 运行应用
python run.py
```

## 使用方法

1. **导入数模**: 点击"文件 > 导入 STEP"加载CAD模型，或使用"生成测试梁"快速演示
2. **设置材质**: 从材质数据库面板选择材质
3. **定义固定约束**: 点击面定义固定（零位移）约束
4. **施加载荷**: 点击面施加压力载荷
5. **定义坐标系**: 设置分析坐标系
6. **运行分析**: 点击"运行仿真"执行FEA求解器
7. **查看结果**: 查看位移值和应力等高线

## 技术细节

### 依赖

- Python 3.13+
- PySide6 (Qt6 GUI框架)
- Gmsh 4.15 (STEP解析和网格生成)
- PyVista + VTK (3D可视化)
- SciPy (稀疏矩阵求解器)
- NumPy (数值计算)

### 求解器

内置FEA求解器实现：

- 线性四面体单元 (Tet4)
- 基于Lame参数的线弹性理论
- 稀疏直接求解器
- von Mises应力恢复
- 安全系数 = 屈服强度 / 最大von Mises应力

### 单位系统

- 内部：SI单位（米、帕斯卡、牛顿）
- 输入/输出：毫米、MPa（标准工程单位）

## 从源代码构建

### Windows

```powershell
# 运行构建脚本
.\build.ps1
```

或直接使用 PyInstaller：

```powershell
pyinstaller --noconfirm --distpath dist --workpath build obara-3d-parser.spec
```

### GitHub Actions

项目包含GitHub Actions工作流，在每次标签推送时自动构建并发布Windows可执行文件。

## 项目结构

```
obara-3d-parser/
├── app/                    # 主应用代码
│   ├── __init__.py         # 包初始化（含版本信息）
│   ├── fea.py              # FEA求解器（线弹性）
│   ├── geometry.py         # STEP导入和网格处理
│   ├── material_db.py      # 材质数据库加载器
│   ├── main.py             # 应用入口
│   ├── main_window.py      # 主窗口UI
│   ├── panels.py           # 停靠面板（材质、分析、结果）
│   ├── study.py            # 分析数据模型
│   └── viewport.py         # 3D视图（PyVista）
├── assets/                 # 应用资源
│   └── app_icon.ico        # 应用图标
├── material_data/          # 材质数据库
│   └── sldmaterials.json   # SolidWorks兼容材质（100+种）
├── hooks/                  # PyInstaller运行时钩子
│   ├── runtime_hook_gmsh.py
│   └── runtime_hook_scipy.py
├── tests/                  # 测试脚本
│   ├── test_fea.py
│   └── test_integration.py
├── .github/workflows/
│   └── build.yml           # GitHub Actions工作流
├── .gitignore
├── build.ps1               # PowerShell构建脚本
├── obara-3d-parser.spec  # PyInstaller配置文件
├── requirements.txt        # Python依赖
├── pyproject.toml          # 项目配置
├── LICENSE                 # MIT协议
└── README.md               # 本文档
```

## 协议

本项目采用 MIT 协议 - 详见 [LICENSE](LICENSE)。

## 贡献

欢迎贡献！请随时提交issues和pull requests。

## 致谢

- [Gmsh](https://gmsh.info/) - 3D有限元网格生成器
- [PyVista](https://docs.pyvista.org/) - 3D绘图和网格分析
- [SciPy](https://scipy.org/) - 科学计算
- [PySide6](https://doc.qt.io/qtforpython/) - Qt6 Python绑定