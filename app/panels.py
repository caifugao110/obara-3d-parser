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
    QHeaderView, QMessageBox, QInputDialog, QSplitter, QFrame,
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

    def __init__(self, materials: List[Material], parent=None):
        super().__init__("材质库", parent)
        self._materials = materials
        self._by_name = {m.name: m for m in materials}
        self._current: Optional[Material] = None

        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(6, 6, 6, 6)

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
        self.lbl_material = QLabel("未定义")
        self.lbl_mesh = QLabel("-")
        f_part.addRow("数模:", self.lbl_part)
        f_part.addRow("材质:", self.lbl_material)
        f_part.addRow("网格:", self.lbl_mesh)
        v.addWidget(gb_part)

        # --- fixtures ---
        gb_fix = QGroupBox("固定位置 (约束)")
        vf = QVBoxLayout(gb_fix)
        self.fix_list = QListWidget()
        self.fix_list.setMaximumHeight(110)
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
        self.load_list.itemChanged.connect(self._on_load_item_edited)
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

        self.btn_run = QPushButton("▶  运行仿真")
        self.btn_run.setStyleSheet("padding:8px; font-weight:bold;")
        self.btn_run.clicked.connect(self.run_clicked.emit)
        v.addWidget(self.btn_run)

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

    # --- refresh from study ---
    def refresh_part(self) -> None:
        s = self._study
        if s is None or s.part is None:
            self.lbl_part.setText("未导入")
            self.lbl_material.setText("未定义")
            self.lbl_mesh.setText("-")
            return
        self.lbl_part.setText(s.part.name)
        m = s.material
        self.lbl_material.setText(m.name if m else "未定义")
        self.lbl_mesh.setText(
            f"节点 {s.part.mesh.num_nodes} / 单元 {s.part.mesh.num_tets} / 面 {s.part.mesh.num_faces}"
        )

    def refresh_fixtures(self) -> None:
        self.fix_list.clear()
        if self._study is None:
            return
        for i, fx in enumerate(self._study.fixtures):
            self.fix_list.addItem(QListWidgetItem(f"固定 #{i+1}  →  面 {fx.face_id}"))

    def refresh_loads(self) -> None:
        self.load_list.clear()
        if self._study is None:
            return
        for i, ld in enumerate(self._study.loads):
            txt = (f"压力 #{i+1}  →  面 {ld.face_id}   {ld.pressure/1e6:.4f} MPa"
                   if hasattr(ld, "pressure")
                   else f"力 #{i+1}  →  面 {ld.face_id}   {ld.force:.2f} N")
            item = QListWidgetItem(txt)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self.load_list.addItem(item)

    def _on_load_item_edited(self, item: QListWidgetItem) -> None:
        idx = self.load_list.row(item)
        if self._study is None or idx < 0 or idx >= len(self._study.loads):
            return
        ld = self._study.loads[idx]
        try:
            val = float(item.text().split()[-2])  # last numeric token
        except Exception:
            self.refresh_loads()
            return
        if hasattr(ld, "pressure"):
            ld.pressure = val * 1e6  # MPa -> Pa
        else:
            ld.force = val
        self.load_edited.emit()

    def _rm_fixture(self) -> None:
        row = self.load_list.currentRow() if False else self.fix_list.currentRow()
        if row >= 0:
            self.remove_fixture.emit(row)

    def _rm_load(self) -> None:
        row = self.load_list.currentRow()
        if row >= 0:
            self.remove_load.emit(row)

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
        v.addWidget(self.summary, 1)

        self.face_table = QTextEdit()
        self.face_table.setReadOnly(True)
        self.face_table.setMaximumHeight(220)
        v.addWidget(self.face_table, 0)

        self.setWidget(container)

    def show_result(self, result: FEAResult, material_name: str,
                    yield_mpa: float) -> None:
        sf = result.safety_factor
        sf_txt = f"{sf:.3f}" if np.isfinite(sf) else "∞"
        html = (
            "<style>td{padding:2px 8px;}</style>"
            f"<h3>仿真结果</h3>"
            f"<table>"
            f"<tr><td>材质</td><td>{material_name}</td></tr>"
            f"<tr><td>节点数</td><td>{result.num_nodes}</td></tr>"
            f"<tr><td>单元数</td><td>{result.num_tets}</td></tr>"
            f"<tr><td>最大位移</td><td><b>{result.max_displacement*1000:.6f} mm</b></td></tr>"
            f"<tr><td>最大 von Mises 应力</td><td><b>{result.max_von_mises/1e6:.4f} MPa</b></td></tr>"
            f"<tr><td>屈服强度</td><td>{yield_mpa:.3f} MPa</td></tr>"
            f"<tr><td>安全系数</td><td><b style='color:{'green' if (np.isfinite(sf) and sf>1.5) else 'red'}'>{sf_txt}</b></td></tr>"
            f"</table>"
        )
        self.summary.setHtml(html)

        rows = ""
        for r in result.loaded_face_reports:
            ux, uy, uz = r["disp_local"]
            mag = r["magnitude"]
            unit = "MPa" if r["load_type"] == "pressure" else "N"
            val = r["load_value"] / 1e6 if r["load_type"] == "pressure" else r["load_value"]
            rows += (
                f"<tr>"
                f"<td>{r['name']}</td>"
                f"<td>{r['load_type']}<br/>{val:.4f} {unit}</td>"
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
