import json
from html import escape
from pathlib import Path

from qgis.PyQt.QtWidgets import (
    QAction,
    QApplication,
    QDialog,
    QShortcut,
    QAbstractItemView,
    QTableWidgetItem,
)
from qgis.PyQt.QtGui import QIcon, QKeySequence, QMouseEvent
from qgis.PyQt.QtCore import Qt, QTimer, QEvent, QPoint, QCoreApplication

import sip  # type: ignore  # QGIS runtime dependency, not resolvable by static analysers

from qgis.core import QgsProject, NULL as QGIS_NULL
from qgis.gui import QgsHighlight, QgsAttributeTableFilterModel

from .core.constants import (
    KEY_VALIDATION_FIELD,
    KEY_COMMENT_FIELD,
    KEY_ZOOM_BUFFER,
    KEY_AUTO_ADVANCE,
    KEY_AUTO_ADVANCE_DELAY,
    KEY_SHORTCUTS,
)
from .core.dock import DockMixin
from .core.layer_utils import get_feature_ids, populate_layer_combo
from .core.rendering import kbd_table
from .core.session import ValidationSession
from .core.utils import tr
from .core.widgets import JsonConfigDialog


class CheckAKea(DockMixin):

    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()

        self.action = None
        self.dock = None

        self.layer_combo = None
        self.field_checklist = None
        self.attribute_table = None
        self.checked_fields = set()
        self.status_label = None
        self.footer_label = None
        self.auto_identify_button = None

        self.validation_controls_widget = None
        self.comment_box = None
        self._comment_save_timer = None
        self.auto_identify = False

        self.session = None
        self._programmatic_selection = False

        self.histogram_widget = None

        self.highlight = None
        self.shortcuts = []
        self._focus_guard = None

        self.plugin_dir = Path(__file__).parent
        self.config_path = self.plugin_dir / "config.json"
        self.config = self.load_config()

        self._translator = None
        self._load_translator()

    # ------------------------------------------------------------------ config

    def load_config(self):
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        if KEY_COMMENT_FIELD not in config:
            config[KEY_COMMENT_FIELD] = "comment"
        return config

    def save_config(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)

    def _load_translator(self):
        from qgis.PyQt.QtCore import QTranslator, QSettings

        locale = QSettings().value("locale/userLocale", "en")[0:2]
        qm_path = self.plugin_dir / "i18n" / f"check_a_kea_{locale}.qm"
        if qm_path.exists():
            self._translator = QTranslator()
            self._translator.load(str(qm_path))
            QCoreApplication.installTranslator(self._translator)

    # ------------------------------------------------------------------ plugin lifecycle

    def initGui(self):
        icon_path = self.plugin_dir / "icon.png"
        if icon_path.exists():
            self.action = QAction(
                QIcon(str(icon_path)), "Check-a-Kea", self.iface.mainWindow()
            )
        else:
            self.action = QAction("Check-a-Kea", self.iface.mainWindow())
        self.action.triggered.connect(self.show_dock)
        self.iface.addPluginToMenu("&Check-a-Kea", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self._comment_save_timer is not None:
            self._comment_save_timer.stop()
        if self._translator:
            QCoreApplication.removeTranslator(self._translator)
            self._translator = None
        if self._focus_guard:
            QApplication.instance().removeEventFilter(self._focus_guard)
            self._focus_guard = None
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

    # ------------------------------------------------------------------ UI state

    def set_validation_controls_visible(self, visible):
        if self.validation_controls_widget is not None:
            self.validation_controls_widget.setVisible(visible)
        if not visible and self.footer_label is not None:
            self.footer_label.setText("")

    # ------------------------------------------------------------------ config actions

    def open_config_dialog(self):
        dialog = JsonConfigDialog(self.config, self.iface.mainWindow())
        if dialog.exec_() != QDialog.Accepted:
            return
        self.config = dialog.config
        self.save_config()
        self.reload_config()
        if self.status_label:
            self.status_label.setText(tr("Config saved and reloaded."))

    def reload_config(self):
        self.config = self.load_config()
        self.register_shortcuts()
        self.refresh_field_checklist()
        if self.session:
            self.session.waiting_to_advance = False
        if self.status_label:
            delay_ms = self.config.get(KEY_AUTO_ADVANCE_DELAY, 100)
            self.status_label.setText(
                tr("Config reloaded.")
                + "<br>"
                + tr("Auto-advance delay: {} ms").format(delay_ms)
            )

    # ------------------------------------------------------------------ layer combo

    def refresh_layer_combo(self):
        if self.layer_combo is None:
            return
        current_layer_id = self.layer_combo.currentData()
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        populate_layer_combo(self.layer_combo, QgsProject.instance().layerTreeRoot())
        restored = False
        if current_layer_id:
            index = self.layer_combo.findData(current_layer_id)
            if index >= 0:
                self.layer_combo.setCurrentIndex(index)
                restored = True
        self.layer_combo.blockSignals(False)
        if current_layer_id and not restored:
            self.clear_active_queue()
            self.refresh_field_checklist()
            if self.status_label:
                self.status_label.setText(
                    tr(
                        "Active layer was removed. Choose a layer, then start the queue."
                    )
                )

    def layer_selection_changed(self):
        self.clear_active_queue()
        self.refresh_field_checklist()
        if self.status_label:
            self.status_label.setText(
                tr("Layer changed. Click Start / refresh queue to begin.")
            )

    # ------------------------------------------------------------------ field checklist

    def refresh_field_checklist(self):
        if self.field_checklist is None:
            return
        layer_id = self.layer_combo.currentData() if self.layer_combo else None
        layer = QgsProject.instance().mapLayer(layer_id)
        try:
            self.field_checklist.model().itemChanged.disconnect(
                self._on_checklist_changed
            )
        except TypeError:
            pass
        self.field_checklist.clear()
        if layer:
            layer_field_names = {f.name() for f in layer.fields()}
            self.checked_fields &= layer_field_names
            for field in layer.fields():
                self.field_checklist.add_check_item(
                    field.name(), checked=field.name() in self.checked_fields
                )
        self.field_checklist.model().itemChanged.connect(self._on_checklist_changed)
        self.field_checklist.update_display()
        self.refresh_attribute_table()

    def _on_checklist_changed(self, item):
        if item.checkState() == Qt.Checked:
            self.checked_fields.add(item.text())
        else:
            self.checked_fields.discard(item.text())
        self.field_checklist.update_display()
        self.refresh_attribute_table()

    # ------------------------------------------------------------------ attribute table

    def refresh_attribute_table(self, feature=None):
        if self.attribute_table is None:
            return
        self.attribute_table.setRowCount(0)
        if not self.session:
            return
        if feature is None:
            feature = self.session.current_feature()
            if feature is None:
                return
        fields_to_show = [
            f for f in self.session.layer.fields() if f.name() in self.checked_fields
        ]
        self.attribute_table.setRowCount(len(fields_to_show))
        for row, field in enumerate(fields_to_show):
            value = feature[field.name()]
            value_str = "" if (value is None or value == QGIS_NULL) else str(value)
            self.attribute_table.setItem(row, 0, QTableWidgetItem(field.name()))
            self.attribute_table.setItem(row, 1, QTableWidgetItem(value_str))
        self.attribute_table.resizeRowsToContents()

    # ------------------------------------------------------------------ shortcuts

    def register_shortcuts(self):
        self.clear_shortcuts()
        all_shortcuts = [
            (QKeySequence(key), lambda k=key: self.apply_validation(k))
            for key in self.config[KEY_SHORTCUTS]
        ] + [
            (QKeySequence(Qt.Key_Left), self.previous_feature),
            (QKeySequence(Qt.Key_Right), self.next_feature),
        ]
        for sequence, handler in all_shortcuts:
            shortcut = QShortcut(sequence, self.iface.mainWindow())
            shortcut.setContext(Qt.ApplicationShortcut)
            shortcut.activated.connect(handler)
            self.shortcuts.append(shortcut)

    def clear_shortcuts(self):
        for shortcut in self.shortcuts:
            shortcut.setParent(None)
            shortcut.deleteLater()
        self.shortcuts = []

    # ------------------------------------------------------------------ validation queue

    def _connect_selection_signal(self):
        self.session.layer.selectionChanged.connect(self._on_layer_selection_changed)

    def _disconnect_selection_signal(self):
        if self.session:
            try:
                self.session.layer.selectionChanged.disconnect(
                    self._on_layer_selection_changed
                )
            except TypeError:
                pass

    def _on_layer_selection_changed(self, selected_ids, *_):
        if self._programmatic_selection or not self.session:
            return
        if len(selected_ids) != 1:
            return
        fid = selected_ids[0]
        new_index = self.session.index_of(fid)
        if new_index is None:
            return
        self.session.index = new_index
        self.show_current_feature()

    def clear_active_queue(self):
        self._disconnect_selection_signal()
        self.session = None
        self.clear_highlight()
        self.clear_comment_box()
        self.set_validation_controls_visible(False)

    def start_validation(self):
        layer_id = self.layer_combo.currentData()
        layer = QgsProject.instance().mapLayer(layer_id)

        if not layer:
            self.status_label.setText(tr("No valid layer selected."))
            self.set_validation_controls_visible(False)
            return

        validation_field = self.config[KEY_VALIDATION_FIELD]
        if validation_field not in [f.name() for f in layer.fields()]:
            self.status_label.setText(
                tr("Field '{}' does not exist in this layer.").format(
                    escape(validation_field)
                )
                + "<br>"
                + tr("Add it as a Text/String field first.")
            )
            self.set_validation_controls_visible(False)
            return

        if not layer.isEditable():
            layer.startEditing()

        feature_ids = get_feature_ids(layer, self.config)
        if not feature_ids:
            self.status_label.setText(tr("No features found for validation."))
            self.clear_highlight()
            self.clear_comment_box()
            self.set_validation_controls_visible(False)
            return

        self.session = ValidationSession(layer, feature_ids)
        self._connect_selection_signal()
        self.refresh_field_checklist()
        self.set_validation_controls_visible(True)
        self.show_current_feature()

    def refresh_histogram(self):
        if not self.session or self.histogram_widget is None:
            return
        counts = self.session.validation_counts(self.config[KEY_VALIDATION_FIELD])
        self.histogram_widget.update_data(counts)

    # ------------------------------------------------------------------ feature display

    def show_current_feature(self):
        if not self.session:
            return
        self.session.clamp_index()
        feature = self.session.current_feature()
        if feature is None:
            self.status_label.setText(tr("Could not load feature."))
            return

        fid = self.session.current_fid
        self._programmatic_selection = True
        self.session.layer.selectByIds([fid])
        self._programmatic_selection = False
        QTimer.singleShot(0, self._scroll_attribute_table_to_selection)
        self.zoom_to_feature(feature)
        self.highlight_feature(feature)
        self.load_comment_for_feature(feature)
        if self.auto_identify:
            self._auto_identify_feature(feature)
        self.refresh_attribute_table(feature)

        validation_field = self.config[KEY_VALIDATION_FIELD]
        current_value = feature[validation_field]
        active_value = (
            None
            if (current_value is None or current_value == QGIS_NULL)
            else str(current_value)
        )

        self.footer_label.setText(
            f'<table width="100%"><tr>'
            f'<td>{tr("Feature {} of {}").format(self.session.index + 1, len(self.session))}</td>'
            f'<td align="right">FID: {fid}</td>'
            f"</tr></table>"
        )
        self.status_label.setText(
            f"<h4 style='margin: 4px 0;'>{tr('Validation shortcuts')}</h4>"
            f"{kbd_table(list(self.config[KEY_SHORTCUTS].items()), active_value=active_value)}"
        )

    def _scroll_attribute_table_to_selection(self):
        if not self.session:
            return
        fid = self.session.current_fid
        for widget in QApplication.instance().allWidgets():
            if not hasattr(widget, "model") or not hasattr(widget, "scrollTo"):
                continue
            try:
                raw = widget.model()
                if raw is None:
                    continue
                if raw.metaObject().className() != "QgsAttributeTableFilterModel":
                    continue
                model = sip.wrapinstance(
                    sip.unwrapinstance(raw), QgsAttributeTableFilterModel
                )
                if model.layer().id() != self.session.layer.id():
                    continue
                index = model.fidToIndex(fid)
                if index.isValid():
                    widget.scrollTo(index, QAbstractItemView.PositionAtCenter)
            except Exception:
                pass

    # ------------------------------------------------------------------ identify

    def _on_auto_identify_toggled(self, checked):
        self.auto_identify = checked
        if checked and self.session:
            feature = self.session.current_feature()
            if feature:
                self._auto_identify_feature(feature)

    def _auto_identify_feature(self, feature):
        if not self.session or feature is None:
            return
        geom = feature.geometry()
        if geom is None or geom.isNull():
            return
        canvas = self.iface.mapCanvas()
        map_point = geom.pointOnSurface().asPoint()
        ct = canvas.getCoordinateTransform()
        canvas_pt = ct.transform(map_point.x(), map_point.y())
        qpoint = QPoint(int(canvas_pt.x()), int(canvas_pt.y()))
        self.iface.actionIdentify().trigger()
        viewport = canvas.viewport()
        QApplication.sendEvent(
            viewport,
            QMouseEvent(
                QEvent.MouseButtonPress,
                qpoint,
                Qt.LeftButton,
                Qt.LeftButton,
                Qt.NoModifier,
            ),
        )
        QApplication.sendEvent(
            viewport,
            QMouseEvent(
                QEvent.MouseButtonRelease,
                qpoint,
                Qt.LeftButton,
                Qt.LeftButton,
                Qt.NoModifier,
            ),
        )

    # ------------------------------------------------------------------ zoom / highlight

    def zoom_to_feature(self, feature):
        geom = feature.geometry()
        if geom is None or geom.isEmpty():
            return
        extent = geom.boundingBox()
        buffer_percent = self.config.get(KEY_ZOOM_BUFFER, 30)
        extent.scale(1 + buffer_percent / 100)
        self.canvas.setExtent(extent)
        self.canvas.refresh()

    def highlight_feature(self, feature):
        self.clear_highlight()
        self.highlight = QgsHighlight(
            self.canvas, feature.geometry(), self.session.layer
        )
        self.highlight.setWidth(3)
        self.highlight.show()

    def clear_highlight(self):
        if self.highlight:
            self.highlight.hide()
            self.highlight = None

    # ------------------------------------------------------------------ comment

    def load_comment_for_feature(self, feature):
        if self.comment_box is None:
            return
        comment_field = self.config.get(KEY_COMMENT_FIELD, "comment")
        field_index = self.session.layer.fields().indexOf(comment_field)
        self.comment_box.blockSignals(True)
        if field_index == -1:
            self.comment_box.setPlainText("")
            self.comment_box.setEnabled(False)
            self.comment_box.setPlaceholderText(
                tr("Comment field '{}' does not exist.").format(comment_field)
            )
        else:
            comment_value = feature[comment_field]
            self.comment_box.setPlainText(
                ""
                if (comment_value is None or comment_value == QGIS_NULL)
                else str(comment_value)
            )
            self.comment_box.setEnabled(True)
            self.comment_box.setPlaceholderText(
                tr("Write an optional comment for this feature...")
            )
        self.comment_box.blockSignals(False)

    def clear_comment_box(self):
        if self.comment_box is None:
            return
        self.comment_box.blockSignals(True)
        self.comment_box.setPlainText("")
        self.comment_box.blockSignals(False)

    def save_comment_for_current_feature(self):
        if not self.session or self.comment_box is None:
            return
        comment_field = self.config.get(KEY_COMMENT_FIELD, "comment")
        field_index = self.session.layer.fields().indexOf(comment_field)
        if field_index == -1:
            return
        fid = self.session.current_fid
        comment_text = self.comment_box.toPlainText()
        comment_value = comment_text if comment_text else None
        if not self.session.layer.isEditable():
            self.session.layer.startEditing()
        self.session.layer.changeAttributeValue(fid, field_index, comment_value)

    # ------------------------------------------------------------------ navigation

    def apply_validation(self, key):
        if not self.session or self.session.waiting_to_advance:
            return
        if key not in self.config[KEY_SHORTCUTS]:
            return

        validation_value = self.config[KEY_SHORTCUTS][key]
        validation_field = self.config[KEY_VALIDATION_FIELD]

        try:
            success = self.session.write_validation(validation_field, validation_value)
        except ValueError:
            self.status_label.setText(
                tr("Field '{}' does not exist.").format(escape(validation_field))
            )
            return
        if not success:
            self.status_label.setText(
                tr("Could not write '{}' to feature {}.").format(
                    escape(validation_value), self.session.current_fid
                )
            )
            return

        self.save_comment_for_current_feature()

        if self.config.get(KEY_AUTO_ADVANCE, True):
            delay_ms = self.config.get(KEY_AUTO_ADVANCE_DELAY, 100)
            self.session.waiting_to_advance = True
            QTimer.singleShot(delay_ms, self.advance_after_delay)
        else:
            self.show_current_feature()

    def advance_after_delay(self):
        if self.session:
            self.session.waiting_to_advance = False
        self.next_feature()

    def _navigate(self, delta):
        if not self.session or self.session.waiting_to_advance:
            return
        self.save_comment_for_current_feature()
        if self.session.navigate(delta):
            self.show_current_feature()
        elif delta > 0:
            self.clear_active_queue()
            self.status_label.setText(tr("Finished validation queue."))

    def next_feature(self):
        self._navigate(1)

    def previous_feature(self):
        self._navigate(-1)
