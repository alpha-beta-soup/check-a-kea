import json
from pathlib import Path
from html import escape

from qgis.PyQt.QtWidgets import (
    QAction,
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QShortcut,
    QTextEdit,
    QDialog,
    QPlainTextEdit,
    QDialogButtonBox,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
)
from qgis.PyQt.QtGui import QKeySequence, QIcon
from qgis.PyQt.QtCore import Qt, QTimer

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeatureRequest,
)

from qgis.gui import QgsHighlight


class JsonConfigDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Edit Check-a-Kea config")
        self.resize(600, 520)

        self.config = config

        layout = QVBoxLayout(self)

        self.editor = QPlainTextEdit()
        self.editor.setPlainText(json.dumps(config, indent=2))
        self.editor.setTabChangesFocus(False)

        layout.addWidget(QLabel("Edit config.json directly, then click Save."))
        layout.addWidget(self.editor)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(button_box)

    def accept(self):
        try:
            self.config = json.loads(self.editor.toPlainText())
        except json.JSONDecodeError as error:
            QMessageBox.warning(
                self,
                "Invalid JSON",
                f"Could not save config because the JSON is invalid:\n\n{error}"
            )
            return

        super().accept()


class AttributeTableDialog(QDialog):
    def __init__(self, layer, feature, parent=None):
        super().__init__(parent)

        self.layer = None
        self.feature = None

        self.setWindowTitle("Check-a-Kea attributes")
        self.resize(650, 520)

        layout = QVBoxLayout(self)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Attribute", "Value"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)

        self.table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.Stretch
        )

        layout.addWidget(self.table)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        close_button = button_box.button(QDialogButtonBox.Close)
        if close_button:
            close_button.clicked.connect(self.close)

        layout.addWidget(button_box)

        self.update_feature(layer, feature)

    def update_feature(self, layer, feature):
        self.layer = layer
        self.feature = feature

        self.setWindowTitle(f"Check-a-Kea attributes - FID {feature.id()}")

        self.table.setRowCount(len(layer.fields()))

        for row, field in enumerate(layer.fields()):
            field_name = field.name()
            value = feature[field_name]

            field_item = QTableWidgetItem(field_name)
            value_item = QTableWidgetItem("" if value is None else str(value))

            self.table.setItem(row, 0, field_item)
            self.table.setItem(row, 1, value_item)

        self.table.resizeRowsToContents()


