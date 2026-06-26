from html import escape


def kbd_table(rows, active_value=None):
    KBD = (
        "background-color: #f0f0f0;"
        "border: 1px solid #aaaaaa;"
        "padding: 2px 7px;"
        "font-family: monospace;"
        "font-weight: bold;"
    )
    cells = "".join(
        f"<tr>"
        f'<td style="text-align: center; vertical-align: middle; font-size: 7px; color: '
        f'{"black" if active_value is not None and str(value) == active_value else "transparent"}'
        f';">&#9679;</td>'
        f'<td align="center" style="{KBD}">{escape(str(key))}</td>'
        f'<td style="padding: 2px 6px;">{escape(str(value))}</td>'
        f"</tr>"
        for key, value in rows
    )
    return f'<table cellspacing="3" cellpadding="0">{cells}</table>'
