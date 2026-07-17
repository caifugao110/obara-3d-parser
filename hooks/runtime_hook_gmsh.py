"""Runtime hook: ensure native DLLs are discoverable.

gmsh.py loads ``gmsh-4.15.dll`` via ``ctypes.CDLL`` at import time. In a
PyInstaller bundle the DLL sits next to the (frozen) gmsh.py inside
``sys._MEIPASS``, but gmsh's own path search and ``ctypes.util.find_library``
may still miss it. We register that directory with the Windows DLL search
path so the ``CDLL`` call always succeeds.

Also adds the PyInstaller and PySide6 binary directories to PATH for Qt DLLs.
"""
import os
import sys

def _add_dll_dir(path):
    if not path or not os.path.isdir(path):
        return
    try:
        os.add_dll_directory(path)
    except (AttributeError, OSError):
        pass
    sep = os.pathsep
    cur = os.environ.get("PATH", "")
    if path not in cur.split(sep):
        os.environ["PATH"] = path + sep + cur


_base_dir = os.path.dirname(sys.executable)
_meipass = getattr(sys, "_MEIPASS", None) or _base_dir
_internal_dir = os.path.join(_base_dir, "_internal")

for _dll_dir in (
    os.path.join(_internal_dir, "PySide6"),
    _internal_dir,
    os.path.join(_meipass, "PySide6"),
    _meipass,
):
    _add_dll_dir(_dll_dir)