class CheckAKea:
    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()

        self.action = None
        self.dock = None

        self.layer_combo = None
        self.display_field_combo = None
        self.status_label = None

        self.validation_controls_widget = None
        self.comment_controls_widget = None
        self.comment_box = None
        self.save_comment_button = None

        self.attributes_dialog = None

        self.layer = None
        self.feature_ids = []
        self.index = -1

        self.highlight = None
        self.shortcuts = []

        self.waiting_to_advance = False

        self.plugin_dir = Path(__file__).parent
        self.config_path = self.plugin_dir / "config.json"
        self.config = self.load_config()

    def load_config(self):
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        if "comment_field" not in config:
            config["comment_field"] = "comment"

        return config

    def save_config(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)

    def initGui(self):
        icon_path = self.plugin_dir / "icon.png"

        if icon_path.exists():
            self.action = QAction(
                QIcon(str(icon_path)),
                "Check-a-Kea",
                self.iface.mainWindow()
            )
        else:
            self.action = QAction(
                "Check-a-Kea",
                self.iface.mainWindow()
            )

        self.action.triggered.connect(self.show_dock)

        self.iface.addPluginToMenu("&Check-a-Kea", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu("&Check-a-Kea", self.action)
            self.iface.removeToolBarIcon(self.action)

        self.clear_shortcuts()

        if self.attributes_dialog:
            self.attributes_dialog.close()
            self.attributes_dialog = None

        if self.dock:
            self.iface.removeDockWidget(self.dock)
            self.dock = None

    def show_dock(self):
        if self.dock is None:
            self.build_dock()

        self.dock.show()
        self.dock.raise_()

    def build_dock(self):
        self.dock = QDockWidget("Check-a-Kea", self.iface.mainWindow())
        self.dock.setObjectName("CheckAKeaDock")

        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.layer_combo = QComboBox()
        self.layer_combo.currentIndexChanged.connect(
            lambda _: self.layer_selection_changed()
        )

        refresh_layers_button = QPushButton("Refresh layer list")
        refresh_layers_button.clicked.connect(self.refresh_layer_combo)

        start_button = QPushButton("Start / refresh queue")
        start_button.clicked.connect(self.start_validation)

        config_button = QPushButton("Edit config / shortcuts")
        config_button.clicked.connect(self.open_config_dialog)

        reload_config_button = QPushButton("Reload config")
        reload_config_button.clicked.connect(self.reload_config)

        config_layout = QHBoxLayout()
        config_layout.addWidget(config_button)
        config_layout.addWidget(reload_config_button)

        self.status_label = QLabel("Choose a polygon layer, then start the queue.")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.RichText)

        layout.addWidget(QLabel("Target polygon layer"))
        layout.addWidget(self.layer_combo)
        layout.addWidget(refresh_layers_button)
        layout.addWidget(start_button)
        layout.addLayout(config_layout)

        self.validation_controls_widget = QWidget()
        validation_layout = QVBoxLayout(self.validation_controls_widget)
        validation_layout.setContentsMargins(0, 0, 0, 0)

        self.display_field_combo = QComboBox()
        self.display_field_combo.currentIndexChanged.connect(
            lambda _: self.display_field_changed()
        )
        self.display_field_combo.setToolTip(
            "Choose an attribute field to display for the current polygon."
        )

        previous_button = QPushButton("◀ Previous")
        previous_button.clicked.connect(self.previous_feature)
        previous_button.setToolTip("Go to previous polygon, Left Arrow")

        next_button = QPushButton("Next ▶")
        next_button.clicked.connect(self.next_feature)
        next_button.setToolTip("Go to next polygon, Right Arrow")

        nav_layout = QHBoxLayout()
        nav_layout.addWidget(previous_button)
        nav_layout.addWidget(next_button)

        show_attributes_button = QPushButton("Show attributes")
        show_attributes_button.clicked.connect(self.open_attributes_dialog)
        show_attributes_button.setToolTip(
            "Open a table showing all attributes for the current polygon."
        )

        validation_layout.addWidget(QLabel("Attribute to display"))
        validation_layout.addWidget(self.display_field_combo)
        validation_layout.addLayout(nav_layout)
        validation_layout.addWidget(show_attributes_button)

        self.comment_controls_widget = QWidget()
        comment_layout = QVBoxLayout(self.comment_controls_widget)
        comment_layout.setContentsMargins(0, 0, 0, 0)

        self.comment_box = QTextEdit()
        self.comment_box.setPlaceholderText(
            "Write an optional comment for this polygon..."
        )
        self.comment_box.setMinimumHeight(70)

        self.save_comment_button = QPushButton("Save comment")
        self.save_comment_button.clicked.connect(
            lambda: self.save_comment_for_current_feature(silent=False)
        )

        comment_layout.addWidget(QLabel("Comment"))
        comment_layout.addWidget(self.comment_box)
        comment_layout.addWidget(self.save_comment_button)

        layout.addWidget(self.validation_controls_widget)
        layout.addWidget(self.status_label)
        layout.addWidget(self.comment_controls_widget)

        widget.setLayout(layout)
        self.dock.setWidget(widget)

        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)

        self.refresh_layer_combo()
        self.set_validation_controls_visible(False)
        self.register_shortcuts()

    def set_validation_controls_visible(self, visible):
        if self.validation_controls_widget is not None:
            self.validation_controls_widget.setVisible(visible)

        if self.comment_controls_widget is not None:
            self.comment_controls_widget.setVisible(visible)

    def clear_active_queue(self):
        self.waiting_to_advance = False
        self.layer = None
        self.feature_ids = []
        self.index = -1

        self.clear_highlight()
        self.clear_comment_box()
        self.set_validation_controls_visible(False)

        if self.attributes_dialog and self.attributes_dialog.isVisible():
            self.attributes_dialog.close()

    def layer_selection_changed(self):
        self.clear_active_queue()
        self.refresh_display_field_combo()

        if self.status_label:
            self.status_label.setText(
                "Layer changed. Click Start / refresh queue to begin."
            )

    def open_config_dialog(self):
        dialog = JsonConfigDialog(self.config, self.iface.mainWindow())

        if dialog.exec_() != QDialog.Accepted:
            return

        self.config = dialog.config
        self.save_config()
        self.reload_config()

        if self.status_label:
            self.status_label.setText("Config saved and reloaded.")

    def reload_config(self):
        self.config = self.load_config()
        self.register_shortcuts()
        self.refresh_display_field_combo()
        self.waiting_to_advance = False

        if self.status_label:
            delay_ms = self.config.get("auto_advance_delay_ms", 100)
            self.status_label.setText(
                f"Config reloaded.<br>Auto-advance delay: {delay_ms} ms"
            )

    def refresh_layer_combo(self):
        if self.layer_combo is None:
            return

        current_layer_id = self.layer_combo.currentData()

        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()

        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer) and layer.geometryType() == 2:
                self.layer_combo.addItem(layer.name(), layer.id())

        if current_layer_id:
            index = self.layer_combo.findData(current_layer_id)
            if index >= 0:
                self.layer_combo.setCurrentIndex(index)

        self.layer_combo.blockSignals(False)

        self.clear_active_queue()
        self.refresh_display_field_combo()

        if self.status_label:
            self.status_label.setText(
                "Choose a polygon layer, then start the queue."
            )

    def refresh_display_field_combo(self):
        if self.layer_combo is None or self.display_field_combo is None:
            return

        current_field = self.display_field_combo.currentData()
        default_field = self.config.get("default_display_field")

        layer_id = self.layer_combo.currentData()
        layer = QgsProject.instance().mapLayer(layer_id)

        self.display_field_combo.blockSignals(True)
        self.display_field_combo.clear()

        self.display_field_combo.addItem("Select an attribute instead", None)

        if layer:
            for field in layer.fields():
                self.display_field_combo.addItem(field.name(), field.name())

            preferred_field = current_field or default_field

            if preferred_field:
                index = self.display_field_combo.findData(preferred_field)

                if index >= 0:
                    self.display_field_combo.setCurrentIndex(index)
                else:
                    self.display_field_combo.setCurrentIndex(0)
            else:
                self.display_field_combo.setCurrentIndex(0)

        self.display_field_combo.blockSignals(False)

        self.display_field_changed()

    def display_field_changed(self):
        if self.layer and self.feature_ids and self.index >= 0:
            self.show_current_feature()

    def get_display_field(self):
        if self.display_field_combo is None:
            return None

        return self.display_field_combo.currentData()

    def register_shortcuts(self):
        self.clear_shortcuts()

        for key in self.config["shortcuts"].keys():
            shortcut = QShortcut(QKeySequence(key), self.iface.mainWindow())
            shortcut.setContext(Qt.ApplicationShortcut)
            shortcut.activated.connect(
                lambda k=key: self.apply_validation(k)
            )
            self.shortcuts.append(shortcut)

        previous_shortcut = QShortcut(
            QKeySequence(Qt.Key_Left),
            self.iface.mainWindow()
        )
        previous_shortcut.setContext(Qt.ApplicationShortcut)
        previous_shortcut.activated.connect(self.previous_feature)
        self.shortcuts.append(previous_shortcut)

        next_shortcut = QShortcut(
            QKeySequence(Qt.Key_Right),
            self.iface.mainWindow()
        )
        next_shortcut.setContext(Qt.ApplicationShortcut)
        next_shortcut.activated.connect(self.next_feature)
        self.shortcuts.append(next_shortcut)

    def clear_shortcuts(self):
        for shortcut in self.shortcuts:
            shortcut.setParent(None)
            shortcut.deleteLater()

        self.shortcuts = []

    def start_validation(self):
        self.waiting_to_advance = False

        layer_id = self.layer_combo.currentData()
        self.layer = QgsProject.instance().mapLayer(layer_id)

        if not self.layer:
            self.status_label.setText("No valid polygon layer selected.")
            self.set_validation_controls_visible(False)
            return

        validation_field = self.config["validation_field"]

        if validation_field not in [field.name() for field in self.layer.fields()]:
            self.status_label.setText(
                f"Field '{escape(validation_field)}' does not exist in this layer.<br>"
                f"Add it as a Text/String field first."
            )
            self.set_validation_controls_visible(False)
            return

        if not self.layer.isEditable():
            self.layer.startEditing()

        self.feature_ids = self.get_validation_feature_ids()
        self.index = 0

        if not self.feature_ids:
            self.status_label.setText("No polygons found for validation.")
            self.clear_highlight()
            self.clear_comment_box()
            self.set_validation_controls_visible(False)
            return

        self.refresh_display_field_combo()
        self.set_validation_controls_visible(True)
        self.show_current_feature()

    def get_validation_feature_ids(self):
        filter_expression = self.config.get(
            "unvalidated_filter",
            f"{self.config['validation_field']} IS NULL OR "
            f"{self.config['validation_field']} = ''"
        )

        request = QgsFeatureRequest()
        request.setFilterExpression(filter_expression)

        return [feature.id() for feature in self.layer.getFeatures(request)]

    def show_current_feature(self):
        if not self.layer or not self.feature_ids:
            return

        self.index = max(0, min(self.index, len(self.feature_ids) - 1))
        fid = self.feature_ids[self.index]

        request = QgsFeatureRequest(fid)
        feature = next(self.layer.getFeatures(request), None)

        if feature is None:
            self.status_label.setText("Could not load feature.")
            return

        self.layer.selectByIds([fid])
        self.zoom_to_feature(feature)
        self.highlight_feature(feature)
        self.load_comment_for_feature(feature)
        self.refresh_attributes_dialog(feature)

        validation_field = self.config["validation_field"]
        current_value = feature[validation_field]

        comment_field = self.config.get("comment_field", "comment")
        if self.layer.fields().indexOf(comment_field) == -1:
            comment_status = f"missing field: {comment_field}"
        else:
            comment_status = comment_field

        display_field = self.get_display_field()
        display_text = "Select an attribute to display."

        if display_field and self.layer.fields().indexOf(display_field) != -1:
            display_value = feature[display_field]

            if display_value is None:
                display_value_text = ""
            else:
                display_value_text = str(display_value)

            max_chars = 300
            if len(display_value_text) > max_chars:
                display_value_text = display_value_text[:max_chars] + "..."

            display_text = (
                f"<b>{escape(display_field)}: "
                f"{escape(display_value_text)}</b>"
            )

        shortcut_text = "\n".join(
            f"{key} = {value}"
            for key, value in self.config["shortcuts"].items()
        )

        delay_ms = self.config.get("auto_advance_delay_ms", 100)

        self.status_label.setText(
            f"Polygon {self.index + 1} of {len(self.feature_ids)}<br>"
            f"FID: {fid}<br>"
            f"<b>{escape(validation_field)}: {escape(str(current_value))}</b><br>"
            f"Comment field: {escape(comment_status)}<br><br>"
            f"Display attribute:<br>"
            f"{display_text}<br><br>"
            f"Navigation:<br>"
            f"◀ Left Arrow = Previous<br>"
            f"Right Arrow = Next ▶<br><br>"
            f"Validation shortcuts:<br>"
            f"{escape(shortcut_text).replace(chr(10), '<br>')}<br><br>"
            f"Auto-advance delay: {delay_ms} ms"
        )

    def open_attributes_dialog(self):
        if not self.layer or not self.feature_ids or self.index < 0:
            return

        fid = self.feature_ids[self.index]
        request = QgsFeatureRequest(fid)
        feature = next(self.layer.getFeatures(request), None)

        if feature is None:
            if self.status_label:
                self.status_label.setText("Could not load feature attributes.")
            return

        if self.attributes_dialog is None or not self.attributes_dialog.isVisible():
            self.attributes_dialog = AttributeTableDialog(
                self.layer,
                feature,
                self.iface.mainWindow()
            )
            self.attributes_dialog.show()
        else:
            self.attributes_dialog.update_feature(self.layer, feature)

        self.attributes_dialog.raise_()
        self.attributes_dialog.activateWindow()

    def refresh_attributes_dialog(self, feature):
        if self.attributes_dialog is None:
            return

        if not self.attributes_dialog.isVisible():
            return

        if not self.layer:
            return

        self.attributes_dialog.update_feature(self.layer, feature)

    def load_comment_for_feature(self, feature):
        if self.comment_box is None:
            return

        comment_field = self.config.get("comment_field", "comment")
        field_index = self.layer.fields().indexOf(comment_field)

        self.comment_box.blockSignals(True)

        if field_index == -1:
            self.comment_box.setPlainText("")
            self.comment_box.setEnabled(False)
            if self.save_comment_button:
                self.save_comment_button.setEnabled(False)
            self.comment_box.setPlaceholderText(
                f"Comment field '{comment_field}' does not exist."
            )
        else:
            comment_value = feature[comment_field]
            self.comment_box.setPlainText(
                "" if comment_value is None else str(comment_value)
            )
            self.comment_box.setEnabled(True)
            if self.save_comment_button:
                self.save_comment_button.setEnabled(True)
            self.comment_box.setPlaceholderText(
                "Write an optional comment for this polygon..."
            )

        self.comment_box.blockSignals(False)

    def clear_comment_box(self):
        if self.comment_box is None:
            return

        self.comment_box.blockSignals(True)
        self.comment_box.setPlainText("")
        self.comment_box.blockSignals(False)

    def save_comment_for_current_feature(self, silent=True):
        if not self.layer or not self.feature_ids or self.index < 0:
            return False

        if self.comment_box is None:
            return False

        comment_field = self.config.get("comment_field", "comment")
        field_index = self.layer.fields().indexOf(comment_field)

        if field_index == -1:
            if not silent and self.status_label:
                self.status_label.setText(
                    f"Comment field '{escape(comment_field)}' does not exist."
                )
            return False

        fid = self.feature_ids[self.index]
        comment_text = self.comment_box.toPlainText()

        if not self.layer.isEditable():
            self.layer.startEditing()

        success = self.layer.changeAttributeValue(
            fid,
            field_index,
            comment_text
        )

        if not success:
            if not silent and self.status_label:
                self.status_label.setText(
                    f"Could not save comment for feature {fid}."
                )
            return False

        if not silent:
            self.iface.messageBar().pushSuccess(
                "Check-a-Kea",
                f"Saved comment for feature {fid}."
            )

            self.show_current_feature()

        return True

    def zoom_to_feature(self, feature):
        geom = feature.geometry()

        if geom is None or geom.isEmpty():
            return

        extent = geom.boundingBox()

        buffer_percent = self.config.get("zoom_buffer_percent", 30)
        extent.scale(1 + buffer_percent / 100)

        self.canvas.setExtent(extent)
        self.canvas.refresh()

    def highlight_feature(self, feature):
        self.clear_highlight()

        self.highlight = QgsHighlight(
            self.canvas,
            feature.geometry(),
            self.layer
        )

        self.highlight.setWidth(3)
        self.highlight.show()

    def clear_highlight(self):
        if self.highlight:
            self.highlight.hide()
            self.highlight = None

    def apply_validation(self, key):
        if self.waiting_to_advance:
            return

        if not self.layer or not self.feature_ids:
            return

        if key not in self.config["shortcuts"]:
            return

        validation_value = self.config["shortcuts"][key]
        validation_field = self.config["validation_field"]

        fid = self.feature_ids[self.index]
        field_index = self.layer.fields().indexOf(validation_field)

        if field_index == -1:
            self.status_label.setText(
                f"Field '{escape(validation_field)}' does not exist."
            )
            return

        if not self.layer.isEditable():
            self.layer.startEditing()

        success = self.layer.changeAttributeValue(
            fid,
            field_index,
            validation_value
        )

        if not success:
            self.status_label.setText(
                f"Could not write '{escape(validation_value)}' to feature {fid}."
            )
            return

        self.save_comment_for_current_feature(silent=True)

        if self.config.get("auto_advance", True):
            delay_ms = self.config.get("auto_advance_delay_ms", 100)
            self.waiting_to_advance = True

            display_field = self.get_display_field()
            extra_display = ""

            if display_field:
                extra_display = f"<br>Display field: {escape(display_field)}"

            self.status_label.setText(
                f"Set {escape(validation_field)} = {escape(validation_value)}<br>"
                f"FID: {fid}"
                f"{extra_display}<br>"
                f"Advancing in {delay_ms} ms..."
            )

            QTimer.singleShot(delay_ms, self.advance_after_delay)
        else:
            self.show_current_feature()

    def advance_after_delay(self):
        self.waiting_to_advance = False
        self.next_feature()

    def next_feature(self):
        if self.waiting_to_advance:
            return

        if not self.feature_ids:
            return

        self.save_comment_for_current_feature(silent=True)

        if self.index < len(self.feature_ids) - 1:
            self.index += 1
            self.show_current_feature()
        else:
            self.status_label.setText("Finished validation queue.")
            self.clear_highlight()
            self.clear_comment_box()
            self.set_validation_controls_visible(False)

    def previous_feature(self):
        if self.waiting_to_advance:
            return

        if not self.feature_ids:
            return

        self.save_comment_for_current_feature(silent=True)

        if self.index > 0:
            self.index -= 1
            self.show_current_feature()