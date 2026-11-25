"""Caché de imágenes remotas para iconos de servidor y emojis.

Descarga en segundo plano y crea los ``PhotoImage`` en el hilo de Tk. Si algo
falla (red, formato), se devuelve ``None`` y la interfaz usa el respaldo dibujado.
"""
from __future__ import annotations

import base64
import tkinter as tk
import urllib.request
from typing import Any, Callable

from ..constants import USER_AGENT


class ImageCache:
    def __init__(self, app: Any):
        self._app = app
        self._cache: dict[tuple[str, int], tk.PhotoImage | None] = {}
        self._pending: set[tuple[str, int]] = set()
        self._waiters: dict[tuple[str, int], list[Callable[[tk.PhotoImage | None], None]]] = {}
        self.enabled = True

    def get(self, url: str | None, target: int = 48,
            callback: Callable[[tk.PhotoImage | None], None] | None = None) -> tk.PhotoImage | None:
        if not url or not self.enabled:
            if callback:
                self._app.root.after(0, callback, None)
            return None
        key = (url, target)
        if key in self._cache:
            photo = self._cache[key]
            if callback:
                self._app.root.after(0, callback, photo)
            return photo
        if key in self._pending:
            if callback:
                self._waiters.setdefault(key, []).append(callback)
            return None
        self._pending.add(key)
        if callback:
            self._waiters[key] = [callback]

        def work() -> bytes:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=12) as response:
                return response.read()

        def done(raw: bytes) -> None:
            self._pending.discard(key)
            photo = self._to_photo(raw, target)
            self._cache[key] = photo
            for waiter in self._waiters.pop(key, []):
                waiter(photo)

        def failed(_error: BaseException) -> None:
            self._pending.discard(key)
            # No se cachea el fallo: si la red se recupera, el siguiente refresco
            # vuelve a intentarlo y sustituye las iniciales por la imagen real.
            for waiter in self._waiters.pop(key, []):
                waiter(None)

        self._app.tasks.run(work, done, failed)
        return None

    def apply(self, widget: Any, url: str | None, size: int) -> None:
        """Carga ``url`` y la aplica con ``widget.set_photo``; si falla, deja el respaldo."""
        if not url:
            return

        def setter(photo: tk.PhotoImage | None) -> None:
            try:
                widget.set_photo(photo)
            except tk.TclError:
                pass

        cached = self.get(url, size, setter)
        if cached is not None:
            setter(cached)

    @staticmethod
    def _to_photo(raw: bytes, target: int) -> tk.PhotoImage | None:
        try:
            encoded = base64.b64encode(raw).decode("ascii")
            image = tk.PhotoImage(data=encoded)
        except (tk.TclError, ValueError):
            return None
        try:
            factor = max(1, (image.width() + max(1, target) - 1) // max(1, target))
            if factor > 1:
                image = image.subsample(factor)
        except tk.TclError:
            return image
        return image
