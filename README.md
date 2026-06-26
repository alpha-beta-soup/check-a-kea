![](icon.png)

[![manaakiwhenua-standards](https://github.com/manaakiwhenua/check-a-kea/workflows/manaakiwhenua-standards/badge.svg)](https://github.com/manaakiwhenua/manaakiwhenua-standards)

# Check-a-Kea

Check-a-Kea is a QGIS plugin for fast human validation of spatial features.

It is designed for quickly stepping through features, assigning validation values using keyboard shortcuts, viewing supporting attribute information, and even writing associated comments.

It lets you:

- choose a vector layer to validate (e.g. a random sample of features, or just a layer with a filter)
- step through features
- write configurable validation values to one attribute field
- using keyboard shortcuts such as `1`, `2`, and `3`
- edit shortcut values from inside the plugin
- view other selected attributes while validating
- add optional free-text comments to a configurable comment field
- move previous/next using arrow keys
- auto-advance after each feature is validated

## Setup

Your layer needs a text field for validation values, usually called `validation`. If you want to use comments, your layer should also have a text field, usually called `comment`.

The validation field is used to store string values such as:

```text
true
false
maybe
```

## Default config

The plugin uses a configuration file, `config.json`, to control field names, queue filtering, shortcut values, zoom behaviour, and auto-advance timing.

You can edit this file manually, or from within QGIS using a button.

Default example:

```json
{
  "validation_field": "validation",
  "comment_field": "comment",
  "unvalidated_filter": "validation IS NULL OR validation = ''",
  "zoom_buffer_percent": 30,
  "auto_advance": true,
  "auto_advance_delay_ms": 100,
  "shortcuts": {
    "1": "true",
    "2": "false",
    "3": "maybe"
  }
}
```

You can set `unvalidated_filter` to an empty string so that features with a validated value are included (perhaps for inspection or re-validation). This option can also be used to filter based on some other attribute; the built-in layer filter will always also be respected. This can allow multiple validators to validate the same file while only being presented with those features that are assigned to them.

## Config options

| Option | Description |
|---|---|
| `validation_field` | Attribute field that receives the validation value. |
| `comment_field` | Attribute field that receives optional free-text comments. |
| `unvalidated_filter` | QGIS expression used to build the validation queue. |
| `zoom_buffer_percent` | Extra zoom padding around the current feature. |
| `auto_advance` | If `true`, the plugin moves to the next feature after a validation shortcut. |
| `auto_advance_delay_ms` | Delay in milliseconds before auto-advancing. |
| `shortcuts` | Keyboard shortcuts and the values they write to the validation field. |

## Usage

1. Open Check-a-Kea from the QGIS plugin menu.
2. Select a vector layer.
3. Click **Start / refresh queue**.
4. Select optional display attributes.
5. Review the current feature details.
6. Add an optional comment.
7. Press a shortcut key to validate the current feature.
8. Use **Previous** / **Next** or the left/right arrow keys to move manually.

NB users must manually save all layer edits when finished for them to be written to disk. This plugin edits the validation data using the built-in edit functionality.

NB the auto-identify option is useful for seeing the full set of layer attributes, and also those of coincident layers. To change the identify colour, go to **Settings** > **Options** > on the **Map Tools** tab > and on the **Identify** section you can change the highlight colour to any colour of your choice.

The **Summary** tab shows a bar chart of how many features currently hold each validation value across the whole layer, including unvalidated features. It updates after each shortcut press and when the queue is started or refreshed.

If you have the layer's attribute table open in the QGIS interface, the current feature will be kept in view (auto-scrolling). If you select a different row in the attribute table, the plugin will make that the active feature.

## Controls

Navigation shortcuts:

```text
Left Arrow  = Previous feature
Right Arrow = Next feature
```

Default validation shortcuts:

```text
1 = true
2 = false
3 = maybe
```

Buttons:

| Button | Description |
|---|---|
| **Start / refresh queue** | Builds the queue of features to validate. |
| **Edit config / shortcuts** | Opens the config editor inside QGIS. |
| **Reload config** | Reloads `config.json` after manual edits. |
| **Auto-identify** | Automatically "identifies" the current feature using the built-in identify tool. |

## Feature order and filtering

By default, Check-a-Kea steps through all features in the layer in their FID order; the same as the QGIS attribute table.

**Sort order:** if you sort the attribute table by a column, QGIS saves that sort on the layer. Check-a-Kea will then use it when building the queue, so the navigation order matches the attribute table.

**Layer filter:** if a permanent filter is set on the layer (via Layer Properties → Source), only matching features are included in the queue.

**Attribute table filter:** a temporary filter applied via the attribute table's filter bar is a view-only setting for the attribute table, and is not stored on the layer, so it cannot be reflected in the queue.

**Limiting to unvalidated features:** set `unvalidated_filter` in `config.json` to a QGIS expression, for example:

```json
"unvalidated_filter": "validation IS NULL OR validation = ''"
```

Leave it as an empty string to include all features.

## Notes

Check-a-Kea starts an edit session automatically if the selected layer is not already editable.

The plugin does not automatically commit/save the layer after every validation. This allows you to use normal QGIS edit workflows, including undo, save edits, or discard edits.

Comments are saved to the edit buffer 500 ms after typing (debounced). Like other edits, they still need to be saved manually to be written to disk.

**Remember to save your layer edits in QGIS!!**

## Development

Install dev dependencies (into your QGIS Python environment or a separate venv):

```bash
pip install -r requirements-dev.txt
```

Format code with [black](https://black.readthedocs.io):

```bash
black .
```

Run unit tests (no QGIS required):

```bash
pytest
```

Run integration tests (requires QGIS Python environment):

```bash
PYTHONPATH=/path/to/qgis/python /path/to/qgis/python/bin/pytest
```

On a typical Linux conda install this looks like:

```bash
PYTHONPATH=~/miniforge3/envs/qgis_latest/share/qgis/python \
  ~/miniforge3/envs/qgis_latest/bin/pytest
```

For translation workflows, see [i18n/README.md](i18n/README.md).
