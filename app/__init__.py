"""obara-3d-parser - a lightweight SolidWorks-style static FEA app."""

from datetime import date


def _current_version() -> str:
    return f"v{date.today():%y-%m-%d}-α"


__version__ = _current_version()
__author__ = "Tobin"
__license__ = "MIT"
