"""Dockable side panels.

  * MaterialPanel       - material library tree + property preview.
  * StudySetupPanel     - part info, fixtures, loads, coordinate system.
  * ResultsPanel        - summary + per-face displacement report.

Panels emit signals that the main window wires up; the main window pushes
state back via the ``refresh_*`` methods.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDockWidget, QTreeWidget, QTreeWidgetItem, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QPushButton, QDoubleSpinBox, QLineEdit, QGroupBox,
    QListWidget, QListWidgetItem, QTabWidget, QTextEdit, QComboBox, QCheckBox,
    QHeaderView, QMessageBox, QInputDialog, QSplitter, QFrame, QSlider,
)
from typing import List, Optional

from .material_db import Material, group_by_classification
from .study import Study
from .fea import CoordSystem, FEAResult


# --------------------------------------------------------------------------- #
# Material library panel
# --------------------------------------------------------------------------- #
class MaterialPanel(QDockWidget):
    apply_material = Signal(object)   # Material
    part_selected = Signal(int)       # part index

    def __init__(self, materials: List[Material], parent=None):
        super().__init__("材质库", parent)
        self._materials = materials
        self._by_name = {m.name: m for m in materials}
        self._current: Optional[Material] = None
        self._parts: List[str] = []
        self._current_part_idx = 0

        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(6, 6, 6, 6)

        gb_part = QGroupBox("选择零件")
        h_part = QHBoxLayout(gb_part)
        self.part_combo = QComboBox()
        self.part_combo.currentIndexChanged.connect(self._on_part_changed)
        h_part.addWidget(self.part_combo)
        v.addWidget(gb_part)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["材质 / 分类"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.itemClicked.connect(self._on_item_clicked)
        v.addWidget(self.tree)

        self.info = QTextEdit()
        self.info.setReadOnly(True)
        self.info.setMaximumHeight(180)
        v.addWidget(self.info)

        self.apply_btn = QPushButton("应用材质到零件")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._emit_apply)
        v.addWidget(self.apply_btn)

        self.setWidget(container)
        self._populate()
    
    def set_parts(self, parts: List[str]) -> None:
        self._parts = parts
        self.part_combo.clear()
        for i, name in enumerate(parts):
            self.part_combo.addItem(f"零件 {i+1}: {name}")
        self._current_part_idx = 0
    
    def _on_part_changed(self, idx: int) -> None:
        self._current_part_idx = idx
        self.part_selected.emit(idx)

    def _populate(self) -> None:
        self.tree.clear()
        for cls_name, mats in group_by_classification(self._materials).items():
            top = QTreeWidgetItem([f"{cls_name}  ({len(mats)})"])
            top.setData(0, Qt.UserRole, None)
            for m in mats:
                child = QTreeWidgetItem([m.name])
                child.setData(0, Qt.UserRole, m.name)
                top.addChild(child)
            self.tree.addTopLevelItem(top)

    def _on_item_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        name = item.data(0, Qt.UserRole)
        if name is None:
            return
        m = self._by_name.get(name)
        if m is None:
            return
        self._current = m
        self.info.setHtml(self._material_html(m))
        self.apply_btn.setEnabled(True)

    @staticmethod
    def _material_html(m: Material) -> str:
        def row(k, v, unit=""):
            return f"<tr><td>{k}</td><td>{v}{unit}</td></tr>"
        rows = "".join([
            row("分类", m.classification),
            row("弹性模量 EX", f"{m.ex/1e9:.3f}", " GPa"),
            row("泊松比 NUXY", f"{m.nuxy:.4f}"),
            row("抗剪模量 GXY", f"{m.gxy/1e9:.3f}", " GPa"),
            row("密度 DENS", f"{m.dens:.1f}", " kg/m³"),
            row("屈服强度 SIGYLD", f"{m.sigyld/1e6:.3f}", " MPa"),
            row("抗拉强度 SIGXT", f"{m.sigxt/1e6:.3f}", " MPa"),
        ])
        return f"<b>{m.name}</b><table style='font-size:11px'>{rows}</table>"

    def _emit_apply(self) -> None:
        if self._current is not None:
            self.apply_material.emit(self._current)

    def current_material(self) -> Optional[Material]:
        return self._current

    def set_materials(self, materials: List[Material]) -> None:
        self._materials = materials
        self._by_name = {m.name: m for m in materials}
        self._current = None
        self._populate()
        self.info.clear()
        self.apply_btn.setEnabled(False)


# --------------------------------------------------------------------------- #
# Study setup panel (part / fixtures / loads / coordinate system)
# --------------------------------------------------------------------------- #
class StudySetupPanel(QDockWidget):
    # workflow signals
    add_fixture_clicked = Signal()
    add_load_clicked = Signal()
    remove_fixture = Signal(int)
    remove_load = Signal(int)
    run_clicked = Signal()
    coord_changed = Signal()
    load_edited = Signal()
    mesh_size_changed = Signal(float)
    mesh_clicked = Signal()
    part_material_clicked = Signal(int)
    solver_backend_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__("分析设置", parent)
        self._study: Optional[Study] = None

        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(6, 6, 6, 6)

        # --- part info ---
        gb_part = QGroupBox("零件与材质")
        f_part = QFormLayout(gb_part)
        self.lbl_part = QLabel("未导入")
        self.material_list = QListWidget()
        self.material_list.setMaximumHeight(120)
        self.material_list.itemClicked.connect(self._on_material_item_clicked)
        self.lbl_mesh = QLabel("-")
        f_part.addRow("数模:", self.lbl_part)
        f_part.addRow("材质:", self.material_list)
        f_part.addRow("网格:", self.lbl_mesh)
        v.addWidget(gb_part)

        # --- fixtures ---
        gb_fix = QGroupBox("固定位置 (约束)")
        vf = QVBoxLayout(gb_fix)
        self.fix_list = QListWidget()
        self.fix_list.setMaximumHeight(110)
        self.fix_list.itemDoubleClicked.connect(self._on_fix_double_clicked)
        vf.addWidget(self.fix_list)
        rowf = QHBoxLayout()
        self.btn_add_fix = QPushButton("＋ 拾取固定面")
        self.btn_rm_fix = QPushButton("－ 删除")
        self.btn_rm_fix.clicked.connect(self._rm_fixture)
        rowf.addWidget(self.btn_add_fix)
        rowf.addWidget(self.btn_rm_fix)
        vf.addLayout(rowf)
        v.addWidget(gb_fix)

        # --- loads ---
        gb_load = QGroupBox("载荷 (加压位置与压力)")
        vl = QVBoxLayout(gb_load)
        self.load_list = QListWidget()
        self.load_list.setMaximumHeight(140)
        self.load_list.itemDoubleClicked.connect(self._on_load_double_clicked)
        vl.addWidget(self.load_list)
        rowl = QHBoxLayout()
        self.btn_add_load = QPushButton("＋ 拾取加压面")
        self.btn_rm_load = QPushButton("－ 删除")
        self.btn_rm_load.clicked.connect(self._rm_load)
        rowl.addWidget(self.btn_add_load)
        rowl.addWidget(self.btn_rm_load)
        vl.addLayout(rowl)
        v.addWidget(gb_load)

        # --- coordinate system ---
        gb_cs = QGroupBox("解析坐标系 (原点 + X轴 + Y轴)")
        fcs = QFormLayout(gb_cs)
        self.cs_ox = QDoubleSpinBox(); self.cs_ox.setRange(-1e6, 1e6); self.cs_ox.setDecimals(3)
        self.cs_oy = QDoubleSpinBox(); self.cs_oy.setRange(-1e6, 1e6); self.cs_oy.setDecimals(3)
        self.cs_oz = QDoubleSpinBox(); self.cs_oz.setRange(-1e6, 1e6); self.cs_oz.setDecimals(3)
        self.cs_xx = QDoubleSpinBox(); self.cs_xx.setRange(-1, 1); self.cs_xx.setValue(1.0); self.cs_xx.setDecimals(4)
        self.cs_xy = QDoubleSpinBox(); self.cs_xy.setRange(-1, 1); self.cs_xy.setDecimals(4)
        self.cs_xz = QDoubleSpinBox(); self.cs_xz.setRange(-1, 1); self.cs_xz.setDecimals(4)
        self.cs_yx = QDoubleSpinBox(); self.cs_yx.setRange(-1, 1); self.cs_yx.setDecimals(4)
        self.cs_yy = QDoubleSpinBox(); self.cs_yy.setRange(-1, 1); self.cs_yy.setValue(1.0); self.cs_yy.setDecimals(4)
        self.cs_yz = QDoubleSpinBox(); self.cs_yz.setRange(-1, 1); self.cs_yz.setDecimals(4)
        fcs.addRow("原点 X / Y / Z:", self._row(self.cs_ox, self.cs_oy, self.cs_oz))
        fcs.addRow("X轴:", self._row(self.cs_xx, self.cs_xy, self.cs_xz))
        fcs.addRow("Y轴:", self._row(self.cs_yx, self.cs_yy, self.cs_yz))
        for sb in (self.cs_ox, self.cs_oy, self.cs_oz,
                   self.cs_xx, self.cs_xy, self.cs_xz,
                   self.cs_yx, self.cs_yy, self.cs_yz):
            sb.valueChanged.connect(self._push_coord)
        v.addWidget(gb_cs)

        # --- mesh density ---
        gb_mesh = QGroupBox("网格密度")
        fm = QFormLayout(gb_mesh)
        mesh_row = QHBoxLayout()
        self.mesh_slider = QSlider(Qt.Horizontal)
        self.mesh_slider.setRange(0, 90)
        self.mesh_slider.setValue(70)
        self.mesh_slider.setTickPosition(QSlider.TicksBelow)
        self.mesh_slider.setTickInterval(10)
        self.mesh_size_label = QLabel("5.00 mm")
        self.mesh_size_label.setFixedWidth(60)
        self.mesh_size_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        mesh_row.addWidget(self.mesh_slider)
        mesh_row.addWidget(self.mesh_size_label)
        fm.addRow(mesh_row)
        
        mesh_info_row = QHBoxLayout()
        mesh_info_row.addWidget(QLabel("粗糙"))
        mesh_info_row.addStretch(1)
        mesh_info_row.addWidget(QLabel("良好"))
        fm.addRow(mesh_info_row)
        
        self.btn_mesh = QPushButton("网格化")
        self.btn_mesh.setStyleSheet("padding:6px;")
        fm.addRow(self.btn_mesh)
        v.addWidget(gb_mesh)
        self.mesh_slider.valueChanged.connect(self._on_mesh_slider_changed)
        self.btn_mesh.clicked.connect(self.mesh_clicked.emit)

        gb_solver = QGroupBox("求解器后端")
        fs = QFormLayout(gb_solver)
        self.solver_combo = QComboBox()
        self.solver_combo.addItem("内置线性静应力", "internal")
        self.solver_combo.addItem("CalculiX 外部求解器", "calculix")
        self.solver_combo.currentIndexChanged.connect(self._on_solver_changed)
        fs.addRow("后端:", self.solver_combo)
        fs.addRow(QLabel("不使用 SolidWorks COM 时，外部 FEA 后端是最接近的可部署方案。"))
        v.addWidget(gb_solver)

        self.btn_run = QPushButton("▶  运行仿真")
        self.btn_run.setStyleSheet("padding:8px; font-weight:bold;")
        self.btn_run.clicked.connect(self.run_clicked.emit)
        v.addWidget(self.btn_run)

        self.simulation_log = QTextEdit()
        self.simulation_log.setReadOnly(True)
        self.simulation_log.setMaximumHeight(120)
        self.simulation_log.setPlaceholderText("仿真过程信息将显示在此处...")
        self.simulation_log.setStyleSheet("font-size:11px;")
        v.addWidget(self.simulation_log)

        v.addStretch(1)
        self.setWidget(container)

    @staticmethod
    def _row(*widgets) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        for x in widgets:
            h.addWidget(x)
        return w

    def set_study(self, study: Study) -> None:
        self._study = study
        idx = self.solver_combo.findData(study.solver_backend)
        if idx >= 0:
            self.solver_combo.setCurrentIndex(idx)

    # --- refresh from study ---
    def refresh_part(self) -> None:
        s = self._study
        if s is None or not s.parts:
            self.lbl_part.setText("未导入")
            self.material_list.clear()
            self.lbl_mesh.setText("-")
            return
        if len(s.parts) > 1:
            self.lbl_part.setText(s.name)
        else:
            self.lbl_part.setText(s.parts[0].name)
        
        self.material_list.clear()
        for i, p in enumerate(s.parts):
            if p.material:
                item = QListWidgetItem(f"{p.name}: {p.material.name}")
            else:
                item = QListWidgetItem(f"{p.name}: 未定义")
            item.setData(Qt.UserRole, i)
            self.material_list.addItem(item)
        
        if s.parts[0].mesh is not None and s.parts[0].mesh.num_tets > 0:
            mesh = s.parts[0].mesh
            self.lbl_mesh.setText(
                f"节点 {mesh.num_nodes} / 单元 {mesh.num_tets} / 面 {mesh.num_faces} / 零件 {len(s.parts)}"
            )
        else:
            self.lbl_mesh.setText("待网格化")
    
    def _on_material_item_clicked(self, item: QListWidgetItem) -> None:
        part_idx = item.data(Qt.UserRole)
        if part_idx is not None:
            self.part_material_clicked.emit(part_idx)

    def _on_solver_changed(self, _idx: int) -> None:
        if self._study is None:
            return
        backend = self.solver_combo.currentData() or "internal"
        self._study.solver_backend = backend
        self.solver_backend_changed.emit(backend)

    def refresh_fixtures(self) -> None:
        self.fix_list.clear()
        if self._study is None:
            return
        for i, fx in enumerate(self._study.fixtures):
            item = QListWidgetItem(f"固定 #{i+1}  →  面 {fx.face_id}")
            self.fix_list.addItem(item)

    def refresh_loads(self) -> None:
        self.load_list.clear()
        if self._study is None:
            return
        for i, ld in enumerate(self._study.loads):
            load_type = "法向载荷" if not hasattr(ld, 'direction') else "定向载荷"
            txt = f"{load_type} #{i+1}  →  面 {ld.face_id}   {ld.force:.2f} N"
            item = QListWidgetItem(txt)
            self.load_list.addItem(item)

    def _on_fix_double_clicked(self, item: QListWidgetItem) -> None:
        idx = self.fix_list.row(item)
        if self._study is None or idx < 0 or idx >= len(self._study.fixtures):
            return
        fx = self._study.fixtures[idx]
        new_face_id, ok = QInputDialog.getInt(self, "编辑约束位置", "输入面ID:", value=fx.face_id)
        if ok:
            fx.face_id = new_face_id
            self.refresh_fixtures()

    def _on_load_double_clicked(self, item: QListWidgetItem) -> None:
        idx = self.load_list.row(item)
        if self._study is None or idx < 0 or idx >= len(self._study.loads):
            return
        ld = self._study.loads[idx]
        new_force, ok = QInputDialog.getDouble(self, "编辑载荷", "输入力值 (N):", value=ld.force)
        if ok:
            ld.force = new_force
            self.refresh_loads()

    def _rm_fixture(self) -> None:
        row = self.load_list.currentRow() if False else self.fix_list.currentRow()
        if row >= 0:
            self.remove_fixture.emit(row)

    def _rm_load(self) -> None:
        row = self.load_list.currentRow()
        if row >= 0:
            self.remove_load.emit(row)

    def _on_mesh_slider_changed(self) -> None:
        slider_val = self.mesh_slider.value()
        mesh_size = 12.0 - (slider_val / 90.0) * 9.0
        mesh_size = round(mesh_size * 100) / 100
        self.mesh_size_label.setText(f"{mesh_size:.2f} mm")
        if self._study is not None:
            self._study.mesh_size = mesh_size
            self.mesh_size_changed.emit(self._study.mesh_size)

    # --- coordinate system ---
    def _push_coord(self) -> None:
        if self._study is None:
            return
        self._study.coord_system = CoordSystem(
            origin=np.array([self.cs_ox.value(), self.cs_oy.value(), self.cs_oz.value()]),
            x_axis=np.array([self.cs_xx.value(), self.cs_xy.value(), self.cs_xz.value()]),
            y_axis=np.array([self.cs_yx.value(), self.cs_yy.value(), self.cs_yz.value()]),
        )
        self.coord_changed.emit()

    def update_ready_state(self, ready: bool, issues: List[str]) -> None:
        if ready:
            self.btn_run.setEnabled(True)
            self.btn_run.setToolTip("运行静态仿真")
        else:
            self.btn_run.setEnabled(False)
            self.btn_run.setToolTip("缺少:\n" + "\n".join(issues))

    def clear_setup(self) -> None:
        self.fix_list.clear()
        self.load_list.clear()
        self.simulation_log.clear()


# --------------------------------------------------------------------------- #
# Results panel
# --------------------------------------------------------------------------- #
class ResultsPanel(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("结果", parent)
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(6, 6, 6, 6)

        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMinimumHeight(180)
        v.addWidget(self.summary, 0)

        self.face_table = QTextEdit()
        self.face_table.setReadOnly(True)
        self.face_table.setMinimumHeight(300)
        v.addWidget(self.face_table, 1)

        self.setWidget(container)
        self.setMinimumHeight(500)

    def show_result(self, result: FEAResult, material_name: str,
                    yield_mpa: float) -> None:
        html = (
            "<style>td{padding:2px 8px;}</style>"
            f"<h3>仿真结果</h3>"
            f"<table>"
            f"<tr><td>材质</td><td>{material_name}</td></tr>"
            f"<tr><td>节点数</td><td>{result.num_nodes}</td></tr>"
            f"<tr><td>单元数</td><td>{result.num_tets}</td></tr>"
            f"<tr><td>最大位移</td><td><b>{result.max_displacement*1000:.6f} mm</b></td></tr>"
            f"<tr><td>最大 von Mises 应力</td><td><b>{result.max_von_mises/1e6:.4f} MPa</b></td></tr>"
            f"</table>"
        )
        self.summary.setHtml(html)
        self.summary.document().setTextWidth(self.summary.viewport().width())
        doc_height = self.summary.document().size().height()
        self.summary.setFixedHeight(int(doc_height) + 20)

        rows = ""
        for r in result.loaded_face_reports:
            ux, uy, uz = r["disp_local"]
            mag = r["magnitude"]
            unit = "N"
            val = r["load_value"]
            load_type_name = "法向载荷" if r["load_type"] == "pressure" else "定向载荷"
            rows += (
                f"<tr>"
                f"<td>{r['name']}</td>"
                f"<td>{load_type_name}<br/>{val:.2f} {unit}</td>"
                f"<td>{ux*1000:+.6f}</td>"
                f"<td>{uy*1000:+.6f}</td>"
                f"<td>{uz*1000:+.6f}</td>"
                f"<td>{mag*1000:.6f}</td>"
                f"</tr>"
            )
        table_html = (
            "<style>td{padding:2px 6px; font-size:11px;} th{background:#eee;}</style>"
            "<b>加压位置位移 (解析坐标系, 单位 mm)</b><table border='1' cellspacing='0'>"
            "<tr><th>位置</th><th>载荷</th><th>UX</th><th>UY</th><th>UZ</th><th>合成</th></tr>"
            f"{rows}</table>"
            "<p><i>注: UX/UY/UZ 为载荷作用面形心处位移在该坐标系下的分量。</i></p>"
        )
        self.face_table.setHtml(table_html)

    def clear_result(self) -> None:
        self.summary.setHtml("<i>尚未运行仿真。</i>")
        self.face_table.clear()
