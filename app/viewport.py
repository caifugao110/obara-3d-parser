"""3D viewport based on pyvista + pyvistaqt.

Embeds a VTK render window inside Qt and provides:
  * surface-mesh display of the imported part,
  * click-to-pick surface faces (a face = all triangles sharing a Gmsh
    2D entity, exactly like selecting a face in SolidWorks),
  * coloured overlays for fixture faces (green) and load faces (red),
  * ISO contour plots of displacement magnitude and von Mises stress,
  * optional deformed-shape display with a configurable scale factor,
  * a triad showing the user-defined analysis coordinate system.
"""
from __future__ import annotations

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication
from typing import List, Optional
import vtk

from .geometry import Part
from .fea import FEAResult


FIXTURE_COLOR = (0.2, 0.8, 0.2)
LOAD_COLOR = (0.9, 0.2, 0.2)


def _surface_polydata(part: Part) -> pv.PolyData:
    pts = part.mesh.points
    tris = part.mesh.surf_tris
    if len(tris) == 0:
        return pv.PolyData(pts)
    faces = np.hstack([np.full((len(tris), 1), 3), tris]).ravel()
    return pv.PolyData(pts, faces)


def _face_submesh(part: Part, face_id: int) -> pv.PolyData:
    tris = part.mesh.surf_tris[part.mesh.tri_to_face == face_id]
    if len(tris) == 0:
        return pv.PolyData()
    faces = np.hstack([np.full((len(tris), 1), 3), tris]).ravel()
    # unique nodes needed
    nodes = np.unique(tris.ravel())
    return pv.PolyData(part.mesh.points[nodes], faces)


