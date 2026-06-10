import json
from pathlib import Path

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
)
from qgis.PyQt.QtGui import QKeySequence, QIcon
from qgis.PyQt.QtCore import Qt, QTimer

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeatureRequest,
)

from qgis.gui import QgsHighlight


class CheckAKea:
    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()

        self.action = None
        self.dock = None
        self.layer_combo = None
        self.display_field_combo = None
        self.status_label = None

        self.layer = None
        self.feature_ids = []
        self.index = -1

        self.highlight = None
        self.shortcuts = []

        self.waiting_to_advance = False

        self.config = self.load_config()

    def load_config(self):
        plugin_dir = Path(__file__).parent
        config_path = plugin_dir / "config.json"

        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def initGui(self):
        plugin_dir = Path(__file__).parent
        icon_path = plugin_dir / "icon.png"

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
            lambda _: self.refresh_display_field_combo()
        )

        self.display_field_combo = QComboBox()
        self.display_field_combo.currentIndexChanged.connect(
            lambda _: self.display_field_changed()
        )
        self.display_field_combo.setToolTip(
            "Choose an attribute field to display for the current polygon."
        )

        self.refresh_layer_combo()

        refresh_layers_button = QPushButton("Refresh layer list")
        refresh_layers_button.clicked.connect(self.refresh_layer_combo)

        start_button = QPushButton("Start / refresh queue")
        start_button.clicked.connect(self.start_validation)

        previous_button = QPushButton("◀ Previous")
        previous_button.clicked.connect(self.previous_feature)
        previous_button.setToolTip("Go to previous polygon, Left Arrow")

        next_button = QPushButton("Next ▶")
        next_button.clicked.connect(self.next_feature)
        next_button.setToolTip("Go to next polygon, Right Arrow")

        nav_layout = QHBoxLayout()
        nav_layout.addWidget(previous_button)
        nav_layout.addWidget(next_button)

        reload_config_button = QPushButton("Reload config")
        reload_config_button.clicked.connect(self.reload_config)

        self.status_label = QLabel("Choose a polygon layer and start.")
        self.status_label.setWordWrap(True)

        layout.addWidget(QLabel("Target polygon layer"))
        layout.addWidget(self.layer_combo)
        layout.addWidget(refresh_layers_button)

        layout.addWidget(QLabel("Attribute to display"))
        layout.addWidget(self.display_field_combo)

        layout.addWidget(start_button)
        layout.addLayout(nav_layout)
        layout.addWidget(reload_config_button)
        layout.addWidget(self.status_label)

        widget.setLayout(layout)
        self.dock.setWidget(widget)

        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)

        self.register_shortcuts()

    def reload_config(self):
        self.config = self.load_config()
        self.register_shortcuts()
        self.refresh_display_field_combo()
        self.waiting_to_advance = False

        if self.status_label:
            delay_ms = self.config.get("auto_advance_delay_ms", 100)
            self.status_label.setText(
                f"Config reloaded.\nAuto-advance delay: {delay_ms} ms"
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

        self.refresh_display_field_combo()

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
            return

        validation_field = self.config["validation_field"]

        if validation_field not in [field.name() for field in self.layer.fields()]:
            self.status_label.setText(
                f"Field '{validation_field}' does not exist in this layer.\n"
                f"Add it as a Text/String field first."
            )
            return

        if not self.layer.isEditable():
            self.layer.startEditing()

        self.feature_ids = self.get_validation_feature_ids()
        self.index = 0

        if not self.feature_ids:
            self.status_label.setText("No polygons found for validation.")
            self.clear_highlight()
            return

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

        validation_field = self.config["validation_field"]
        current_value = feature[validation_field]

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

            display_text = f"{display_field}: {display_value_text}"

        shortcut_text = "\n".join(
            f"{key} = {value}"
            for key, value in self.config["shortcuts"].items()
        )

        delay_ms = self.config.get("auto_advance_delay_ms", 100)

        self.status_label.setText(
            f"Polygon {self.index + 1} of {len(self.feature_ids)}\n"
            f"FID: {fid}\n"
            f"{validation_field}: {current_value}\n\n"
            f"Display attribute:\n"
            f"{display_text}\n\n"
            f"Navigation:\n"
            f"◀ Left Arrow = Previous\n"
            f"Right Arrow = Next ▶\n\n"
            f"Validation shortcuts:\n"
            f"{shortcut_text}\n\n"
            f"Auto-advance delay: {delay_ms} ms"
        )

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
                f"Field '{validation_field}' does not exist."
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
                f"Could not write '{validation_value}' to feature {fid}."
            )
            return

        if self.config.get("auto_advance", True):
            delay_ms = self.config.get("auto_advance_delay_ms", 100)
            self.waiting_to_advance = True

            display_field = self.get_display_field()
            extra_display = ""

            if display_field:
                extra_display = f"\nDisplay field: {display_field}"

            self.status_label.setText(
                f"Set {validation_field} = {validation_value}\n"
                f"FID: {fid}"
                f"{extra_display}\n"
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

        if self.index < len(self.feature_ids) - 1:
            self.index += 1
            self.show_current_feature()
        else:
            self.status_label.setText("Finished validation queue.")
            self.clear_highlight()

    def previous_feature(self):
        if self.waiting_to_advance:
            return

        if not self.feature_ids:
            return

        if self.index > 0:
            self.index -= 1
            self.show_current_feature()