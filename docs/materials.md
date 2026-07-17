# 材料库说明

材料库位于：

```text
material_data/sldmaterials.json
```

应用启动时通过 `app/material_db.py` 读取材料，并在材料库面板中按分类展示。

## 数据来源与用途

材料数据用于线性静力分析，至少需要：

- 弹性模量
- 泊松比
- 屈服强度

界面还会展示密度、抗拉强度、剪切模量、热膨胀系数、热导率、比热容等信息。并非所有字段都会直接参与当前求解。

## 单位约定

材料数据库按 SI 单位存储：

- 弹性模量 `EX`：Pa
- 泊松比 `NUXY`：无量纲
- 剪切模量 `GXY`：Pa
- 密度 `DENS`：kg/m³
- 屈服强度 `SIGYLD`：Pa
- 抗拉强度 `SIGXT`：Pa
- 热膨胀系数 `ALPX`：1/K
- 热导率 `KX`：W/(m·K)
- 比热容 `C`：J/(kg·K)

界面中常转换为：

- GPa：弹性模量、剪切模量
- MPa：屈服强度、抗拉强度

## 代码映射

`Material` 数据类字段：

| 字段 | 类型 | 说明 | 单位 |
|------|------|------|------|
| `name` | str | 材料名称 | - |
| `classification` | str | 分类名称 | - |
| `ex` | float | 弹性模量 | Pa |
| `nuxy` | float | 泊松比 | 无量纲 |
| `gxy` | float | 剪切模量 | Pa |
| `dens` | float | 密度 | kg/m³ |
| `sigyld` | float | 屈服强度 | Pa |
| `sigxt` | float | 抗拉强度 | Pa |
| `alpx` | float | 热膨胀系数 | 1/K |
| `kx` | float | 热导率 | W/(m·K) |
| `c` | float | 比热容 | J/(kg·K) |
| `swatch_color` | str | 颜色样本（十六进制） | - |
| `description` | str | 材料描述 | - |

便捷属性：

- `youngs_modulus()`：返回弹性模量
- `poisson()`：返回泊松比
- `yield_strength()`：返回屈服强度

## 从文件夹加载材料库

程序支持从外部文件夹加载自定义材质库，该文件夹下的所有 `*.json` 文件会被自动扫描并合并。

### 使用方式

在主窗口中点击菜单：

```text
文件 > 选择材质库文件夹...
```

或通过代码调用：

```python
from app.material_db import load_material_database_from_dir

materials = load_material_database_from_dir("/path/to/material/folder")
```

### JSON 文件格式

每个 JSON 文件需包含以下结构：

```json
{
  "classifications": [
    {
      "name": "分类名称",
      "materials": [
        {
          "name": "材料名称",
          "description": "材料描述",
          "swatchcolor": {
            "RGB": "ffffff"
          },
          "physicalproperties": {
            "EX": { "value": 2.0e11 },
            "NUXY": { "value": 0.3 },
            "DENS": { "value": 7850 },
            "SIGYLD": { "value": 2.5e8 },
            "SIGXT": { "value": 4.0e8 },
            "GXY": { "value": 7.7e10 },
            "ALPX": { "value": 1.2e-5 },
            "KX": { "value": 45 },
            "C": { "value": 450 }
          }
        }
      ]
    }
  ]
}
```

## 添加新材料

### 方法一：编辑内置材料库

1. 打开 `material_data/sldmaterials.json`。
2. 在合适分类下添加材料记录。
3. 确保关键字段使用 SI 单位。
4. 运行程序并在材料库面板中检查显示。
5. 运行测试：

```powershell
pytest
```

### 方法二：创建外部材料库

1. 创建一个新的 JSON 文件，格式如上所述。
2. 将文件放入一个单独的文件夹。
3. 在程序中通过"选择材质库文件夹"加载。

## 材料选择建议

- 对结构刚度敏感的问题，应优先确认弹性模量和泊松比。
- 对安全系数敏感的问题，应确认屈服强度。
- 当前求解为线弹性静力分析，不会模拟塑性屈服后的行为。
- 如果材料属性缺失或明显不合理，安全系数和应力判断会失真。
- 多零件模型中，不同零件可分配不同材料，实现多材料分析。