class Viewport(QtInteractor):
    """The central 3D view."""

    face_picked = Signal(int)   # emits the picked face id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.set_background("white")
        self._part: Optional[Part] = None
        self._surf: Optional[pv.PolyData] = None
        self._main_actor = None
        self._fixture_actors: List = []
        self._load_actors: List = []
        self._cs_actor = None
        self._picking_active = False
        self._result: Optional[FEAResult] = None
        self._deformed = False
        self._deform_scale = 1.0
        self._picker = vtk.vtkCellPicker()
        self._picker.SetTolerance(0.005)

    # ------------------------------------------------------------------ #
    # Part loading
    # ------------------------------------------------------------------ #
    def set_part(self, part: Part) -> None:
        self.clear_scene()
        self._part = part
        self._surf = _surface_polydata(part)
        self._main_actor = self.add_mesh(
            self._surf, color="lightgrey", show_edges=True, edge_color=(0.4, 0.4, 0.4),
            line_width=0.5, opacity=0.9, pickable=True,
        )
        self.add_axes_at_origin(labels_off=True)
        self.reset_camera_clipping_range()
        self.view_isometric()

    def clear_scene(self) -> None:
        self.clear()
        self._main_actor = None
        self._fixture_actors.clear()
        self._load_actors.clear()
        self._cs_actor = None
        self._surf = None
        self._result = None

    # ------------------------------------------------------------------ #
    # Picking
    # ------------------------------------------------------------------ #
    def set_picking_active(self, active: bool) -> None:
        self._picking_active = active

    def _on_pick(self, picked) -> None:
        if not self._picking_active or self._part is None or picked is None:
            return
        try:
            ids = picked.cell_data.get("vtkOriginalCellIds")
        except Exception:
            ids = None
        if ids is None or len(ids) == 0:
            return
        tri_id = int(ids[0])
        if 0 <= tri_id < len(self._part.mesh.tri_to_face):
            face_id = int(self._part.mesh.tri_to_face[tri_id])
            self.face_picked.emit(face_id)

    def mousePressEvent(self, event):
        if self._picking_active and self._part is not None and self._main_actor is not None:
            pos = event.position()
            x, y = pos.x(), pos.y()
            renderer = self.GetRenderWindow().GetRenderers().GetFirstRenderer()
            if renderer:
                self._picker.SetPickFromList(True)
                self._picker.InitializePickList()
                self._picker.AddPickList(self._main_actor)
                self._picker.Pick(x, self.GetRenderWindow().GetSize()[1] - y, 0, renderer)
                cell_id = self._picker.GetCellId()
                if cell_id >= 0:
                    tri_id = int(cell_id)
                    if 0 <= tri_id < len(self._part.mesh.tri_to_face):
                        face_id = int(self._part.mesh.tri_to_face[tri_id])
                        self.face_picked.emit(face_id)
                        return
        super().mousePressEvent(event)

    # ------------------------------------------------------------------ #
    # Highlighting
    # ------------------------------------------------------------------ #
    def highlight_fixtures(self, face_ids: List[int]) -> None:
        for a in self._fixture_actors:
            try:
                self.remove_actor(a)
            except Exception:
                pass
        self._fixture_actors.clear()
        if self._part is None:
            return
        for fid in face_ids:
            sub = _face_submesh(self._part, fid)
            if sub.n_points:
                a = self.add_mesh(
                    sub, color=FIXTURE_COLOR, opacity=0.85,
                    show_edges=True, edge_color=(0.0, 0.4, 0.0), pickable=False,
                )
                self._fixture_actors.append(a)

    def highlight_loads(self, face_ids: List[int]) -> None:
        for a in self._load_actors:
            try:
                self.remove_actor(a)
            except Exception:
                pass
        self._load_actors.clear()
        if self._part is None:
            return
        for fid in face_ids:
            sub = _face_submesh(self._part, fid)
            if sub.n_points:
                a = self.add_mesh(
                    sub, color=LOAD_COLOR, opacity=0.85,
                    show_edges=True, edge_color=(0.4, 0.0, 0.0), pickable=False,
                )
                self._load_actors.append(a)

    # ------------------------------------------------------------------ #
    # Coordinate-system triad
    # ------------------------------------------------------------------ #
    def show_coord_system(self, origin, x_axis, y_axis) -> None:
        if self._cs_actor is not None:
            try:
                self.remove_actor(self._cs_actor)
            except Exception:
                pass
            self._cs_actor = None
        origin = np.asarray(origin, dtype=float)
        x = np.asarray(x_axis, dtype=float)
        y = np.asarray(y_axis, dtype=float)
        z = np.cross(x, y)
        scale = self._scene_scale() * 0.25
        arrows = []
        for vec, col in ((x, (1, 0, 0)), (y, (0, 1, 0)), (z, (0, 0, 1))):
            v = vec / (np.linalg.norm(vec) + 1e-30) * scale
            arrow = pv.Arrow(start=origin, direction=v)
            arrows.append((arrow, col))
        for arrow, col in arrows:
            self.add_mesh(arrow, color=col)

    def _scene_scale(self) -> float:
        if self._part is None:
            return 1.0
        bb = self._part.mesh.points.max(axis=0) - self._part.mesh.points.min(axis=0)
        return float(np.linalg.norm(bb))

    # ------------------------------------------------------------------ #
    # Result display
    # ------------------------------------------------------------------ #
    def show_mesh_mode(self) -> None:
        if self._part is None:
            return
        self._deformed = False
        # rebuild undeformed surface
        self._surf = _surface_polydata(self._part)
        for a in self._fixture_actors + self._load_actors:
            try:
                self.remove_actor(a)
            except Exception:
                pass
        self._fixture_actors.clear()
        self._load_actors.clear()
        try:
            self.remove_actor(self._main_actor)
        except Exception:
            pass
        self._main_actor = self.add_mesh(
            self._surf, color="lightgrey", show_edges=True,
            edge_color=(0.4, 0.4, 0.4), line_width=0.5, opacity=0.9, pickable=True,
        )
        self._result = None

    def _deformed_points(self, result: FEAResult, scale: float) -> np.ndarray:
        pts = self._part.mesh.points.copy()
        pts += result.displacements * scale
        return pts

    def show_displacement(self, result: FEAResult, deformed: bool = False,
                          scale: float = 1.0) -> None:
        if self._part is None:
            return
        self._result = result
        self._deformed = deformed
        self._deform_scale = scale
        pts = self._deformed_points(result, scale) if deformed else self._part.mesh.points
        surf = pv.PolyData(
            pts,
            np.hstack([np.full((len(self._part.mesh.surf_tris), 1), 3),
                       self._part.mesh.surf_tris]).ravel(),
        )
        surf["位移 (mm)"] = result.disp_magnitude * 1000.0
        for a in self._fixture_actors + self._load_actors:
            try:
                self.remove_actor(a)
            except Exception:
                pass
        self._fixture_actors.clear()
        self._load_actors.clear()
        try:
            self.remove_actor(self._main_actor)
        except Exception:
            pass
        self._main_actor = self.add_mesh(
            surf, scalars="位移 (mm)", cmap="jet", show_edges=False,
            opacity=1.0, pickable=False, scalar_bar_args={"title": "位移 (mm)"},
        )
        self.add_text("位移 ISO 图", font_size=10)

    def show_stress(self, result: FEAResult, deformed: bool = False,
                    scale: float = 1.0) -> None:
        if self._part is None:
            return
        self._result = result
        self._deformed = deformed
        self._deform_scale = scale
        pts = self._deformed_points(result, scale) if deformed else self._part.mesh.points
        surf = pv.PolyData(
            pts,
            np.hstack([np.full((len(self._part.mesh.surf_tris), 1), 3),
                       self._part.mesh.surf_tris]).ravel(),
        )
        surf["von Mises (MPa)"] = result.von_mises / 1e6
        for a in self._fixture_actors + self._load_actors:
            try:
                self.remove_actor(a)
            except Exception:
                pass
        self._fixture_actors.clear()
        self._load_actors.clear()
        try:
            self.remove_actor(self._main_actor)
        except Exception:
            pass
        self._main_actor = self.add_mesh(
            surf, scalars="von Mises (MPa)", cmap="jet", show_edges=False,
            opacity=1.0, pickable=False, scalar_bar_args={"title": "von Mises (MPa)"},
        )
        self.add_text("应力 ISO 图", font_size=10)

    def reset_camera(self) -> None:
        if self._part is not None:
            self.view_isometric()
