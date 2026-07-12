"""Main application window.

Wires the viewport, material library, study-setup and results panels into a
single SolidWorks-Simulation-like workflow:

  import STEP → assign material → pick fixed faces → pick loaded faces +
  pressure → define CS → run → view ISO displacement / stress.
"""
from __future__ import annotations

import os
import sys
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QObject, QThread, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QFileDialog,
    QStatusBar, QMessageBox, QInputDialog, QDialog, QFormLayout, QDoubleSpinBox,
    QDialogButtonBox, QLabel, QApplication,
)

from .material_db import load_material_database, load_material_database_from_dir, Material
from .geometry import load_step, make_test_beam, Part
from .fea import solve_static, CoordSystem, Fixture, PressureLoad, FEAResult
from .study import Study
from .viewport import Viewport
from .panels import MaterialPanel, StudySetupPanel, ResultsPanel


# --------------------------------------------------------------------------- #
# Background solver worker
# --------------------------------------------------------------------------- #
class _SolveWorker(QObject):
    progress = Signal(str)
    finished = Signal(object)   # FEAResult or Exception

    def __init__(self, study: Study):
        super().__init__()
        self.study = study

    def run(self) -> None:
        try:
            result = solve_static(
                self.study.part,
                self.study.material,
                self.study.fixtures,
                self.study.loads,
                self.study.coord_system,
                progress=lambda s: self.progress.emit(s),
            )
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(exc)


# --------------------------------------------------------------------------- #
# Small dialog for entering pressure value
# --------------------------------------------------------------------------- #
class _PressureDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("输入压力")
        form = QFormLayout(self)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(-1e9, 1e9)
        self.spin.setDecimals(4)
        self.spin.setValue(1.0)
        self.unit = QDoubleSpinBox()
        self.unit.setRange(1, 2)
        self.unit.setValue(0)  # 0 = MPa, handled separately
        form.addRow("压力 (MPa):", self.spin)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def pressure_pa(self) -> float:
        return float(self.spin.value()) * 1e6


class _BeamDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("生成测试梁")
        form = QFormLayout(self)
        self.length = QDoubleSpinBox(); self.length.setRange(1, 1e4); self.length.setValue(100.0)
        self.width = QDoubleSpinBox(); self.width.setRange(1, 1e4); self.width.setValue(20.0)
        self.height = QDoubleSpinBox(); self.height.setRange(1, 1e4); self.height.setValue(10.0)
        self.mesh = QDoubleSpinBox(); self.mesh.setRange(1, 1e3); self.mesh.setValue(6.0)
        form.addRow("长度 (mm):", self.length)
        form.addRow("宽度 (mm):", self.width)
        form.addRow("高度 (mm):", self.height)
        form.addRow("网格尺寸 (mm):", self.mesh)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)


