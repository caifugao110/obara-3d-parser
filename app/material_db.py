"""Material database loader for the SolidWorks-style material library.

Reads ``sldmaterials.json`` and exposes the FEA-relevant physical properties
of each material.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Material:
    """A single material with the properties needed for static FEA.

    All SI units (matching the source database):
      * EX      Young's modulus      [Pa]
      * NUXY    Poisson's ratio      [-]
      * GXY     Shear modulus        [Pa]
      * DENS    Density              [kg/m^3]
      * SIGYLD  Yield strength       [Pa]
      * SIGXT   Tensile strength     [Pa]
    """

    name: str
    classification: str
    ex: float            # 弹性模量
    nuxy: float          # 普阿松比率
    dens: float          # 密度
    sigyld: float        # 屈服力
    sigxt: float = 0.0   # 张力强度
    gxy: float = 0.0     # 抗剪模量
    alpx: float = 0.0    # 热扩张系数
    kx: float = 0.0      # 热导率
    c: float = 0.0       # 特定热
    swatch_color: str = "ffffff"
    description: str = ""

    def youngs_modulus(self) -> float:
        return self.ex

    def poisson(self) -> float:
        return self.nuxy

    def yield_strength(self) -> float:
        return self.sigyld


def _f(props: Dict, key: str, default: float = 0.0) -> float:
    entry = props.get(key)
    if isinstance(entry, dict):
        try:
            return float(entry.get("value", default))
        except (TypeError, ValueError):
            return default
    return default


def load_material_database(path: str | Path) -> List[Material]:
    """Load the full material database from ``sldmaterials.json``."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    materials: List[Material] = []
    for cls in data.get("classifications", []):
        cls_name = cls.get("name", "")
        for m in cls.get("materials", []):
            props = m.get("physicalproperties", {}) or {}
            swatch = m.get("swatchcolor", {}) or {}
            color = swatch.get("RGB", "ffffff") if isinstance(swatch, dict) else "ffffff"
            materials.append(
                Material(
                    name=m.get("name", ""),
                    classification=cls_name,
                    ex=_f(props, "EX"),
                    nuxy=_f(props, "NUXY"),
                    gxy=_f(props, "GXY"),
                    alpx=_f(props, "ALPX"),
                    dens=_f(props, "DENS"),
                    kx=_f(props, "KX"),
                    c=_f(props, "C"),
                    sigyld=_f(props, "SIGYLD"),
                    sigxt=_f(props, "SIGXT"),
                    swatch_color=color,
                    description=m.get("description", "") or "",
                )
            )
    return materials


def group_by_classification(materials: List[Material]) -> Dict[str, List[Material]]:
    grouped: Dict[str, List[Material]] = {}
    for m in materials:
        grouped.setdefault(m.classification, []).append(m)
    return grouped


def find_material(materials: List[Material], name: str) -> Optional[Material]:
    for m in materials:
        if m.name == name:
            return m
    return None


def load_material_database_from_dir(dir_path: str | Path) -> List[Material]:
    """Load material database from all JSON files in a directory.

    Searches for all *.json files in the given directory and merges their
    material data into a single list.
    """
    dir_path = Path(dir_path)
    if not dir_path.is_dir():
        raise ValueError(f"Not a directory: {dir_path}")

    all_materials: List[Material] = []
    for json_file in sorted(dir_path.glob("*.json")):
        try:
            materials = load_material_database(json_file)
            all_materials.extend(materials)
        except Exception:
            continue
    return all_materials
