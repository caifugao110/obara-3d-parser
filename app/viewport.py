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
from typing import List, Optional
import vtk

try:
    from pyvistaqt import QtInteractor
    from PySide6.QtCore import Signal
    from PySide6.QtWidgets import QApplication
except Exception:  # noqa: BLE001 - allow headless helpers without Qt bindings
    QtInteractor = object

    class Signal:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            pass

    QApplication = None  # type: ignore[assignment]

from .geometry import Part
from .fea import FEAResult


FIXTURE_COLOR = (0.9, 0.2, 0.2)
LOAD_COLOR = (0.2, 0.2, 0.9)
SELECTED_COLOR = (0.2, 0.8, 0.2)
PART_HIGHLIGHT_COLOR = (0.8, 0.8, 0.2)


def _surface_polydata(part: Part) -> pv.PolyData:
    if part.mesh is None:
        return pv.PolyData()
    pts = part.mesh.points
    tris = part.mesh.surf_tris
    if len(tris) == 0:
        return pv.PolyData(pts)
    faces = np.hstack([np.full((len(tris), 1), 3), tris]).ravel()
    return pv.PolyData(pts, faces)


def _face_submesh(part: Part, face_id: int) -> pv.PolyData:
    if part.mesh is None:
        return pv.PolyData()
    tris = part.mesh.surf_tris[part.mesh.tri_to_face == face_id]
    if len(tris) == 0:
        return pv.PolyData()
    faces = np.hstack([np.full((len(tris), 1), 3), tris]).ravel()
    nodes = np.unique(tris.ravel())
    return pv.PolyData(part.mesh.points[nodes], faces)