# --------------------------------------------------------------------------- #
# Main window
# --------------------------------------------------------------------------- #
class MainWindow(QMainWindow):
    def __init__(self, material_db_path: str):
        super().__init__()
        self.setWindowTitle("obara-3d-parser - 简易版 SolidWorks 仿真")
        self.resize(1400, 900)

        self.study = Study()
        self._materials = load_material_database(material_db_path)
        self._pick_mode = "none"          # "none" | "fixture" | "load"
        self._solve_thread: Optional[QThread] = None
        self._solve_worker: Optional[_SolveWorker] = None
        self._display_mode = "mesh"       # "mesh" | "disp" | "stress"

        self._build_ui()
        self._refresh_all()
        self.statusBar().showMessage("就绪。请导入 STEP 数模或生成测试零件。")

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        # central viewport
        self.viewport = Viewport(self)
        self.setCentralWidget(self.viewport)
        self.viewport.face_picked.connect(self._on_face_picked)

        # dock panels
        self.material_panel = MaterialPanel(self._materials, self)
        self.material_panel.apply_material.connect(self._apply_material)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.material_panel)

        self.setup_panel = StudySetupPanel(self)
        self.setup_panel.set_study(self.study)
        self.setup_panel.add_fixture_clicked.connect(self._begin_pick_fixture)
        self.setup_panel.add_load_clicked.connect(self._begin_pick_load)
        self.setup_panel.remove_fixture.connect(self._remove_fixture)
        self.setup_panel.remove_load.connect(self._remove_load)
        self.setup_panel.run_clicked.connect(self._run_simulation)
        self.setup_panel.coord_changed.connect(self._on_coord_changed)
        self.setup_panel.btn_add_fix.clicked.connect(self._begin_pick_fixture)
        self.setup_panel.btn_add_load.clicked.connect(self._begin_pick_load)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.setup_panel)

        self.results_panel = ResultsPanel(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.results_panel)

        self._build_toolbar()
        self._build_menu()

    def _build_toolbar(self) -> None:
        tb = QToolBar("主工具栏")
        tb.setMovable(False)
        self.addToolBar(tb)

        a_import = QAction("导入 STEP", self)
        a_import.triggered.connect(self._import_step)
        tb.addAction(a_import)

        a_beam = QAction("生成测试梁", self)
        a_beam.triggered.connect(self._generate_beam)
        tb.addAction(a_beam)

        tb.addSeparator()

        a_mesh = QAction("网格视图", self)
        a_mesh.triggered.connect(lambda: self._set_display_mode("mesh"))
        tb.addAction(a_mesh)

        a_disp = QAction("位移 ISO", self)
        a_disp.triggered.connect(lambda: self._set_display_mode("disp"))
        tb.addAction(a_disp)

        a_stress = QAction("应力 ISO", self)
        a_stress.triggered.connect(lambda: self._set_display_mode("stress"))
        tb.addAction(a_stress)

        tb.addSeparator()

        a_run = QAction("▶ 运行仿真", self)
        a_run.triggered.connect(self._run_simulation)
        tb.addAction(a_run)

        a_reset = QAction("重置视图", self)
        a_reset.triggered.connect(self.viewport.reset_camera)
        tb.addAction(a_reset)

    def _build_menu(self) -> None:
        mb = self.menuBar()
        m_file = mb.addMenu("文件")
        m_file.addAction("导入 STEP 数模…", self._import_step)
        m_file.addAction("生成测试梁…", self._generate_beam)
        m_file.addSeparator()
        m_file.addAction("选择材质库文件夹…", self._select_material_dir)
        m_file.addSeparator()
        m_file.addAction("退出", self.close)

        m_view = mb.addMenu("视图")
        m_view.addAction("网格视图", lambda: self._set_display_mode("mesh"))
        m_view.addAction("位移 ISO 图", lambda: self._set_display_mode("disp"))
        m_view.addAction("应力 ISO 图", lambda: self._set_display_mode("stress"))
        m_view.addAction("重置视图", self.viewport.reset_camera)

        m_help = mb.addMenu("帮助")
        m_help.addAction("关于", self._show_about)

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
            part = load_step(path, mesh_size=5.0)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导入失败", f"无法导入 STEP 文件:\n{exc}")
            self.statusBar().showMessage("导入失败。")
            return
        self._set_part(part)
        self.statusBar().showMessage(
            f"已导入 {part.name}: 节点 {part.mesh.num_nodes}, "
            f"单元 {part.mesh.num_tets}, 面 {part.mesh.num_faces}"
        )

    def _generate_beam(self) -> None:
        dlg = _BeamDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        self.statusBar().showMessage("正在生成测试梁网格 …")
        QApplication.processEvents()
        try:
            part = make_test_beam(
                dlg.length.value(), dlg.width.value(), dlg.height.value(),
                dlg.mesh.value(),
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "生成失败", f"无法生成测试梁:\n{exc}")
            return
        self._set_part(part)
        self.statusBar().showMessage(
            f"已生成测试梁: 节点 {part.mesh.num_nodes}, 单元 {part.mesh.num_tets}, "
            f"面 {part.mesh.num_faces}"
        )

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
        self.study = Study(name=part.name, part=part)
        self.setup_panel.set_study(self.study)
        self.viewport.set_part(part)
        self.viewport.show_coord_system(
            self.study.coord_system.origin,
            self.study.coord_system.x_axis,
            self.study.coord_system.y_axis,
        )
        self._display_mode = "mesh"
        self._refresh_all()
        self.results_panel.clear_result()

    def _apply_material(self, material: Material) -> None:
        self.study.material = material
        self._refresh_all()
        self.statusBar().showMessage(f"已应用材质: {material.name}")

    # ------------------------------------------------------------------ #
    # Workflow: picking fixtures / loads
    # ------------------------------------------------------------------ #
    def _begin_pick_fixture(self) -> None:
        if self.study.part is None:
            QMessageBox.warning(self, "提示", "请先导入数模。")
            return
        self._pick_mode = "fixture"
        self.viewport.set_picking_active(True)
        self.statusBar().showMessage("请在 3D 视图中点击一个面作为固定位置 …")

    def _begin_pick_load(self) -> None:
        if self.study.part is None:
            QMessageBox.warning(self, "提示", "请先导入数模。")
            return
        self._pick_mode = "load"
        self.viewport.set_picking_active(True)
        self.statusBar().showMessage("请在 3D 视图中点击一个面作为加压位置 …")

    def _on_face_picked(self, face_id: int) -> None:
        if self._pick_mode == "fixture":
            # avoid duplicates
            if not any(f.face_id == face_id for f in self.study.fixtures):
                self.study.fixtures.append(Fixture(face_id=face_id))
            self.viewport.set_picking_active(False)
            self._pick_mode = "none"
            self._refresh_all()
            self.statusBar().showMessage(f"已添加固定面 #{face_id}。")
        elif self._pick_mode == "load":
            dlg = _PressureDialog(self)
            if dlg.exec() != QDialog.Accepted:
                self.viewport.set_picking_active(False)
                self._pick_mode = "none"
                return
            p = dlg.pressure_pa()
            idx = len([l for l in self.study.loads if hasattr(l, "pressure")]) + 1
            self.study.loads.append(
                PressureLoad(face_id=face_id, pressure=p, name=f"加压面 #{idx}")
            )
            self.viewport.set_picking_active(False)
            self._pick_mode = "none"
            self._refresh_all()
            self.statusBar().showMessage(
                f"已添加压力载荷: 面 {face_id}, {p/1e6:.4f} MPa。"
            )

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
    # Workflow: run simulation
    # ------------------------------------------------------------------ #
    def _run_simulation(self) -> None:
        issues = self.study.ready_report()
        if issues:
            QMessageBox.warning(self, "无法运行", "缺少:\n" + "\n".join(issues))
            return
        self.study.clear_result()
        self.statusBar().showMessage("正在运行仿真 …")
        self._solve_thread = QThread()
        self._solve_worker = _SolveWorker(self.study)
        self._solve_worker.moveToThread(self._solve_thread)
        self._solve_thread.started.connect(self._solve_worker.run)
        self._solve_worker.progress.connect(
            lambda s: self.statusBar().showMessage(s)
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
        self.results_panel.show_result(
            result,
            material_name=self.study.material.name,
            yield_mpa=self.study.material.sigyld / 1e6,
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
    def _set_display_mode(self, mode: str) -> None:
        if self.study.part is None:
            return
        self._display_mode = mode
        if mode == "mesh":
            self.viewport.show_mesh_mode()
            self._refresh_highlights()
        elif mode == "disp":
            if self.study.result is None:
                QMessageBox.information(self, "提示", "请先运行仿真。")
                return
            self.viewport.show_displacement(self.study.result, deformed=False)
        elif mode == "stress":
            if self.study.result is None:
                QMessageBox.information(self, "提示", "请先运行仿真。")
                return
            self.viewport.show_stress(self.study.result, deformed=False)

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
        self.viewport.highlight_loads([l.face_id for l in self.study.loads])

    def _update_ready_state(self) -> None:
        issues = self.study.ready_report()
        self.setup_panel.update_ready_state(self.study.is_ready(), issues)

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

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape and self._pick_mode != "none":
            self.viewport.set_picking_active(False)
            self._pick_mode = "none"
            self.statusBar().showMessage("已取消拾取。")
        else:
            super().keyPressEvent(event)
