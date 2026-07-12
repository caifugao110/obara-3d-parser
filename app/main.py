"""Application entry point.

Locates the bundled material database and launches the Qt main window.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _resource_path(resource: str) -> str:
    here = Path(__file__).resolve().parent
    frozen_dirs = []
    if getattr(sys, "frozen", False):
        frozen_dirs.append(Path(sys.executable).resolve().parent)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            frozen_dirs.append(Path(meipass))
    candidates = (
        [d / "assets" / resource for d in frozen_dirs]
        + [
            here.parent / "assets" / resource,
            here / "assets" / resource,
            Path("assets") / resource,
        ]
    )
    for c in candidates:
        if c.exists():
            return str(c)
    return str(candidates[0])


def _material_db_path() -> str:
    here = Path(__file__).resolve().parent
    frozen_dirs = []
    if getattr(sys, "frozen", False):
        frozen_dirs.append(Path(sys.executable).resolve().parent)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            frozen_dirs.append(Path(meipass))
    candidates = (
        [d / "material_data" / "sldmaterials.json" for d in frozen_dirs]
        + [
            here.parent / "material_data" / "sldmaterials.json",
            here / "material_data" / "sldmaterials.json",
            Path("material_data") / "sldmaterials.json",
        ]
    )
    for c in candidates:
        if c.exists():
            return str(c)
    return str(candidates[0])


def main() -> int:
    # gmsh prints to its own terminal; silence it.
    os.environ.setdefault("GMSH_VERBOSITY", "0")

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setApplicationName("obara-3d-parser")

    icon_path = _resource_path("app_icon.ico")
    app.setWindowIcon(QIcon(icon_path))

    # defer import so gmsh/pyvista are only loaded once Qt exists
    from .main_window import MainWindow

    win = MainWindow(_material_db_path())
    win.setWindowIcon(QIcon(icon_path))
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
