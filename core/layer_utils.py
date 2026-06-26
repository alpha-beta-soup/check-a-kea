from qgis.PyQt.QtCore import Qt
from qgis.core import QgsFeatureRequest, QgsLayerTree, QgsIconUtils, QgsVectorLayer

from .constants import KEY_UNVALIDATED_FILTER
from .utils import dim_icon


def get_feature_ids(layer, config):
    request = QgsFeatureRequest()
    filter_expression = config.get(KEY_UNVALIDATED_FILTER, "")
    if filter_expression:
        request.setFilterExpression(filter_expression)
    table_config = layer.attributeTableConfig()
    sort_expr = table_config.sortExpression()
    if sort_expr:
        ascending = table_config.sortOrder() == Qt.AscendingOrder
        request.addOrderBy(sort_expr, ascending)
        return [f.id() for f in layer.getFeatures(request)]
    return sorted(f.id() for f in layer.getFeatures(request))


def populate_layer_combo(combo, node, depth=0):
    indent = "  " * depth
    for child in node.children():
        if QgsLayerTree.isGroup(child):
            combo.addItem(f"{indent}▸ {child.name()}", None)
            item = combo.model().item(combo.count() - 1)
            if item:
                item.setEnabled(False)
            populate_layer_combo(combo, child, depth + 1)
        elif QgsLayerTree.isLayer(child):
            layer = child.layer()
            if layer is None:
                continue
            icon = QgsIconUtils.iconForLayer(layer)
            if not child.isVisible():
                icon = dim_icon(icon)
            if isinstance(layer, QgsVectorLayer):
                combo.addItem(icon, f"{indent}{layer.name()}", layer.id())
            else:
                combo.addItem(icon, f"{indent}{layer.name()}", None)
                item = combo.model().item(combo.count() - 1)
                if item:
                    item.setEnabled(False)
