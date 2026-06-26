from qgis.core import NULL as QGIS_NULL, QgsFeatureRequest


class ValidationSession:
    """Holds state for a single validation run on one layer."""

    def __init__(self, layer, feature_ids):
        self.layer = layer
        self.feature_ids = feature_ids
        self._fid_to_index = {fid: i for i, fid in enumerate(feature_ids)}
        self.index = 0
        self.waiting_to_advance = False

    def index_of(self, fid):
        """Return the queue index for a given FID, or None if not in queue."""
        return self._fid_to_index.get(fid)

    @property
    def current_fid(self):
        return self.feature_ids[self.index]

    def current_feature(self):
        return next(self.layer.getFeatures(QgsFeatureRequest(self.current_fid)), None)

    def write_validation(self, field_name, value):
        """Write value to field_name for the current feature.

        Raises ValueError if the field does not exist.
        Returns True if the write succeeded, False otherwise.
        """
        field_index = self.layer.fields().indexOf(field_name)
        if field_index == -1:
            raise ValueError(field_name)
        if not self.layer.isEditable():
            self.layer.startEditing()
        return self.layer.changeAttributeValue(self.current_fid, field_index, value)

    def validation_counts(self, field_name):
        """Return {value_or_None: count} for all features in the layer."""
        counts = {}
        for feature in self.layer.getFeatures():
            value = feature[field_name]
            key = None if (value is None or value == QGIS_NULL) else str(value)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def navigate(self, delta):
        """Move by delta. Returns True on success, False at boundary."""
        new_index = self.index + delta
        if 0 <= new_index < len(self.feature_ids):
            self.index = new_index
            return True
        return False

    def clamp_index(self):
        self.index = max(0, min(self.index, len(self.feature_ids) - 1))

    def __len__(self):
        return len(self.feature_ids)
