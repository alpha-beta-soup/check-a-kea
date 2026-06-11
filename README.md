![](icon.png)

# Check-a-Kea

Check-a-Kea is a small QGIS plugin for fast manual polygon validation.

It is designed for quickly stepping through polygon features, assigning validation values with keyboard shortcuts, viewing supporting attribute information, and optionally writing comments for each polygon.

It lets you:

- choose a polygon layer
- jump through unvalidated polygons
- write configurable validation values to one attribute field
- use keyboard shortcuts such as `1`, `2`, and `3`
- edit shortcut values from inside the plugin using **Edit config / shortcuts**
- view another selected attribute while validating
- show the current validation value and selected display attribute in bold
- add optional free-text comments to a configurable comment field
- move previous/next with arrow keys or buttons
- use an optional auto-advance delay after each validation shortcut

## Setup

Your polygon layer needs a text field for validation values, usually called:

```text
validation
```

If you want to use comments, your polygon layer should also have a text field, usually called:

```text
comment
```

The validation field is used to store values such as:

```text
true
false
maybe
```

The comment field is optional. If the configured comment field does not exist, validation will still work, but comments will not be saved.

## Default config

The plugin uses `config.json` to control field names, queue filtering, shortcut values, zoom behaviour, and auto-advance timing.

You can edit this file manually, or from inside QGIS using:

```text
Edit config / shortcuts
```

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

## Config options

| Option | Description |
|---|---|
| `validation_field` | Attribute field that receives the validation value. |
| `comment_field` | Attribute field that receives optional free-text comments. |
| `unvalidated_filter` | QGIS expression used to build the validation queue. |
| `zoom_buffer_percent` | Extra zoom padding around the current polygon. |
| `auto_advance` | If `true`, the plugin moves to the next polygon after a validation shortcut. |
| `auto_advance_delay_ms` | Delay in milliseconds before auto-advancing. |
| `shortcuts` | Keyboard shortcuts and the values they write to the validation field. |

## Usage

1. Open Check-a-Kea from the QGIS plugin menu.
2. Select a polygon layer.
3. Click **Start / refresh queue**.
4. Choose an optional display attribute.
5. Review the current polygon details.
6. Add an optional comment.
7. Press a shortcut key to validate the current polygon.
8. Use **Previous** / **Next** or the left/right arrow keys to move manually.
9. Save layer edits when finished.

## Controls

Default validation shortcuts:

```text
1 = true
2 = false
3 = maybe
```

Navigation shortcuts:

```text
Left Arrow  = Previous polygon
Right Arrow = Next polygon
```

Buttons:

| Button | Description |
|---|---|
| **Refresh layer list** | Refreshes the available polygon layers. |
| **Start / refresh queue** | Builds the queue of polygons to validate. |
| **Previous** | Moves to the previous polygon. |
| **Next** | Moves to the next polygon. |
| **Save comment** | Saves the current comment to the configured comment field. |
| **Edit config / shortcuts** | Opens the config editor inside QGIS. |
| **Reload config** | Reloads `config.json` after manual edits. |

## Notes

Check-a-Kea starts an edit session automatically if the selected layer is not already editable.

The plugin does not automatically commit/save the layer after every validation. This allows you to use normal QGIS edit workflows, including undo, save edits, or discard edits.

**Remember to save your layer edits in QGIS!!**
