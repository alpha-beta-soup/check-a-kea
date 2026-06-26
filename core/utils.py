from qgis.PyQt.QtCore import Qt, QCoreApplication
from qgis.PyQt.QtGui import QIcon, QPixmap, QPainter


def tr(string):
    return QCoreApplication.translate("CheckAKea", string)


def dim_icon(icon):
    pixmap = icon.pixmap(16, 16)
    result = QPixmap(pixmap.size())
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setOpacity(0.25)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return QIcon(result)
