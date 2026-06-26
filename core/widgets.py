import json

from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)
from qgis.PyQt.QtGui import QStandardItem
from qgis.PyQt.QtCore import Qt, QEvent, QObject

from .utils import tr


class CommentFocusGuard(QObject):
    """Redirects focus to the canvas when the user clicks outside the comment box.

    Without this, the comment box keeps keyboard focus and swallows the
    validation shortcut keys.
    """

    def __init__(self, comment_box, canvas):
        super().__init__()
        self._box = comment_box
        self._canvas = canvas

    def eventFilter(self, obj, event):
        if (
            event.type() == QEvent.MouseButtonPress
            and self._box.hasFocus()
            and isinstance(obj, QWidget)
            and obj is not self._box
            and not self._box.isAncestorOf(obj)
        ):
            self._canvas.setFocus()
        return False


class CheckableComboBox(QComboBox):
    """A combo box whose dropdown items each have a checkbox."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setPlaceholderText(tr("Select attributes..."))

    def showPopup(self):
        self.view().viewport().installEventFilter(self)
        super().showPopup()

    def hidePopup(self):
        self.view().viewport().removeEventFilter(self)
        super().hidePopup()

    def eventFilter(self, obj, event):
        if obj == self.view().viewport() and event.type() == QEvent.MouseButtonRelease:
            index = self.view().indexAt(event.pos())
            if index.isValid():
                item = self.model().itemFromIndex(index)
                if item and item.isCheckable():
                    item.setCheckState(
                        Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
                    )
                    return True
        return super().eventFilter(obj, event)

    def add_check_item(self, text, checked=False):
        item = QStandardItem(text)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.model().appendRow(item)

    def checked_items(self):
        model = self.model()
        return [
            model.item(i).text()
            for i in range(model.rowCount())
            if model.item(i) and model.item(i).checkState() == Qt.Checked
        ]

    def update_display(self):
        checked = self.checked_items()
        self.lineEdit().setText(", ".join(checked) if checked else "")


class LayerComboBox(QComboBox):
    """A combo box that refreshes its contents each time the user opens it."""

    def __init__(self, refresh_fn, parent=None):
        super().__init__(parent)
        self._refresh_fn = refresh_fn

    def mousePressEvent(self, event):
        self._refresh_fn()
        super().mousePressEvent(event)


class JsonConfigDialog(QDialog):
    """A simple JSON editor dialog for the plugin config."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Edit Check-a-Kea config"))
        self.resize(600, 520)
        self.config = config

        layout = QVBoxLayout(self)

        self.editor = QPlainTextEdit()
        self.editor.setPlainText(json.dumps(config, indent=2))
        self.editor.setTabChangesFocus(False)

        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(QLabel(tr("Edit config.json directly, then click Save.")))
        layout.addWidget(self.editor)
        layout.addWidget(button_box)

    def accept(self):
        try:
            self.config = json.loads(self.editor.toPlainText())
        except json.JSONDecodeError as error:
            QMessageBox.warning(
                self,
                tr("Invalid JSON"),
                tr("Could not save config because the JSON is invalid:\n\n{}").format(
                    error
                ),
            )
            return
        super().accept()
