"""Study data model.

Bundles everything that defines a single static study: the imported part,
its assigned material, the restraints, the loads, the analysis coordinate
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
    part: Optional[Part] = None
    material: Optional[Material] = None
    fixtures: List[Fixture] = field(default_factory=list)
    loads: List[object] = field(default_factory=list)  # PressureLoad | ForceLoad
    coord_system: CoordSystem = field(default_factory=CoordSystem)
    result: Optional[FEAResult] = None

    # --- convenience checks -------------------------------------------------
    def is_ready(self) -> bool:
        return (
            self.part is not None
            and self.material is not None
            and len(self.fixtures) > 0
            and len(self.loads) > 0
        )

    def ready_report(self) -> List[str]:
        missing: List[str] = []
        if self.part is None:
            missing.append("尚未导入 STEP 数模")
        if self.material is None:
            missing.append("尚未定义零件材质")
        if not self.fixtures:
            missing.append("尚未定义固定位置")
        if not self.loads:
            missing.append("尚未定义加压位置/压力")
        return missing

    def clear_result(self) -> None:
        self.result = None

    def fixture_face_ids(self) -> List[int]:
        return [f.face_id for f in self.fixtures]

    def load_face_ids(self) -> List[int]:
        return [l.face_id for l in self.loads]
