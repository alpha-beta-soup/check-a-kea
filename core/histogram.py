from qgis.PyQt.QtWidgets import QWidget
from qgis.PyQt.QtGui import QColor, QPainter
from qgis.PyQt.QtCore import Qt, QRect


class HistogramWidget(QWidget):
    _BAR_COLOR = QColor(74, 144, 226)
    _NULL_COLOR = QColor(160, 160, 160)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []

    def update_data(self, counts):
        """counts: dict mapping str-or-None → int"""
        self._data = sorted(counts.items(), key=lambda x: (x[0] is None, x[0] or ""))
        n = len(self._data)
        self.setMinimumHeight(n * self._row_h() + 16 if n else 40)
        self.update()

    def _row_h(self):
        return self.fontMetrics().height() + 6

    def paintEvent(self, event):
        if not self._data:
            return

        p = QPainter(self)
        fm = self.fontMetrics()
        row_h = self._row_h()
        margin = 8

        label_w = (
            max(fm.horizontalAdvance(lbl or "(none)") for lbl, _ in self._data) + 8
        )
        max_count = max(c for _, c in self._data)
        count_w = fm.horizontalAdvance(str(max_count)) + 8

        bar_x = margin + label_w
        bar_w = max(1, self.width() - margin * 2 - label_w - count_w)
        text_color = self.palette().windowText().color()

        for i, (label, count) in enumerate(self._data):
            y = margin + i * row_h
            display = label if label is not None else "(none)"

            p.setPen(text_color)
            p.drawText(
                QRect(margin, y, label_w - 4, row_h),
                Qt.AlignRight | Qt.AlignVCenter,
                display,
            )

            filled_w = int(bar_w * count / max_count) if max_count else 0
            p.fillRect(
                bar_x,
                y + 2,
                filled_w,
                row_h - 4,
                self._NULL_COLOR if label is None else self._BAR_COLOR,
            )

            p.setPen(text_color)
            p.drawText(
                QRect(bar_x + bar_w + 4, y, count_w, row_h),
                Qt.AlignLeft | Qt.AlignVCenter,
                str(count),
            )

        p.end()
