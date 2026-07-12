"""Runtime hook: ensure the gmsh native DLL is discoverable.

gmsh.py loads ``gmsh-4.15.dll`` via ``ctypes.CDLL`` at import time. In a
PyInstaller bundle the DLL sits next to the (frozen) gmsh.py inside
``sys._MEIPASS``, but gmsh's own path search and ``ctypes.util.find_library``
may still miss it. We register that directory with the Windows DLL search
path so the ``CDLL`` call always succeeds.
"""
import os
import sys

_meipass = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
if _meipass and os.path.isdir(_meipass):
    try:
        os.add_dll_directory(_meipass)
    except (AttributeError, OSError):
        pass
    sep = os.pathsep
    cur = os.environ.get("PATH", "")
    if _meipass not in cur.split(sep):
        os.environ["PATH"] = _meipass + sep + cur
