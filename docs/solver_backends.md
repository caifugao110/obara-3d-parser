# 求解器后端

## 与 SolidWorks 的区别/联系

SolidWorks Simulation 使用的是其内置的商业求解器，而 obara-3d-parser 使用的是开源求解器。两者都可以通过 SolidWorks 的 COM/API 进行交互，但 obara-3d-parser 不依赖 SolidWorks COM，可以独立运行。

## 后端类型

- `internal`: 内置的 Tet4 线性弹性求解器，支持 STEP 模型导入和网格划分，计算 von Mises 应力
- `calculix`: 使用 CalculiX/Abaqus 格式的 `.inp` 文件，通过 `ccx` 命令行工具调用 CalculiX 求解器进行 FEA 分析，不依赖 SolidWorks COM

## CalculiX 配置

可通过 conda-forge 安装：

```powershell
conda install -y -c conda-forge calculix
```

配置 ccx 路径的优先级：

1. 环境变量 `OBARA_CALCULIX_CCX`
2. 环境变量 `CCX_PATH`
3. 在 `PATH` 中查找 `ccx` / `ccx.exe`

## 备注

使用 `calculix` 后端时，需要确保 CalculiX 已正确安装。UI 会自动生成 `.inp` 文件，提交 CalculiX 求解后读取 FRD/DAT 结果文件，UI 支持直接显示 CalculiX 的求解结果。