class Viewport(QtInteractor):
    """The central 3D view."""

    face_picked = Signal(int)   # emits the picked face id
    probe_data = Signal(dict)   # emits probe data when clicking on result
    part_picked = Signal(int)   # emits the picked part index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.set_background("white")
        self._part: Optional[Part] = None
        self._surf: Optional[pv.PolyData] = None
        self._main_actor = None
        self._fixture_actors: List = []
        self._load_actors: List = []
        self._cs_actor = None
        self._selected_face_actor = None
        self._part_highlight_actor = None
        self._picking_active = False
        self._probe_mode = False
        self._part_picking_mode = False
        self._auto_part_select = False
        self._result: Optional[FEAResult] = None
        self._deformed = False
        self._deform_scale = 1.0
        self._picker = vtk.vtkCellPicker()
        self._picker.SetTolerance(0.005)
        self._point_picker = vtk.vtkPointPicker()
        self._point_picker.SetTolerance(0.005)
        self._face_colors: Dict[int, tuple] = {}
        self._part_colors: Dict[int, tuple] = {}
        self._default_color = (0.6, 0.6, 0.6)
        self._selected_face_id = None
        self._selected_part_idx = None
        self._display_mode = "smooth"

    # ------------------------------------------------------------------ #
    # Part loading
    # ------------------------------------------------------------------ #
    def set_part(self, part: Part, show_edges: bool = False, smooth_shading: bool = True) -> None:
        self.clear_scene()
        self._part = part
        if part.mesh is not None:
            self._surf = _surface_polydata(part)
            self._main_actor = self.add_mesh(
                self._surf, color="lightgrey", show_edges=show_edges, edge_color=(0.4, 0.4, 0.4),
                line_width=0.5, opacity=0.9, pickable=True, smooth_shading=smooth_shading,
            )
        else:
            self._surf = None
            self._main_actor = None
        self.reset_camera_clipping_range()
        self.view_isometric()

    def clear_scene(self) -> None:
        self.clear()
        self._main_actor = None
        self._fixture_actors.clear()
        self._load_actors.clear()
        self._cs_actor = None
        self._selected_face_actor = None
        self._part_highlight_actor = None
        self._surf = None
        self._result = None
        self._face_colors.clear()
        self._selected_face_id = None

    def apply_face_color(self, face_id: int, color: tuple) -> None:
        self._face_colors[face_id] = color
        if self._part is not None and self._part.mesh is not None:
            if self._display_mode == "smooth":
                self.show_smooth_mode()
            elif self._display_mode == "mesh":
                self.show_mesh_mode()

    def clear_face_colors(self) -> None:
        self._face_colors.clear()
        if self._part is not None and self._part.mesh is not None:
            if self._display_mode == "smooth":
                self.show_smooth_mode()
            elif self._display_mode == "mesh":
                self.show_mesh_mode()
    
    def apply_part_color(self, part_idx: int, color: tuple) -> None:
        self._part_colors[part_idx] = color
        if self._part is not None and self._part.mesh is not None:
            if self._display_mode == "smooth":
                self.show_smooth_mode()
            elif self._display_mode == "mesh":
                self.show_mesh_mode()
    
    def clear_part_colors(self) -> None:
        self._part_colors.clear()
        if self._part is not None and self._part.mesh is not None:
            if self._display_mode == "smooth":
                self.show_smooth_mode()
            elif self._display_mode == "mesh":
                self.show_mesh_mode()
    
    def clear_all_colors(self) -> None:
        self._face_colors.clear()
        self._part_colors.clear()
        if self._part is not None and self._part.mesh is not None:
            if self._display_mode == "smooth":
                self.show_smooth_mode()
            elif self._display_mode == "mesh":
                self.show_mesh_mode()

    # ------------------------------------------------------------------ #
    # Picking
    # ------------------------------------------------------------------ #
    def set_picking_active(self, active: bool) -> None:
        self._picking_active = active
    
    def set_probe_mode(self, active: bool) -> None:
        self._probe_mode = active
    
    def set_part_picking_mode(self, active: bool) -> None:
        self._part_picking_mode = active
        self._picking_active = not active
    
    def set_auto_part_select(self, active: bool) -> None:
        self._auto_part_select = active
    
    def highlight_selected_face(self, face_id: int) -> None:
        if self._selected_face_actor is not None:
            try:
                self.remove_actor(self._selected_face_actor)
            except Exception:
                pass
            self._selected_face_actor = None
        
        if self._part is None or face_id < 0:
            self._selected_face_id = None
            return
        
        self._selected_face_id = face_id
        sub = _face_submesh(self._part, face_id)
        if sub.n_points:
            self._selected_face_actor = self.add_mesh(
                sub, color=SELECTED_COLOR, opacity=0.7,
                show_edges=True, edge_color=(0.0, 0.6, 0.0), pickable=False,
            )
    
    def highlight_part(self, part_idx: int, parts: list = None) -> None:
        if self._part_highlight_actor is not None:
            try:
                self.remove_actor(self._part_highlight_actor)
            except Exception:
                pass
            self._part_highlight_actor = None
        
        if self._part is None or self._part.mesh is None:
            return
        
        force_highlight = parts is not None and len(parts) == 1 and parts[0] is None
        if not force_highlight and (parts is None or len(parts) <= 1):
            return
        
        self._selected_part_idx = part_idx
        mesh = self._part.mesh
        
        if len(mesh.tets) > 0 and len(mesh.tet_to_part) > 0:
            tet_to_part = mesh.tet_to_part
            part_mask = tet_to_part == part_idx
            if not np.any(part_mask):
                return
            
            part_tets = mesh.tets[part_mask]
            if len(part_tets) == 0:
                return
            
            part_nodes = np.unique(part_tets.ravel())
            part_tris = mesh.surf_tris[np.isin(mesh.surf_tris, part_nodes).any(axis=1)]
        elif hasattr(mesh, 'tri_to_part') and len(mesh.tri_to_part) > 0:
            tri_to_part = mesh.tri_to_part
            part_mask = tri_to_part == part_idx
            if not np.any(part_mask):
                return
            
            part_tris = mesh.surf_tris[part_mask]
            part_nodes = np.unique(part_tris.ravel())
        else:
            return
        
        if len(part_tris) == 0:
            return
        
        faces = np.hstack([np.full((len(part_tris), 1), 3), part_tris]).ravel()
        sub = pv.PolyData(mesh.points[part_nodes], faces)
        
        self._part_highlight_actor = self.add_mesh(
            sub, color=PART_HIGHLIGHT_COLOR, opacity=0.7,
            show_edges=True, edge_color=(0.6, 0.6, 0.0), pickable=False,
        )

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
        if self._probe_mode and self._result is not None and self._part is not None and self._part.mesh is not None:
            pos = event.position()
            x, y = pos.x(), pos.y()
            renderer = self.GetRenderWindow().GetRenderers().GetFirstRenderer()
            if renderer:
                self._point_picker.Pick(x, self.GetRenderWindow().GetSize()[1] - y, 0, renderer)
                point_id = self._point_picker.GetPointId()
                if point_id >= 0 and point_id < self._result.num_nodes:
                    ux = self._result.displacements[point_id, 0] * 1000
                    uy = self._result.displacements[point_id, 1] * 1000
                    uz = self._result.displacements[point_id, 2] * 1000
                    disp_mag = self._result.disp_magnitude[point_id] * 1000
                    stress = self._result.von_mises[point_id] / 1e6
                    coords = self._part.mesh.points[point_id]
                    self.probe_data.emit({
                        "point_id": int(point_id),
                        "coords": coords.tolist(),
                        "ux": float(ux),
                        "uy": float(uy),
                        "uz": float(uz),
                        "disp_magnitude": float(disp_mag),
                        "von_mises": float(stress),
                    })
                    return
        
        if self._part_picking_mode and self._part is not None and self._part.mesh is not None:
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
                        tet_to_part = self._part.mesh.tet_to_part
                        if len(tet_to_part) > 0:
                            part_idx = int(tet_to_part[tri_id] if tri_id < len(tet_to_part) else 0)
                        else:
                            part_idx = 0
                        self.part_picked.emit(part_idx)
                        return
        
        if self._picking_active and self._part is not None and self._main_actor is not None:
            pos = event.position()
            x, y = pos.x(), pos.y()
            renderer = self.GetRenderWindow().GetRenderers().GetFirstRenderer()
            if renderer and self._part.mesh is not None:
                self._picker.SetPickFromList(True)
                self._picker.InitializePickList()
                self._picker.AddPickList(self._main_actor)
                self._picker.Pick(x, self.GetRenderWindow().GetSize()[1] - y, 0, renderer)
                cell_id = self._picker.GetCellId()
                if cell_id >= 0:
                    tri_id = int(cell_id)
                    if 0 <= tri_id < len(self._part.mesh.tri_to_face):
                        face_id = int(self._part.mesh.tri_to_face[tri_id])
                        self.highlight_selected_face(face_id)
                        self.face_picked.emit(face_id)
                        return
        
        if self._auto_part_select and self._part is not None and self._part.mesh is not None:
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
                        tet_to_part = self._part.mesh.tet_to_part
                        if len(tet_to_part) > 0:
                            part_idx = int(tet_to_part[tri_id] if tri_id < len(tet_to_part) else 0)
                        else:
                            part_idx = 0
                        self.part_picked.emit(part_idx)
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
                    show_edges=True, edge_color=(0.6, 0.0, 0.0), pickable=False,
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
        x = np.asarray(x_axis, dtype=float)
        y = np.asarray(y_axis, dtype=float)
        z = np.cross(x, y)
        scale = self._scene_scale() * 0.15
        cs_origin = np.array([0.0, 0.0, 0.0])
        for vec, col, label in ((x, (1, 0, 0), "X"), (y, (0, 1, 0), "Y"), (z, (0, 0, 1), "Z")):
            v = vec / (np.linalg.norm(vec) + 1e-30) * scale
            arrow = pv.Arrow(start=cs_origin, direction=v)
            self.add_mesh(arrow, color=col)
            label_pos = cs_origin + v * 1.1
            self.add_text(label, position=label_pos, font_size=12, color=col, shadow=True)

    def _scene_scale(self) -> float:
        if self._part is None:
            return 1.0
        bb = self._part.mesh.points.max(axis=0) - self._part.mesh.points.min(axis=0)
        return float(np.linalg.norm(bb))

    # ------------------------------------------------------------------ #
    # Result display
    # ------------------------------------------------------------------ #
    def show_smooth_mode(self) -> None:
        if self._part is None:
            return
        self._display_mode = "smooth"
        self._deformed = False
        for a in self._fixture_actors + self._load_actors:
            try:
                self.remove_actor(a)
            except Exception:
                pass
        self._fixture_actors.clear()
        self._load_actors.clear()
        
        if self._selected_face_actor is not None:
            try:
                self.remove_actor(self._selected_face_actor)
            except Exception:
                pass
            self._selected_face_actor = None
        
        if self._part_highlight_actor is not None:
            try:
                self.remove_actor(self._part_highlight_actor)
            except Exception:
                pass
            self._part_highlight_actor = None
        
        if self._part.mesh is not None:
            self._surf = _surface_polydata(self._part)
            self._apply_face_colors_to_surf()
            try:
                self.remove_actor(self._main_actor)
            except Exception:
                pass
            if self._face_colors:
                self._main_actor = self.add_mesh(
                    self._surf, scalars="face_color", show_edges=False,
                    line_width=0.5, opacity=0.9, pickable=True, smooth_shading=True,
                    rgb=True,
                )
            else:
                self._main_actor = self.add_mesh(
                    self._surf, color="lightgrey", show_edges=False,
                    line_width=0.5, opacity=0.9, pickable=True, smooth_shading=True,
                )
        self._result = None
        
        if self._selected_face_id is not None:
            self.highlight_selected_face(self._selected_face_id)
        
        if self._selected_part_idx is not None:
            self.highlight_part(self._selected_part_idx, [None])

    def _apply_face_colors_to_surf(self) -> None:
        if self._part is None or self._surf is None:
            return
        tri_to_face = self._part.mesh.tri_to_face
        colors = np.zeros((len(tri_to_face), 3), dtype=np.float64)
        default = np.array(self._default_color, dtype=np.float64)
        
        tri_to_part = getattr(self._part.mesh, 'tri_to_part', None)
        
        for i, face_id in enumerate(tri_to_face):
            part_idx = int(tri_to_part[i]) if tri_to_part is not None and i < len(tri_to_part) else 0
            
            if face_id in self._face_colors:
                colors[i] = np.array(self._face_colors[face_id], dtype=np.float64)
            elif part_idx in self._part_colors:
                colors[i] = np.array(self._part_colors[part_idx], dtype=np.float64)
            else:
                colors[i] = default
        self._surf["face_color"] = colors

    def show_mesh_mode(self) -> None:
        if self._part is None:
            return
        self._display_mode = "mesh"
        self._deformed = False
        for a in self._fixture_actors + self._load_actors:
            try:
                self.remove_actor(a)
            except Exception:
                pass
        self._fixture_actors.clear()
        self._load_actors.clear()
        
        if self._selected_face_actor is not None:
            try:
                self.remove_actor(self._selected_face_actor)
            except Exception:
                pass
            self._selected_face_actor = None
        
        if self._part.mesh is not None:
            self._surf = _surface_polydata(self._part)
            self._apply_face_colors_to_surf()
            try:
                self.remove_actor(self._main_actor)
            except Exception:
                pass
            if self._face_colors:
                self._main_actor = self.add_mesh(
                    self._surf, scalars="face_color", show_edges=True,
                    edge_color=(0.4, 0.4, 0.4), line_width=0.5, opacity=0.9, pickable=True,
                    smooth_shading=False, rgb=True,
                )
            else:
                self._main_actor = self.add_mesh(
                    self._surf, color="lightgrey", show_edges=True,
                    edge_color=(0.4, 0.4, 0.4), line_width=0.5, opacity=0.9, pickable=True,
                    smooth_shading=False,
                )
        self._result = None
        
        if self._selected_face_id is not None:
            self.highlight_selected_face(self._selected_face_id)

    def _deformed_points(self, result: FEAResult, scale: float) -> np.ndarray:
        pts = self._part.mesh.points.copy()
        pts += result.displacements * scale
        return pts

    def show_displacement(self, result: FEAResult, deformed: bool = False,
                          scale: float = 1.0, component: str = "magnitude") -> None:
        if self._part is None or self._part.mesh is None:
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

        component_key = component.lower()
        if component_key in {"x", "ux"}:
            scalar_name = "UX displacement (mm)"
            scalar_values = result.displacements[:, 0] * 1000.0
            title = "UX displacement ISO"
        elif component_key in {"y", "uy"}:
            scalar_name = "UY displacement (mm)"
            scalar_values = result.displacements[:, 1] * 1000.0
            title = "UY displacement ISO"
        elif component_key in {"z", "uz"}:
            scalar_name = "UZ displacement (mm)"
            scalar_values = result.displacements[:, 2] * 1000.0
            title = "UZ displacement ISO"
        else:
            scalar_name = "Resultant displacement (mm)"
            scalar_values = result.disp_magnitude * 1000.0
            title = "Resultant displacement ISO"
        surf[scalar_name] = scalar_values
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
            surf, scalars=scalar_name, cmap="jet", show_edges=False,
            opacity=1.0, pickable=False, scalar_bar_args={"title": scalar_name},
        )
        self.add_text(title, font_size=10)

    def show_stress(self, result: FEAResult, deformed: bool = False,
                          scale: float = 1.0) -> None:
        if self._part is None or self._part.mesh is None:
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

