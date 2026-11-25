"""Resaltado JSON compartido por Roles, Canales y Emojis."""
from __future__ import annotations

import re
import tkinter as tk
from typing import Any

JSON_TAGS = ("key", "string", "number", "bool", "null")
JSON_COLORS = {
    "key": "#7aa2f7",
    "string": "#9ece6a",
    "number": "#ff9e64",
    "bool": "#bb9af7",
    "null": "#f7768e",
}
_JSON_PATTERN = re.compile(
    r'("(?:\\.|[^"\\])*")(\s*:)?'
    r'|(-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)'
    r'|\b(true|false|null)\b'
)


def configure_json_tags(text: tk.Text, theme: Any) -> None:
    for tag, color in JSON_COLORS.items():
        text.tag_configure(tag, foreground=color)
    text.tag_configure("key", font=(theme.mono_family, 9, "bold"))
    text.tag_configure("op_focus", background="#333a66", foreground="#c0caf5")


def highlight_json(text: tk.Text) -> None:
    for tag in JSON_TAGS:
        text.tag_remove(tag, "1.0", "end")
    source = text.get("1.0", "end-1c")
    for match in _JSON_PATTERN.finditer(source):
        start = f"1.0+{match.start()}c"
        end = f"1.0+{match.end()}c"
        if match.group(1):
            tag = "key" if match.group(2) else "string"
            end = f"1.0+{match.end(1)}c"
        elif match.group(3):
            tag = "number"
        else:
            tag = "bool" if match.group(4) in ("true", "false") else "null"
        text.tag_add(tag, start, end)
