"""Study data model.

Bundles everything that defines a single static study: the imported parts,
their assigned materials, the restraints, the loads, the analysis coordinate
system and (after solving) the result. Kept Qt-free so it can be unit
tested and serialised independently of the UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .geometry import Part
from .material_db import Material
from .fea import CoordSystem, FEAResult, Fixture, PressureLoad, ForceLoad


@dataclass
class Study:
    name: str = "静态分析"
    parts: List[Part] = field(default_factory=list)
    fixtures: List[Fixture] = field(default_factory=list)
    loads: List[object] = field(default_factory=list)  # PressureLoad | ForceLoad
    coord_system: CoordSystem = field(default_factory=CoordSystem)
    result: Optional[FEAResult] = None
    mesh_size: float = 5.0
    solver_backend: str = "internal"

    @property
    def part(self) -> Optional[Part]:
        return self.parts[0] if self.parts else None
    
    @part.setter
    def part(self, value: Optional[Part]) -> None:
        if value is None:
            self.parts = []
        else:
            self.parts = [value]
    
    @property
    def material(self) -> Optional[Material]:
        if self.parts:
            return self.parts[0].material
        return None
    
    @material.setter
    def material(self, value: Optional[Material]) -> None:
        if self.parts:
            self.parts[0].material = value

    def is_ready(self) -> bool:
        return (
            len(self.parts) > 0
            and all(p.material is not None for p in self.parts)
            and len(self.fixtures) > 0
            and len(self.loads) > 0
            and self.mesh_size > 0
        )

    def ready_report(self) -> List[str]:
        missing: List[str] = []
        if not self.parts:
            missing.append("尚未导入 STEP 数模")
        else:
            for i, p in enumerate(self.parts):
                if p.material is None:
                    missing.append(f"零件 {i+1} ({p.name}) 尚未定义材质")
        if not self.fixtures:
            missing.append("尚未定义固定位置")
        if not self.loads:
            missing.append("尚未定义加压位置/压力")
        if self.mesh_size <= 0:
            missing.append("网格密度无效")
        return missing

    def clear_result(self) -> None:
        self.result = None

    def clear_setup(self) -> None:
        self.fixtures.clear()
        self.loads.clear()
        self.result = None

    def fixture_face_ids(self) -> List[int]:
        return [f.face_id for f in self.fixtures]

    def load_face_ids(self) -> List[int]:
        return [l.face_id for l in self.loads]
    
    def get_part_materials(self) -> List[Optional[Material]]:
        return [p.material for p in self.parts]
