"""Utilidades pequeñas y sin dependencias."""
from __future__ import annotations

import base64
import mimetypes
import os
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Iterator, Sequence, TypeVar

T = TypeVar("T")

MAX_ICON_BYTES = 8 * 1024 * 1024
MAX_EMOJI_BYTES = 256 * 1024
ALLOWED_IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

_CHANNEL_ALLOWED = set("abcdefghijklmnopqrstuvwxyz0123456789-_|")
_CHANNEL_INVALID_RUN = re.compile(r"-{2,}")


def _is_emoji_char(char: str) -> bool:
    code = ord(char)
    if (0x1F000 <= code <= 0x1FAFF or 0x2600 <= code <= 0x27BF
            or 0x2B00 <= code <= 0x2BFF or 0x1F1E6 <= code <= 0x1F1FF
            or 0x1F3FB <= code <= 0x1F3FF or 0xE0020 <= code <= 0xE007F
            or code in (0x200D, 0xFE0E, 0xFE0F, 0x20E3)):
        return True
    return unicodedata.category(char) == "So"


def normalize_channel_name(value: str, *, strip: bool = True,
                           keep_emoji: bool = False) -> str:
    """Convierte un nombre de canal al formato de Discord.

    Minúsculas, espacios a guiones, sin acentos y solo letras, números, guiones
    y el separador ``|``. Con ``keep_emoji`` conserva emojis Unicode; con
    ``strip=False`` no elimina guiones de los extremos.
    """
    text = unicodedata.normalize("NFKD", (value or "").strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace(" ", "-")
    if keep_emoji:
        text = "".join(ch for ch in text
                       if ch in _CHANNEL_ALLOWED or _is_emoji_char(ch))
    else:
        text = "".join(ch for ch in text if ch in _CHANNEL_ALLOWED)
    text = _CHANNEL_INVALID_RUN.sub("-", text)
    if strip:
        text = text.strip("-")
    return text


def human_size(size: int | float) -> str:
    value = float(size or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def truncate(text: str, limit: int = 60) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def chunks(items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    for index in range(0, len(items), size):
        yield items[index:index + size]


def plural(count: int, singular: str, plural_form: str) -> str:
    return f"{count} {singular if count == 1 else plural_form}"


def image_to_data_uri(path: str | os.PathLike[str], max_bytes: int = MAX_ICON_BYTES) -> str:
    """Convierte una imagen local en data URI base64 para la API de Discord."""
    file_path = Path(path)
    extension = file_path.suffix.lower()
    mime = ALLOWED_IMAGE_MIME.get(extension)
    if mime is None:
        raise ValueError("Formato no admitido. Usa PNG, JPG, GIF o WEBP.")
    size = file_path.stat().st_size
    if size > max_bytes:
        raise ValueError(f"La imagen pesa {human_size(size)} y el máximo es {human_size(max_bytes)}.")
    if size == 0:
        raise ValueError("El archivo está vacío.")
    encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def guess_mime(path: str) -> str:
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


def safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def normalize_ids(value: Iterable[object]) -> list[str]:
    return [str(item) for item in value]
