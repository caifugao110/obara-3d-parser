"""obara-3d-parser - a lightweight SolidWorks-style static FEA app."""

import os
import sys
import tomllib


def _current_version() -> str:
    try:
        if getattr(sys, "frozen", False):
            root_dir = sys._MEIPASS
        else:
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pyproject_path = os.path.join(root_dir, "pyproject.toml")
        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)
        version = pyproject["project"]["version"]
        if version != "0.0.0":
            return version
    except Exception:
        pass
    from datetime import date
    return f"v{date.today():%Y.%m.%d}-beta"


__version__ = _current_version()
__author__ = "Tobin"
__license__ = "MIT"
