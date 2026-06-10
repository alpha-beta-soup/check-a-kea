![](icon.png)

# Check-a-Kea

Check-a-Kea is a small QGIS plugin for fast manual polygon validation.

It lets you:

- choose a polygon layer
- jump through unvalidated polygons
- write configurable validation values to one attribute field
- use keyboard shortcuts such as `1`, `2`, and `3`
- view another selected attribute while validating
- move previous/next with arrow keys or buttons

## Setup

Your polygon layer needs a text field, usually called:

```text
validation
```

## Defualt shortcut values

```text
{
  "validation_field": "validation",
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

## Defualt shortcut values

1. Open Check-a-Kea from the QGIS plugin menu.
1. Select a polygon layer.
1. Choose an optional display attribute.
1. Click Start / refresh queue.
1. Press a shortcut key to validate the current polygon.
1. Save layer edits when finished.