# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for obara-3d-parser.

Bundles gmsh, VTK, pyvista and PySide6 (which all ship binary plugins /
data files) plus the material database.

gmsh is a *single-file* module (gmsh.py) that loads a native shared
library (gmsh-4.15.dll) via ctypes at import time. ``collect_all('gmsh')``
skips binary collection because gmsh is not a package, so we locate the
DLL ourselves using the same search paths as gmsh.py and add it to the
binaries list.
"""
import os
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = [
    "scipy.sparse.linalg",
]


def _find_gmsh_dll():
    """Locate the gmsh native library exactly like gmsh.py does."""
    import platform
    if platform.system() == "Windows":
        libname = "gmsh-4.15.dll"
    elif platform.system() == "Darwin":
        libname = "libgmsh.4.15.dylib"
    else:
        libname = "libgmsh.so.4.15"

    candidates = []
    try:
        import gmsh as _gmsh_mod
        moduledir = os.path.dirname(os.path.realpath(_gmsh_mod.__file__))
    except Exception:
        moduledir = os.path.dirname(os.path.realpath(__file__))

    parentdir1 = os.path.dirname(moduledir)
    parentdir2 = os.path.dirname(parentdir1)
    for base in (moduledir, parentdir1, parentdir2):
        for sub in ("", "lib", "Lib", "bin"):
            candidates.append(os.path.join(base, sub, libname))
    candidates.append(os.path.join(parentdir2, "Library", "bin", "gmsh.dll"))

    for c in candidates:
        if os.path.exists(c):
            return c

    try:
        import gmsh as _gmsh_mod
        return _gmsh_mod.lib._name
    except Exception:
        pass
    return None


for pkg in ("vtk", "pyvista", "PySide6", "shiboken6"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += ["gmsh"]
gmsh_dll = _find_gmsh_dll()
if gmsh_dll and os.path.exists(gmsh_dll):
    binaries += [(gmsh_dll, ".")]
    print(f"[spec] bundled gmsh DLL: {gmsh_dll}")
else:
    print("[spec] WARNING: could not locate gmsh native library!")

datas += [("material_data", "material_data"), ("assets", "assets")]

a = Analysis(
    ["run.py"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    runtime_hooks=["hooks/runtime_hook_scipy.py", "hooks/runtime_hook_gmsh.py"],
    excludes=[
        "PyQt5", "PyQt6", "PySide2", "tkinter",
        "IPython", "jupyter", "pytest", "pandas",
        "sklearn", "scikit-learn",
        "vtkmodules.web", "vtkmodules.qt",
        "matplotlib.tests",
    ],
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="obara-3d-parser",
    console=False,
    icon="assets/app_icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="obara-3d-parser",
)
