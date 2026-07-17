# 架构说明

本文说明 `obara-3d-parser` 的主要模块、数据流和扩展点。

## 总体数据流

```text
STEP / 测试梁
  -> app.geometry.Part (支持多零件)
  -> Gmsh 显示表面网格
  -> Gmsh 四面体实体网格 (多零件合并)
  -> app.study.Study (包含零件列表)
  -> app.solver_backends.solve_study() (支持多材料)
  -> app.fea.FEAResult
  -> app.viewport / app.panels 显示结果
```

## 模块职责

### `app/main.py`

- 创建 Qt 应用。
- 设置应用名称和图标。
- 定位源码运行或 PyInstaller 打包后的资源路径。
- 延迟导入主窗口，避免 Qt 初始化前加载 VTK/Gmsh。

### `app/main_window.py`

- 主窗口和菜单/工具栏逻辑。
- 管理拾取模式：约束、载荷、面上色、零件上色、探针等。
- 协调各面板和视图的状态同步。
- 包含多零件处理和材料库动态加载功能。

### `app/viewport.py`

- 基于 PyVista 的 3D 渲染和交互。
- 实现面和零件拾取。
- 显示网格、位移图、应力图、载荷箭头。
- 支持面/零件颜色标记和探测模式。

### `app/panels.py`

- 材料库面板：按分类树展示材料，支持为不同零件分配材料。
- 分析设置面板：列出约束、载荷、坐标系和求解器设置。
- 结果面板：展示最大位移、最大 von Mises 应力、安全系数。
- 各面板信号与主窗口状态同步。

### `app/material_db.py`

- 定义 `Material` 数据类，包含弹性模量、泊松比、密度、屈服强度、抗拉强度、剪切模量、热膨胀系数、热导率、比热容等字段。
- 从 `material_data/sldmaterials.json` 读取材料。
- 提供 `load_material_database_from_dir()` 函数，支持从外部文件夹加载多个 JSON 文件并合并材料数据。
- 提供分类、名称查找和属性标准化。

### `app/geometry.py`

- STEP 文件导入（Gmsh/OpenCASCADE）。
- 测试梁生成。
- 网格化：生成表面三角网格和四面体实体网格。
- 支持多零件模型，网格化时自动合并网格并建立 `tet_to_part` 映射。

### `app/study.py`

- 保存一个分析工况的状态。
- 包含零件列表（支持多零件）、每个零件的材料、网格尺寸、约束、载荷、坐标系、求解器和结果。
- 提供运行前检查和缺失项报告，检查所有零件是否都分配了材料。
- 支持多零件模型的材料分配和状态管理。

### `app/fea.py`

- 内置线弹性静力求解器，支持多材料分析。
- 定义约束、压力载荷、力载荷、坐标系和结果结构。
- 组装 Tet4 单元刚度矩阵，通过 `tet_to_part` 映射支持多材料。
- 组装表面载荷，支持法向压力和指定方向力。
- 应用固定面约束并求解稀疏线性系统。
- 恢复 von Mises 应力和载荷面报告。
- 安全系数基于所有零件中最小的屈服强度计算。

### `app/solver_backends.py`

- 统一求解器入口。
- 当前包含两个后端：
  - `internal`：内置 Python 线性静力求解器。
  - `calculix`：导出 CalculiX/Abaqus 输入文件并调用外部 `ccx`。

## 关键数据结构

### `Part`

表示一个零件：

- `name`：名称
- `gmsh_model`：Gmsh 模型
- `mesh_quality`：网格质量信息
- `material`：分配的材料

### `TetMesh`

表示四面体网格和表面拾取数据：

- `points`：节点坐标
- `tets`：四面体单元连接关系
- `surf_tris`：表面三角片
- `tri_to_face`：三角片到面 ID 的映射
- `face_centers`：面中心
- `face_areas`：面面积
- `face_normals`：面法向
- `tet_to_part`：单元所属零件索引（多零件模型关键）
- `tri_to_part`：表面三角片所属零件索引（多零件模型关键）

**多零件网格**：对于包含多个零件的模型，网格化时会合并所有零件的网格。`tet_to_part` 和 `tri_to_part` 数组记录每个单元和三角片属于哪个零件，用于多材料分析和零件颜色渲染。

### `FixConstraint`

表示固定约束：

- `face_ids`：约束面 ID 列表

### `PressureLoad`

表示压力载荷：

- `face_ids`：载荷面 ID 列表
- `pressure`：压力值
- `direction_mode`：方向模式（法向或指定方向）
- `direction_vector`：指定方向向量

### `FEAResult`

表示分析结果：

- `displacement`：节点位移向量
- `stress`：单元应力
- `von_mises`：von Mises 应力
- `safety_factor`：安全系数
- `report`：载荷面位移报告

## 扩展点

### 添加新的求解器后端

在 `app/solver_backends.py` 中：

1. 实现新的求解函数，签名与 `solve_internal()` 一致。
2. 在 `available_backends()` 中注册新后端。
3. 在 `solve_study()` 中添加分支调用。

### 添加新的载荷类型

1. 在 `app/fea.py` 中定义载荷数据类。
2. 在载荷组装逻辑中处理新类型。
3. 在 `app/panels.py` 和 `app/main_window.py` 中添加 UI 支持。

### 添加新的材料属性

1. 在 `app/material_db.py` 的 `Material` 类中添加字段。
2. 在解析逻辑中读取新属性。
3. 在材料库面板中展示新属性。

## 资源路径

程序通过 `app/main.py` 中的 `get_resource_path()` 定位资源：

- 源码运行时：使用相对路径。
- PyInstaller 打包后：使用 `sys._MEIPASS`。

资源包括：

- `assets/app_icon.ico`
- `material_data/sldmaterials.json`