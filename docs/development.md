# 开发指南

本文说明项目开发、测试和贡献时的常用流程。

## 开发环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

运行应用：

```powershell
python run.py
```

运行测试：

```powershell
pytest
```

## 代码组织

```text
app/main.py             应用入口
app/main_window.py      主窗口和工作流编排，包含多零件处理和材料库动态加载
app/panels.py           Qt 停靠面板，支持多零件材料分配
app/viewport.py         3D 视图和拾取，支持面/零件颜色标记和探测模式
app/geometry.py         STEP 导入、测试梁、网格，支持多零件模型
app/fea.py              内置 FEA 求解器，支持多材料分析
app/solver_backends.py  求解器后端适配
app/material_db.py      材料库，支持从文件夹加载多个 JSON 文件
app/study.py            工况状态，包含零件列表
tests/                  无界面测试
```

## 版本管理

版本号格式：`v<year>-<month>-<day>-<alpha/beta/release>`

版本号自动生成，基于当前日期和构建类型。

## 测试

项目使用 `pytest` 进行无界面测试：

```powershell
pytest
```

测试覆盖：

- 材料库解析
- 网格化
- FEA 求解器
- 坐标系变换
- 集成测试

## 修改网格或几何逻辑的注意事项

- 保持 `TetMesh` 字段含义稳定。
- 面 ID 是约束、载荷、结果报告和拾取逻辑的关键连接点。
- 多零件模型需要维护 `tet_to_part` 和 `tri_to_part`，确保每个单元和三角片正确映射到所属零件。
- `mesh_part()` 函数负责合并多零件网格并建立 `tet_to_part` 映射。
- 网格尺寸过小可能导致测试和构建环境耗时显著增加。

## 修改求解器的注意事项

- 约束不足会造成刚体运动或矩阵奇异。
- 应力恢复和安全系数需要明确单元/节点映射。
- 新增载荷类型时必须检查单位和方向。
- 多材料分析需要通过 `tet_to_part` 数组正确映射每个单元到对应的材料。
- 安全系数计算基于所有零件中最小的屈服强度。
- 修改后至少运行 `tests/test_fea.py` 和 `tests/test_integration.py`。

## 修改材料库的注意事项

- 新增材料属性字段时需要同步更新 `Material` 数据类。
- 外部材料库加载时需要处理字段缺失情况。
- 切换材料库后需要检查当前使用的材料是否仍存在。

## 添加新的求解器后端

1. 在 `app/solver_backends.py` 中实现新的求解函数。
2. 在 `available_backends()` 中注册新后端。
3. 在 `solve_study()` 中添加分支调用。
4. 更新文档 `docs/solver_backends.md`。

## 添加新的 UI 功能

1. 在 `app/main_window.py` 中添加菜单/工具栏按钮。
2. 在 `app/panels.py` 中添加面板或控件。
3. 在 `app/viewport.py` 中添加渲染或交互逻辑。
4. 在 `app/study.py` 中添加状态管理。

## 代码风格

- 使用 Python 3.13+。
- 使用 `mypy` 进行类型检查。
- 使用 `black` 进行代码格式化。
- 使用 `flake8` 进行代码检查。

## 贡献流程

1. Fork 项目。
2. 创建功能分支。
3. 编写代码和测试。
4. 提交 PR。
5. 等待审核和合并。

## 常见问题

### 为什么测试失败？

- 检查网格尺寸是否过大，导致测试耗时超过超时时间。
- 检查材料库文件是否存在且格式正确。
- 检查依赖版本是否兼容。

### 如何调试 UI 问题？

- 使用 Qt 的调试工具。
- 添加日志输出。
- 使用 `print()` 或调试器检查状态。

### 如何添加新的材料属性？

1. 在 `app/material_db.py` 的 `Material` 类中添加字段。
2. 在解析逻辑中读取新属性。
3. 在材料库面板中展示新属性。
4. 更新文档 `docs/materials.md`。