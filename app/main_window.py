"""Main application window.

Wires the viewport, material library, study-setup and results panels into a
single SolidWorks-Simulation-like workflow:

  import STEP → assign material → pick fixed faces → pick loaded faces +
  pressure → define CS → run → view ISO displacement / stress.
"""
from __future__ import annotations

import os
import sys
from typing import Optional, List

import numpy as np
from PySide6.QtCore import Qt, QObject, QThread, Signal
import time
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QFileDialog,
    QStatusBar, QMessageBox, QInputDialog, QDialog, QFormLayout, QDoubleSpinBox,
    QDialogButtonBox, QLabel, QApplication, QPushButton,
)

from .material_db import load_material_database, load_material_database_from_dir, Material
from .geometry import load_step, make_test_beam, mesh_part, Part
from .fea import CoordSystem, Fixture, PressureLoad, ForceLoad, FEAResult
from .solver_backends import BACKENDS, solve_study
from .study import Study
from .viewport import Viewport
from .panels import MaterialPanel, StudySetupPanel, ResultsPanel


# --------------------------------------------------------------------------- #
# Background solver worker
# --------------------------------------------------------------------------- #
class _SolveWorker(QObject):
    progress = Signal(str)
    finished = Signal(object)   # FEAResult or Exception
    log_message = Signal(str)

    def __init__(self, study: Study):
        super().__init__()
        self.study = study

    def run(self) -> None:
        start_time = time.time()
        try:
            self.log_message.emit(f"开始仿真: {time.strftime('%H:%M:%S')}")
            self.log_message.emit(f"零件数: {len(self.study.parts)}")
            self.log_message.emit(f"网格尺寸: {self.study.mesh_size:.2f} mm")
            
            result = solve_study(
                self.study.solver_backend,
                self.study.parts,
                self.study.fixtures,
                self.study.loads,
                self.study.coord_system,
                progress=lambda s: self.progress.emit(s),
            )
            
            elapsed = time.time() - start_time
            self.log_message.emit(f"仿真完成: {time.strftime('%H:%M:%S')}")
            self.log_message.emit(f"总耗时: {elapsed:.2f} 秒")
            self.log_message.emit(f"节点数: {result.num_nodes}")
            self.log_message.emit(f"单元数: {result.num_tets}")
            
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            elapsed = time.time() - start_time
            self.log_message.emit(f"仿真失败: {time.strftime('%H:%M:%S')}")
            self.log_message.emit(f"总耗时: {elapsed:.2f} 秒")
            self.log_message.emit(f"错误: {str(exc)}")
            self.finished.emit(exc)


# --------------------------------------------------------------------------- #
# Small dialog for entering external force value
# --------------------------------------------------------------------------- #
class _LoadDialog(QDialog):
    def __init__(self, parent=None, load=None):
        super().__init__(parent)
        self.setWindowTitle("定义载荷")
        form = QFormLayout(self)

        from PySide6.QtWidgets import QRadioButton, QGroupBox, QHBoxLayout

        self.radio_normal = QRadioButton("法向")
        self.radio_direction = QRadioButton("选定的方向")
        self.radio_normal.setChecked(True)
        load_type_group = QGroupBox("载荷类型")
        load_type_layout = QHBoxLayout(load_type_group)
        load_type_layout.addWidget(self.radio_normal)
        load_type_layout.addWidget(self.radio_direction)
        form.addRow(load_type_group)

        self.value_spin = QDoubleSpinBox()
        self.value_spin.setRange(-1e9, 1e9)
        self.value_spin.setDecimals(2)
        self.value_spin.setValue(1000.0)
        form.addRow("载荷值 (N):", self.value_spin)

        self.dir_x = QDoubleSpinBox()
        self.dir_x.setRange(-1, 1)
        self.dir_x.setValue(0.0)
        self.dir_x.setDecimals(4)
        self.dir_y = QDoubleSpinBox()
        self.dir_y.setRange(-1, 1)
        self.dir_y.setValue(0.0)
        self.dir_y.setDecimals(4)
        self.dir_z = QDoubleSpinBox()
        self.dir_z.setRange(-1, 1)
        self.dir_z.setValue(-1.0)
        self.dir_z.setDecimals(4)

        dir_group = QGroupBox("方向 (选定方向模式)")
        dir_layout = QFormLayout(dir_group)
        dir_layout.addRow("X:", self.dir_x)
        dir_layout.addRow("Y:", self.dir_y)
        dir_layout.addRow("Z:", self.dir_z)
        form.addRow(dir_group)

        def update_dir_enabled():
            enabled = self.radio_direction.isChecked()
            self.dir_x.setEnabled(enabled)
            self.dir_y.setEnabled(enabled)
            self.dir_z.setEnabled(enabled)

        self.radio_normal.toggled.connect(update_dir_enabled)
        self.radio_direction.toggled.connect(update_dir_enabled)
        if load is not None:
            self.value_spin.setValue(float(load.force))
            if hasattr(load, "direction"):
                self.radio_direction.setChecked(True)
                self.dir_x.setValue(float(load.direction[0]))
                self.dir_y.setValue(float(load.direction[1]))
                self.dir_z.setValue(float(load.direction[2]))
            else:
                self.radio_normal.setChecked(True)
        update_dir_enabled()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def is_normal(self) -> bool:
        return self.radio_normal.isChecked()

    def value(self) -> float:
        return float(self.value_spin.value())

    def direction(self) -> tuple:
        return (
            float(self.dir_x.value()),
            float(self.dir_y.value()),
            float(self.dir_z.value()),
        )


