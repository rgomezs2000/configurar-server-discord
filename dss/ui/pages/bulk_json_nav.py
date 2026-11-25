"""Utilidades para ubicar un bloque JSON por su ruta de origen."""
from __future__ import annotations

import json
import re


def clean_json_text(raw: str) -> str:
    """Quita BOM, vallas Markdown y texto alrededor del objeto JSON."""
    text = raw.lstrip("\ufeff").strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    return text.strip()


def load_clipboard_object(raw: str) -> dict:
    """Devuelve el objeto JSON del portapapeles o lanza ValueError."""
    text = clean_json_text(raw)
    if not text:
        raise ValueError("El portapapeles está vacío.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"JSON inválido: {error.msg} (línea {error.lineno}, "
            f"columna {error.colno}).") from error
    if not isinstance(data, dict):
        raise ValueError("Pega un objeto JSON, no una lista ni un valor suelto.")
    return data


def _skip_string(source: str, index: int) -> int:
    index += 1
    while index < len(source):
        char = source[index]
        if char == "\\":
            index += 2
            continue
        if char == '"':
            return index + 1
        index += 1
    return index


def find_array(source: str, key: str, start: int = 0, end: int | None = None) -> int | None:
    end = len(source) if end is None else end
    match = re.search(rf'"{re.escape(key)}"\s*:\s*\[', source[start:end])
    if not match:
        return None
    return start + match.end() - 1


def array_item(source: str, array_start: int, index: int) -> tuple[int, int] | None:
    count = 0
    depth = 0
    item_start = None
    position = array_start + 1
    while position < len(source):
        char = source[position]
        if char == '"':
            position = _skip_string(source, position)
            continue
        if char == "{":
            if depth == 0:
                item_start = position
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and item_start is not None:
                if count == index:
                    return item_start, position + 1
                count += 1
                item_start = None
        elif char == "]" and depth == 0:
            break
        position += 1
    return None


def source_block(source: str, path: str) -> tuple[int, int] | None:
    match = re.match(r"emojis\[(\d+)\]$", path)
    if match:
        array = find_array(source, "emojis")
        return array_item(source, array, int(match.group(1))) if array else None

    match = re.match(r"uncategorizedChannels\[(\d+)\]$", path)
    if match:
        array = find_array(source, "uncategorizedChannels")
        return array_item(source, array, int(match.group(1))) if array else None

    match = re.match(r"categories\[(\d+)\](?:\.channels\[(\d+)\])?$", path)
    if not match:
        return None
    categories = find_array(source, "categories")
    if categories is None:
        return None
    category = array_item(source, categories, int(match.group(1)))
    if category is None:
        return None
    if match.group(2) is None:
        return category
    channels = find_array(source, "channels", category[0], category[1])
    if channels is None:
        return None
    return array_item(source, channels, int(match.group(2)))
