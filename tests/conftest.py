import sys
from pathlib import Path

# Make core/ importable without being inside the QGIS plugin package
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import qgis  # noqa: F401 — available when PYTHONPATH includes QGIS Python
except ModuleNotFoundError:
    # Stub out QGIS and Qt so unit tests run without a QGIS install
    from unittest.mock import MagicMock

    for _mod in [
        "qgis",
        "qgis.core",
        "qgis.gui",
        "qgis.PyQt",
        "qgis.PyQt.QtCore",
        "qgis.PyQt.QtGui",
        "qgis.PyQt.QtWidgets",
        "sip",
    ]:
        sys.modules.setdefault(_mod, MagicMock())