# --------------------------------------------------------------------------- #
# Main window
# --------------------------------------------------------------------------- #
class MainWindow(QMainWindow):
    def __init__(self, material_db_path: str):
        super().__init__()
        self._base_window_title = "obara-3d-parser - 简易版 SolidWorks 仿真"
        self.setWindowTitle(self._base_window_title)
        self.resize(1400, 900)

        self.study = Study()
        self._materials = load_material_database(material_db_path)
        self._pick_mode = "none"          # "none" | "fixture" | "load" | "color" | "part_color" | "probe"
        self._solve_thread: Optional[QThread] = None
        self._solve_worker: Optional[_SolveWorker] = None
        self._display_mode = "smooth"     # "smooth" | "mesh" | "disp" | "stress"
        self._current_part_idx = 0
        self._edit_fixture_idx = -1
        self._edit_load_idx = -1
        self._pending_edit_load = None
        self._face_color = (0.8, 0.2, 0.2)
        self._part_color = (0.2, 0.2, 0.8)

        self._build_ui()
        self._refresh_all()
        self.statusBar().showMessage("就绪。请导入 STEP 数模。")
        
        self.material_panel.setMinimumHeight(500)
        self.results_panel.setMinimumHeight(300)
        
        self._initial_dock_state = self.saveState()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        # central viewport
        self.viewport = Viewport(self)
        self.setCentralWidget(self.viewport)
        self.viewport.face_picked.connect(self._on_face_picked)
        self.viewport.probe_data.connect(self._on_probe_data)
        self.viewport.part_picked.connect(self._on_part_picked)

        # dock panels
        self.material_panel = MaterialPanel(self._materials, self)
        self.material_panel.apply_material.connect(self._apply_material)
        self.material_panel.part_selected.connect(self._select_part)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.material_panel)

        self.results_panel = ResultsPanel(self)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.results_panel)
        self.splitDockWidget(self.material_panel, self.results_panel, Qt.Vertical)

        self.setup_panel = StudySetupPanel(self)
        self.setup_panel.set_study(self.study)
        self.setup_panel.add_fixture_clicked.connect(self._begin_pick_fixture)
        self.setup_panel.add_load_clicked.connect(self._begin_pick_load)
        self.setup_panel.remove_fixture.connect(self._remove_fixture)
        self.setup_panel.remove_load.connect(self._remove_load)
        self.setup_panel.run_clicked.connect(self._run_simulation)
        self.setup_panel.coord_changed.connect(self._on_coord_changed)
        self.setup_panel.mesh_size_changed.connect(lambda _: self._update_ready_state())
        self.setup_panel.mesh_clicked.connect(self._do_mesh)
        self.setup_panel.part_material_clicked.connect(self._on_part_material_clicked)
        self.setup_panel.solver_backend_changed.connect(self._on_solver_backend_changed)
        self.setup_panel.btn_add_fix.clicked.connect(self._begin_pick_fixture)
        self.setup_panel.btn_add_load.clicked.connect(self._begin_pick_load)
        self.setup_panel.edit_fixture_requested.connect(self._on_edit_fixture)
        self.setup_panel.edit_load_requested.connect(self._on_edit_load)
        self.addDockWidget(Qt.RightDockWidgetArea, self.setup_panel)

        self._build_toolbar()
        self._build_menu()

    def _build_toolbar(self) -> None:
        tb = QToolBar("主工具栏")
        tb.setMovable(False)
        self.addToolBar(tb)

        a_import = QAction("导入 STEP", self)
        a_import.triggered.connect(self._import_step)
        tb.addAction(a_import)

        tb.addSeparator()

        a_smooth = QAction("原始视图", self)
        a_smooth.triggered.connect(lambda: self._set_display_mode("smooth"))
        tb.addAction(a_smooth)

        self.a_mesh = QAction("网格视图", self)
        self.a_mesh.triggered.connect(lambda: self._set_display_mode("mesh"))
        self.a_mesh.setEnabled(False)
        tb.addAction(self.a_mesh)

        a_reset = QAction("重置视图", self)
        a_reset.triggered.connect(self.viewport.reset_camera)
        tb.addAction(a_reset)

        a_reset_layout = QAction("重置布局", self)
        a_reset_layout.triggered.connect(self._reset_layout)
        tb.addAction(a_reset_layout)

        a_clear_panels = QAction("清空面板", self)
        a_clear_panels.triggered.connect(self._clear_panels)
        tb.addAction(a_clear_panels)

        a_disp = QAction("位移 ISO", self)
        a_disp.triggered.connect(lambda: self._set_display_mode("disp"))
        tb.addAction(a_disp)

        a_stress = QAction("应力 ISO", self)
        a_stress.triggered.connect(lambda: self._set_display_mode("stress"))
        tb.addAction(a_stress)

        a_probe = QAction("探测模式", self)
        a_probe.triggered.connect(self._toggle_probe_mode)
        tb.addAction(a_probe)

        tb.addSeparator()
        self.btn_face_color_pick = QPushButton("面颜色")
        self.btn_face_color_pick.setFixedWidth(64)
        self.btn_face_color_pick.clicked.connect(self._choose_face_color)
        tb.addWidget(self.btn_face_color_pick)
        a_face_color_apply = QAction("应用面颜色", self)
        a_face_color_apply.triggered.connect(self._begin_pick_color)
        tb.addAction(a_face_color_apply)
        a_face_color_clear = QAction("清除所有面颜色", self)
        a_face_color_clear.triggered.connect(self._clear_face_colors)
        tb.addAction(a_face_color_clear)

        self.btn_part_color_pick = QPushButton("零件颜色")
        self.btn_part_color_pick.setFixedWidth(72)
        self.btn_part_color_pick.clicked.connect(self._choose_part_color)
        tb.addWidget(self.btn_part_color_pick)
        a_part_color_apply = QAction("应用零件颜色", self)
        a_part_color_apply.triggered.connect(self._begin_pick_part_color)
        tb.addAction(a_part_color_apply)
        a_part_color_clear = QAction("清除所有零件颜色", self)
        a_part_color_clear.triggered.connect(self._clear_part_colors)
        tb.addAction(a_part_color_clear)
        self._update_color_button_previews()

    def _build_menu(self) -> None:
        mb = self.menuBar()
        m_file = mb.addMenu("文件")
        m_file.addAction("导入 STEP 数模…", self._import_step)
        m_file.addAction("生成测试梁", self._generate_test_beam)
        m_file.addAction("选择材质库文件夹…", self._select_material_dir)
        m_file.addSeparator()
        m_file.addAction("退出", self.close)

        m_view = mb.addMenu("视图")
        m_view.addAction("原始视图", lambda: self._set_display_mode("smooth"))
        self.a_mesh_menu = m_view.addAction("网格视图", lambda: self._set_display_mode("mesh"))
        self.a_mesh_menu.setEnabled(False)
        m_view.addAction("重置视图", self.viewport.reset_camera)
        m_view.addAction("重置布局", self._reset_layout)
        m_view.addAction("清空面板", self._clear_panels)

        m_color = mb.addMenu("颜色设置")
        m_color.addAction("选择面颜色", self._choose_face_color)
        m_color.addAction("应用面颜色", self._begin_pick_color)
        m_color.addAction("清除所有面颜色", self._clear_face_colors)
        m_color.addSeparator()
        m_color.addAction("选择零件颜色", self._choose_part_color)
        m_color.addAction("应用零件颜色", self._begin_pick_part_color)
        m_color.addAction("清除所有零件颜色", self._clear_part_colors)

        m_coord = mb.addMenu("解析坐标系")
        m_coord.addAction("设置解析坐标系", self._edit_coord_system)

        m_help = mb.addMenu("帮助")
        m_help.addAction("关于", self._show_about)
        m_help.addAction("应力值表", self._show_stress_table)

    # ------------------------------------------------------------------ #
    # Workflow: import / generate
    # ------------------------------------------------------------------ #
    def _import_step(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 STEP 文件", "", "STEP 文件 (*.step *.stp);;所有文件 (*)"
        )
        if not path:
            return
        self.statusBar().showMessage(f"正在导入 {os.path.basename(path)} …")
        QApplication.processEvents()
        try:
            parts = load_step(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导入失败", f"无法导入 STEP 文件:\n{exc}")
            self.statusBar().showMessage("导入失败。")
            return
        self._set_parts(parts)
        self.statusBar().showMessage(f"已导入 {len(parts)} 个零件 (待网格化)")

    def _generate_test_beam(self) -> None:
        try:
            part = make_test_beam()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "生成失败", f"无法生成测试梁:\n{exc}")
            self.statusBar().showMessage("测试梁生成失败。")
            return
        self._set_part(part)
        self.statusBar().showMessage("已生成测试梁 (待网格化)")

    def _select_material_dir(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择材质库文件夹", "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if not dir_path:
            return
        self.statusBar().showMessage(f"正在加载材质库: {dir_path} …")
        QApplication.processEvents()
        try:
            materials = load_material_database_from_dir(dir_path)
            if not materials:
                QMessageBox.warning(self, "提示", "该文件夹中未找到有效的材质数据文件。")
                self.statusBar().showMessage("材质库加载失败。")
                return
            self.material_panel.set_materials(materials)
            if self.study.material is not None:
                mat_name = self.study.material.name
                if mat_name not in {m.name for m in materials}:
                    self.study.material = None
                    QMessageBox.warning(
                        self, "提示",
                        f"当前材质 '{mat_name}' 在新材质库中不存在，请重新选择。"
                    )
                    self._refresh_all()
            self.statusBar().showMessage(f"材质库已更新: 共 {len(materials)} 种材质")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "加载失败", f"无法加载材质库:\n{exc}")
            self.statusBar().showMessage("材质库加载失败。")

    def _set_part(self, part: Part) -> None:
        self._set_parts([part])
    
    def _set_parts(self, parts: list[Part]) -> None:
        if not parts:
            return
        base_name = parts[0].name.split("_")[0] if len(parts) > 1 else parts[0].name
        self.study = Study(name=base_name, parts=parts)
        self.setup_panel.set_study(self.study)
        self.material_panel.set_parts([p.name for p in parts])
        
        if all(p.mesh is not None for p in parts):
            first_mesh = parts[0].mesh
            if all(p.mesh is first_mesh for p in parts):
                display_mesh = first_mesh
            else:
                pts_list = []
                tri_list = []
                tri_to_face_list = []
                tri_to_part_list = []
                face_centers_list = []
                face_areas_list = []
                face_normals_list = []
                node_offset = 0
                face_offset = 0
                for part_idx, p in enumerate(parts):
                    mesh = p.mesh
                    pts_list.append(mesh.points)
                    tri_list.append(mesh.surf_tris + node_offset)
                    tri_to_face_list.append(mesh.tri_to_face + face_offset)
                    tri_to_part_list.append(np.full(len(mesh.surf_tris), part_idx, dtype=np.int32))
                    face_centers_list.append(mesh.face_centers)
                    face_areas_list.append(mesh.face_areas)
                    face_normals_list.append(mesh.face_normals)
                    node_offset += mesh.points.shape[0]
                    face_offset += mesh.num_faces

                from .geometry import TetMesh
                display_mesh = TetMesh(
                    points=np.vstack(pts_list),
                    tets=np.zeros((0, 4), dtype=np.int32),
                    surf_tris=np.vstack(tri_list),
                    tri_to_face=np.concatenate(tri_to_face_list),
                    face_centers=np.vstack(face_centers_list) if face_centers_list else np.zeros((0, 3)),
                    face_areas=np.concatenate(face_areas_list) if face_areas_list else np.zeros((0,)),
                    face_normals=np.vstack(face_normals_list) if face_normals_list else np.zeros((0, 3)),
                    tet_to_part=np.zeros((0,), dtype=np.int32),
                    tri_to_part=np.concatenate(tri_to_part_list),
                )
            parts[0].mesh = display_mesh
            self.viewport.set_part(parts[0], show_edges=True, smooth_shading=True)
        
        self.viewport.show_coord_system(
            self.study.coord_system.origin,
            self.study.coord_system.x_axis,
            self.study.coord_system.y_axis,
        )
        self._display_mode = "smooth"
        self._set_mesh_view_enabled(False)
        self._refresh_all()
        self.results_panel.clear_result()
        
        if len(parts) > 1:
            self.viewport.set_auto_part_select(True)
            self.statusBar().showMessage(f"已导入 {len(parts)} 个零件。点击预览框选择零件。")
        else:
            self.viewport.set_auto_part_select(False)

    def _apply_material(self, material: Material) -> None:
        if self.study.parts:
            self.study.parts[self._current_part_idx].material = material
        else:
            self.study.material = material
        self._refresh_all()
        part_name = self.study.parts[self._current_part_idx].name if self.study.parts else ""
        self.statusBar().showMessage(f"已应用材质: {material.name} (零件: {part_name})")
    
    def _select_part(self, idx: int) -> None:
        if 0 <= idx < len(self.study.parts):
            self._current_part_idx = idx
            part = self.study.parts[idx]
            self.viewport.highlight_part(idx, self.study.parts)
            self.material_panel.part_combo.setCurrentIndex(idx)
            self.statusBar().showMessage(f"已选择零件: {part.name}")
            self._refresh_all()
    
    def _on_part_material_clicked(self, part_idx: int) -> None:
        self._select_part(part_idx)
        self.material_panel.setVisible(True)
        self.material_panel.setFocus()
        self.statusBar().showMessage(f"请在材质库中选择材质应用到零件: {self.study.parts[part_idx].name}")


    def _on_solver_backend_changed(self, backend: str) -> None:
        self.study.solver_backend = backend
        backend_name = BACKENDS.get(backend, BACKENDS["internal"]).name
        self.statusBar().showMessage(f"已切换求解器后端: {backend_name}")
    # ------------------------------------------------------------------ #
    # Workflow: picking fixtures / loads
    # ------------------------------------------------------------------ #
    def _begin_pick_fixture(self) -> None:
        if self.study.part is None:
            QMessageBox.warning(self, "提示", "请先导入数模。")
            return
        self._pick_mode = "fixture"
        self.viewport.set_picking_active(True)
        self.statusBar().showMessage("请在 3D 视图中点击面作为固定位置 (可多选，按 ESC 结束) …")

    def _begin_pick_load(self) -> None:
        if self.study.part is None:
            QMessageBox.warning(self, "提示", "请先导入数模。")
            return
        self._pick_mode = "load"
        self.viewport.set_picking_active(True)
        self.statusBar().showMessage("请在 3D 视图中点击一个面作为载荷位置 …")

    def _on_face_picked(self, face_id: int) -> None:
        if self._pick_mode == "fixture":
            if not any(f.face_id == face_id for f in self.study.fixtures):
                self.study.fixtures.append(Fixture(face_id=face_id))
                self._refresh_all()
                self.statusBar().showMessage(f"已添加固定面 #{face_id}。继续选择或按 ESC 结束 …")
            else:
                self.statusBar().showMessage(f"面 #{face_id} 已被选中。继续选择或按 ESC 结束 …")
        elif self._pick_mode == "load":
            dlg = _LoadDialog(self)
            if dlg.exec() != QDialog.Accepted:
                self.viewport.set_picking_active(False)
                self._pick_mode = "none"
                return
            val = dlg.value()
            idx = len(self.study.loads) + 1
            if dlg.is_normal():
                self.study.loads.append(
                    PressureLoad(face_id=face_id, force=val, name=f"载荷 #{idx}")
                )
                self.statusBar().showMessage(f"已添加法向载荷: 面 {face_id}, {val:.2f} N。")
            else:
                self.study.loads.append(
                    ForceLoad(face_id=face_id, force=val, direction=dlg.direction(),
                              name=f"载荷 #{idx}")
                )
                self.statusBar().showMessage(f"已添加定向载荷: 面 {face_id}, {val:.2f} N。")
            self.viewport.set_picking_active(False)
            self._pick_mode = "none"
            self._refresh_all()
        elif self._pick_mode == "color":
            self.viewport.apply_face_color(face_id, self._face_color)
            self.viewport.set_picking_active(False)
            self._pick_mode = "none"
            self.statusBar().showMessage(f"已为面 #{face_id} 上色。")

        elif self._pick_mode == "edit_fixture":
            idx = self._edit_fixture_idx
            if 0 <= idx < len(self.study.fixtures):
                self.study.fixtures[idx] = Fixture(face_id=face_id)
            self.viewport.set_picking_active(False)
            self._pick_mode = "none"
            self._edit_fixture_idx = -1
            self._refresh_all()
            self.statusBar().showMessage("固定位置已更新")
        elif self._pick_mode == "edit_load":
            idx = self._edit_load_idx
            pending = self._pending_edit_load
            if 0 <= idx < len(self.study.loads) and pending is not None:
                old_ld = self.study.loads[idx]
                if pending["is_normal"]:
                    self.study.loads[idx] = PressureLoad(face_id=face_id, force=pending["force"], name=old_ld.name)
                else:
                    self.study.loads[idx] = ForceLoad(
                        face_id=face_id, force=pending["force"], direction=pending["direction"], name=old_ld.name
                    )
            self.viewport.set_picking_active(False)
            self._pick_mode = "none"
            self._edit_load_idx = -1
            self._pending_edit_load = None
            self._refresh_all()
            self.statusBar().showMessage("载荷位置和大小已更新")

    def _begin_pick_color(self) -> None:
        if self.study.part is None:
            QMessageBox.warning(self, "提示", "请先导入数模。")
            return
        self._pick_mode = "color"
        self.viewport.set_picking_active(True)
        self.viewport.set_probe_mode(False)
        self.viewport.set_part_picking_mode(False)
        r, g, b = self._face_color
        self.statusBar().showMessage(f"请在 3D 视图中点击一个面进行上色 (颜色: R={int(r*255)} G={int(g*255)} B={int(b*255)}) …")
    
    def _clear_all_colors(self) -> None:
        self.viewport.clear_all_colors()
        self.statusBar().showMessage("已取消所有上色。")
    
    def _begin_pick_part_color(self) -> None:
        if not self.study.parts:
            QMessageBox.warning(self, "提示", "请先导入数模。")
            return
        if len(self.study.parts) <= 1:
            self.viewport.apply_part_color(0, self._part_color)
            r, g, b = self._part_color
            self.statusBar().showMessage(f"已为零件上色 (颜色: R={int(r*255)} G={int(g*255)} B={int(b*255)})。")
            return
        self._pick_mode = "part_color"
        self.viewport.set_part_picking_mode(True)
        self.viewport.set_picking_active(False)
        self.viewport.set_probe_mode(False)
        r, g, b = self._part_color
        self.statusBar().showMessage(f"请在 3D 视图中点击零件进行上色 (颜色: R={int(r*255)} G={int(g*255)} B={int(b*255)}) …")
    
    def _begin_pick_part(self) -> None:
        if not self.study.parts or len(self.study.parts) <= 1:
            QMessageBox.information(self, "提示", "当前只有一个零件，无需选择。")
            return
        self._pick_mode = "part"
        self.viewport.set_part_picking_mode(True)
        self.viewport.set_picking_active(False)
        self.viewport.set_probe_mode(False)
        self.statusBar().showMessage("请在 3D 视图中点击选择零件 …")
    
    def _on_part_picked(self, part_idx: int) -> None:
        if self._pick_mode == "part":
            self._select_part(part_idx)
            self.viewport.set_part_picking_mode(False)
            self._pick_mode = "none"
        elif self._pick_mode == "part_color":
            self.viewport.apply_part_color(part_idx, self._part_color)
            self.viewport.set_part_picking_mode(False)
            self._pick_mode = "none"
            self.statusBar().showMessage(f"已为零件 {part_idx+1} 上色。")
    
    def _toggle_probe_mode(self) -> None:
        if self.study.result is None:
            QMessageBox.information(self, "提示", "请先运行仿真。")
            return
        self._pick_mode = "probe" if self._pick_mode != "probe" else "none"
        if self._pick_mode == "probe":
            self.viewport.set_result(self.study.result)
        self.viewport.set_probe_mode(self._pick_mode == "probe")
        self.viewport.set_picking_active(self._pick_mode != "probe")
        if self._pick_mode == "probe":
            self.statusBar().showMessage("探测模式: 请在 3D 视图中点击查看位移和应力数值 …")
        else:
            self.viewport.clear_probe_markers()
            self.statusBar().showMessage("已退出探测模式。")
    
    def _on_probe_data(self, data: dict) -> None:
        msg = (
            f"节点 #{data['point_id']}\n"
            f"坐标: ({data['coords'][0]:.3f}, {data['coords'][1]:.3f}, {data['coords'][2]:.3f})\n"
            f"位移 UX: {data['ux']:.6f} mm\n"
            f"位移 UY: {data['uy']:.6f} mm\n"
            f"位移 UZ: {data['uz']:.6f} mm\n"
            f"合成位移: {data['disp_magnitude']:.6f} mm\n"
            f"von Mises 应力: {data['von_mises']:.4f} MPa"
        )
        self.statusBar().showMessage(
            f"UX={data['ux']:.4f} UY={data['uy']:.4f} UZ={data['uz']:.4f} "
            f"| 应力={data['von_mises']:.2f} MPa"
        )


    # ------------------------------------------------------------------ #
    # Probe modes
    # ------------------------------------------------------------------ #
    def _begin_probe_disp(self) -> None:
        if self.study.result is None:
            QMessageBox.information(self, "提示", "请先运行仿真。")
            return
        self._pick_mode = "probe"
        self.viewport.set_result(self.study.result)
        self.viewport.set_displacement_probe_mode(True)
        self.viewport.set_picking_active(False)
        self.statusBar().showMessage("位移探测模式: 点击3D视图查看位移值")

    def _begin_probe_stress(self) -> None:
        if self.study.result is None:
            QMessageBox.information(self, "提示", "请先运行仿真。")
            return
        self._pick_mode = "probe"
        self.viewport.set_result(self.study.result)
        self.viewport.set_stress_probe_mode(True)
        self.viewport.set_picking_active(False)
        self.statusBar().showMessage("应力探测模式: 点击3D视图查看应力值")

    # ------------------------------------------------------------------ #
    # Edit fixtures / loads via viewport re-picking
    # ------------------------------------------------------------------ #
    def _edit_coord_system(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("设置解析坐标系")
        form = QFormLayout(dlg)

        def spin(value: float, min_value: float, max_value: float, decimals: int) -> QDoubleSpinBox:
            sb = QDoubleSpinBox()
            sb.setRange(min_value, max_value)
            sb.setDecimals(decimals)
            sb.setValue(float(value))
            return sb

        cs = self.study.coord_system
        ox = spin(cs.origin[0], -1e6, 1e6, 3)
        oy = spin(cs.origin[1], -1e6, 1e6, 3)
        oz = spin(cs.origin[2], -1e6, 1e6, 3)
        xx = spin(cs.x_axis[0], -1, 1, 4)
        xy = spin(cs.x_axis[1], -1, 1, 4)
        xz = spin(cs.x_axis[2], -1, 1, 4)
        yx = spin(cs.y_axis[0], -1, 1, 4)
        yy = spin(cs.y_axis[1], -1, 1, 4)
        yz = spin(cs.y_axis[2], -1, 1, 4)

        form.addRow("原点 X / Y / Z:", StudySetupPanel._row(ox, oy, oz))
        form.addRow("X轴:", StudySetupPanel._row(xx, xy, xz))
        form.addRow("Y轴:", StudySetupPanel._row(yx, yy, yz))
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() != QDialog.Accepted:
            return

        self.study.coord_system = CoordSystem(
            origin=np.array([ox.value(), oy.value(), oz.value()]),
            x_axis=np.array([xx.value(), xy.value(), xz.value()]),
            y_axis=np.array([yx.value(), yy.value(), yz.value()]),
        )
        self._on_coord_changed()

    def _on_edit_fixture(self, idx: int) -> None:
        if self.study.part is None:
            return
        self._pick_mode = "edit_fixture"
        self._edit_fixture_idx = idx
        self.viewport.set_picking_active(True)
        self.statusBar().showMessage(f"编辑固定位置 #{idx+1}: 在3D视图中点击新面")

    def _on_edit_load(self, idx: int) -> None:
        if self.study.part is None:
            return
        if idx < 0 or idx >= len(self.study.loads):
            return
        old_load = self.study.loads[idx]
        dlg = _LoadDialog(self, old_load)
        if dlg.exec() != QDialog.Accepted:
            return
        self._pending_edit_load = {
            "force": dlg.value(),
            "is_normal": dlg.is_normal(),
            "direction": dlg.direction(),
        }
        self._pick_mode = "edit_load"
        self._edit_load_idx = idx
        self.viewport.set_picking_active(True)
        self.statusBar().showMessage(f"编辑载荷 #{idx+1}: 在3D视图中点击新面")

    # ------------------------------------------------------------------ #
    # Color helpers
    # ------------------------------------------------------------------ #
    def _update_color_button_previews(self) -> None:
        face_r, face_g, face_b = self._face_color
        part_r, part_g, part_b = self._part_color
        self.btn_face_color_pick.setStyleSheet(
            f"background-color: rgb({int(face_r * 255)}, {int(face_g * 255)}, {int(face_b * 255)});"
        )
        self.btn_part_color_pick.setStyleSheet(
            f"background-color: rgb({int(part_r * 255)}, {int(part_g * 255)}, {int(part_b * 255)});"
        )

    def _choose_face_color(self) -> None:
        from PySide6.QtWidgets import QColorDialog
        from PySide6.QtGui import QColor
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            self._face_color = (color.redF(), color.greenF(), color.blueF())
            self._update_color_button_previews()

    def _choose_part_color(self) -> None:
        from PySide6.QtWidgets import QColorDialog
        from PySide6.QtGui import QColor
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            self._part_color = (color.redF(), color.greenF(), color.blueF())
            self._update_color_button_previews()

    def _clear_face_colors(self) -> None:
        self.viewport.clear_face_colors()
        self.statusBar().showMessage("已取消面上色。")

    def _clear_part_colors(self) -> None:
        self.viewport.clear_part_colors()
        self.statusBar().showMessage("已取消零件上色。")


    def _remove_fixture(self, idx: int) -> None:
        if 0 <= idx < len(self.study.fixtures):
            self.study.fixtures.pop(idx)
            self._refresh_all()

    def _remove_load(self, idx: int) -> None:
        if 0 <= idx < len(self.study.loads):
            self.study.loads.pop(idx)
            self._refresh_all()

    def _on_coord_changed(self) -> None:
        self.viewport.show_coord_system(
            self.study.coord_system.origin,
            self.study.coord_system.x_axis,
            self.study.coord_system.y_axis,
        )

    # ------------------------------------------------------------------ #
    # Workflow: mesh
    # ------------------------------------------------------------------ #
    def _do_mesh(self) -> None:
        if not self.study.parts:
            QMessageBox.warning(self, "提示", "请先导入数模。")
            return
        self.statusBar().showMessage(f"正在网格化 (单元尺寸: {self.study.mesh_size:.1f} mm) …")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            combined_mesh = mesh_part(self.study.parts, self.study.mesh_size)
            for p in self.study.parts:
                p.mesh = combined_mesh
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "网格化失败", f"无法生成网格:\n{exc}")
            self.statusBar().showMessage("网格化失败。")
            QApplication.restoreOverrideCursor()
            return
        QApplication.restoreOverrideCursor()
        self.viewport.set_part(self.study.parts[0], show_edges=True)
        self._set_display_mode("mesh")
        self._set_mesh_view_enabled(True)
        self.statusBar().showMessage(
            f"网格化完成: 节点 {combined_mesh.num_nodes} / 单元 {combined_mesh.num_tets} / "
            f"零件数 {len(self.study.parts)}"
        )

    def _set_mesh_view_enabled(self, enabled: bool) -> None:
        self.a_mesh.setEnabled(enabled)
        self.a_mesh_menu.setEnabled(enabled)

    # ------------------------------------------------------------------ #
    # Workflow: run simulation
    # ------------------------------------------------------------------ #
    def _run_simulation(self) -> None:
        if self.study.part is None or self.study.part.mesh is None or self.study.part.mesh.num_tets == 0:
            QMessageBox.warning(self, "提示", "请先点击网格化按钮生成网格。")
            return
        issues = self.study.ready_report()
        if issues:
            QMessageBox.warning(self, "无法运行", "缺少:\n" + "\n".join(issues))
            return
        self.study.clear_result()
        self.statusBar().showMessage("正在运行仿真 …")
        self.setup_panel.simulation_log.clear()
        self._solve_thread = QThread()
        self._solve_worker = _SolveWorker(self.study)
        self._solve_worker.moveToThread(self._solve_thread)
        self._solve_thread.started.connect(self._solve_worker.run)
        self._solve_worker.progress.connect(
            lambda s: self.statusBar().showMessage(s)
        )
        self._solve_worker.log_message.connect(
            lambda s: self.setup_panel.simulation_log.append(s)
        )
        self._solve_worker.finished.connect(self._on_solved)
        self._solve_worker.finished.connect(self._solve_thread.quit)
        self._solve_thread.start()

    def _on_solved(self, result_or_exc) -> None:
        if isinstance(result_or_exc, Exception):
            QMessageBox.critical(self, "仿真失败", str(result_or_exc))
            self.statusBar().showMessage("仿真失败。")
            return
        result: FEAResult = result_or_exc
        self.study.result = result
        self.viewport.set_part(self.study.parts[0], show_edges=True)
        self._refresh_all()
        
        material_names = [p.material.name if p.material else "未定义" for p in self.study.parts]
        mat_name = ", ".join(material_names) if len(material_names) > 1 else (material_names[0] if material_names else "未定义")
        min_sigyld = min(p.material.sigyld for p in self.study.parts if p.material and p.material.sigyld > 0) if self.study.parts else 0
        
        self.results_panel.show_result(
            result,
            material_name=mat_name,
            yield_mpa=min_sigyld / 1e6 if min_sigyld > 0 else 0,
        )
        self._set_display_mode("disp")
        self.statusBar().showMessage(
            f"仿真完成: 最大位移 {result.max_displacement*1000:.6f} mm, "
            f"最大应力 {result.max_von_mises/1e6:.4f} MPa, "
            f"安全系数 {result.safety_factor:.3f}"
        )

    # ------------------------------------------------------------------ #
    # Display mode
    # ------------------------------------------------------------------ #
    def _set_view_title(self, title: str) -> None:
        self.setWindowTitle(title)
        self.viewport.set_view_title(title)

    def _set_display_mode(self, mode: str) -> None:
        if self.study.part is None:
            return
        self._display_mode = mode
        if mode == "smooth":
            self.viewport.show_smooth_mode()
            self._set_view_title("原始视图")
            self._refresh_highlights()
        elif mode == "mesh":
            self.viewport.show_mesh_mode()
            self._set_view_title("网格视图")
            self._refresh_highlights()
        elif mode in {"disp", "disp_x", "disp_y", "disp_z"}:
            if self.study.result is None:
                QMessageBox.information(self, "提示", "请先运行仿真。")
                return
            title = "位移 ISO 图"
            self.setWindowTitle(title)
            component = {
                "disp": "magnitude",
                "disp_x": "x",
                "disp_y": "y",
                "disp_z": "z",
            }[mode]
            self.viewport.show_displacement(
                self.study.result, deformed=False, component=component, title=title
            )
            if mode == "disp":
                max_xyz = np.max(np.abs(self.study.result.displacements), axis=0) * 1000.0
                self.statusBar().showMessage(
                    f"位移 ISO: UX={max_xyz[0]:.6f} mm, UY={max_xyz[1]:.6f} mm, UZ={max_xyz[2]:.6f} mm；探测模式可查看点位移"
                )
        elif mode == "stress":
            if self.study.result is None:
                QMessageBox.information(self, "提示", "请先运行仿真。")
                return
            title = "应力 ISO 图"
            self.setWindowTitle(title)
            self.viewport.show_stress(self.study.result, deformed=False, title=title)
        if self._pick_mode == "probe" and self.study.result is not None:
            self.viewport.set_result(self.study.result)

    # ------------------------------------------------------------------ #
    # Refresh helpers
    # ------------------------------------------------------------------ #
    def _refresh_all(self) -> None:
        self.setup_panel.refresh_part()
        self.setup_panel.refresh_fixtures()
        self.setup_panel.refresh_loads()
        self._refresh_highlights()
        self._update_ready_state()

    def _refresh_highlights(self) -> None:
        if self.study.part is None:
            return
        self.viewport.highlight_fixtures([f.face_id for f in self.study.fixtures])
        self.viewport.highlight_loads(self.study.loads)
        if self.viewport._selected_face_id is not None:
            self.viewport.highlight_selected_face(self.viewport._selected_face_id)

    def _update_ready_state(self) -> None:
        issues = self.study.ready_report()
        self.setup_panel.update_ready_state(self.study.is_ready(), issues)

    def _reset_layout(self) -> None:
        self.material_panel.setVisible(True)
        self.results_panel.setVisible(True)
        self.setup_panel.setVisible(True)
        
        if self._initial_dock_state is not None:
            self.restoreState(self._initial_dock_state)
        self.resize(1400, 900)
        self.statusBar().showMessage("布局已恢复初始设置。")

    def _clear_panels(self) -> None:
        self.study.clear_setup()
        self.setup_panel.clear_setup()
        self.results_panel.clear_result()
        self._refresh_highlights()
        self._update_ready_state()
        if self.study.part is not None:
            self._set_display_mode("smooth")
        self.statusBar().showMessage("面板已清空。")

    def _show_about(self) -> None:
        from . import __version__, __author__, __license__
        QMessageBox.about(
            self, "关于",
            f"<b>obara-3d-parser</b><br><br>"
            f"版本: {__version__}<br>"
            f"作者: {__author__}<br>"
            f"协议: {__license__}<br><br>"
            f"简易版 SolidWorks 静态仿真程序。<br>"
            f"线性弹性有限元 (四面体) + gmsh 网格 + VTK 可视化。<br><br>"
            f"支持 STEP 数模导入、材质定义、固定/加压位置、解析坐标系、"
            f"位移与 von Mises 应力 ISO 图。",
        )

    def _show_stress_table(self) -> None:
        stress_data = [
            ["CRCU", "", "1.00E+06", "161.1", "50.00%", "117.44", "163.40"],
            ["BECU-50", "", "1.00E+06", "183.21", "50.00%", "133.56", "218.18"],
            ["BECU-20", "", "1.00E+06", "229.44", "50.00%", "167.37", "263.37"],
            ["BECU-25", "是", "1.00E+06", "94.18", "99.90%", "38.33", "116.78"],
            ["BECU-20C", "是", "1.00E+06", "84.48", "50.00%", "45.79", "45.79"],
            ["AC4C-T6", "是", "1.00E+07", "73.33", "50.00%", "39.74", "39.74"],
            ["AC7A", "是", "1.00E+07", "63.01", "99.90%", "34.53", "34.53"],
            ["A5052", "是", "1.00E+07", "172.15", "99.90%", "70.07", "70.07"],
            ["A7075-T6", "", "1.00E+07", "189.51", "99.90%", "103.85", "103.85"],
            ["A6061-T65", "", "1.00E+07", "100.29", "99.90%", "54.96", "54.96"],
            ["SS400", "", "1.00E+07", "107.89", "99.90%", "59.12", "59.12"],
            ["S45C", "", "1.00E+07", "190.5", "99.90%", "104.39", "104.39"],
            ["SCM435", "", "1.00E+07", "161.8", "99.90%", "88.67", "88.67"],
            ["S55C", "", "1.00E+07", "186.36", "99.90%", "102.13", "102.13"],
        ]
        
        rows_html = ""
        for row in stress_data:
            rows_html += "<tr>"
            for col in row:
                rows_html += f"<td>{col}</td>"
            rows_html += "</tr>"
        
        html = (
            "<style>"
            "table{border-collapse:collapse;}"
            "th, td{border:1px solid #000;padding:4px 8px;font-size:11px;}"
            "th{background:#ccc;font-weight:bold;}"
            "</style>"
            "<table>"
            "<tr>"
            "<th>材质</th>"
            "<th>是否铸件/焊接件</th>"
            "<th>打点数</th>"
            "<th>1000万点50%疲劳强度(MPa)</th>"
            "<th>信耐度</th>"
            "<th>1000万点容许应力</th>"
            "<th>对应点的容许应力(MPa)</th>"
            "</tr>"
            f"{rows_html}"
            "</table>"
        )
        
        dlg = QDialog(self)
        dlg.setWindowTitle("应力值表")
        dlg.resize(600, 450)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(10, 10, 10, 10)
        from PySide6.QtWidgets import QTextBrowser
        browser = QTextBrowser()
        browser.setHtml(html)
        layout.addWidget(browser)
        btn_close = QPushButton("关闭", dlg)
        btn_close.clicked.connect(dlg.accept)
        layout.addWidget(btn_close)
        dlg.exec()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape and self._pick_mode != "none":
            if self._pick_mode == "probe":
                self.viewport.clear_probe_markers()
            self.viewport.set_picking_active(False)
            self._pick_mode = "none"
            self.statusBar().showMessage("已取消拾取。")
        else:
            super().keyPressEvent(event)


