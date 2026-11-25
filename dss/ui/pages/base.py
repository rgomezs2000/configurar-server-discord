"""Base común de las páginas del panel."""
from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

from ...constants import PERMISSION_BY_KEY
from ...errors import DiscordError
from ..theme import C


class Page(tk.Frame):
    key = ""
    label = ""
    glyph = "▤"
    permission: str | None = None

    def __init__(self, master: tk.Misc, app: Any):
        super().__init__(master, bg=C.CONTENT)
        self.app = app
        self._loaded = False
        self.build()

    # -- ciclo de vida ------------------------------------------------------ #
    def build(self) -> None:
        raise NotImplementedError

    def on_show(self, **kwargs: Any) -> None:
        if not self._loaded:
            self._loaded = True
            self.refresh()

    def on_guild_refreshed(self) -> None:
        pass

    def refresh(self) -> None:
        pass

    # -- sincronización automática ----------------------------------------- #
    def is_dirty(self) -> bool:
        """True si hay cambios sin guardar que la sincronización no debe pisar."""
        return False

    def live_refresh(self) -> None:
        """Refresco periódico de la página visible."""
        self.refresh()

    def invalidate(self) -> None:
        """Marca la página como obsoleta para que se recargue al mostrarse."""
        self._loaded = False

    # -- ayudas ------------------------------------------------------------- #
    def can(self, permission_key: str) -> bool:
        return self.app.can(permission_key)

    def require(self, permission_key: str, action: str = "hacer esto") -> bool:
        if self.app.can(permission_key):
            return True
        label = PERMISSION_BY_KEY.get(permission_key, (permission_key,))[0]
        human = PERMISSION_BY_KEY.get(permission_key)
        name = human[3] if human else label
        self.app.toasts.show(f"No puedes {action}: falta el permiso «{name}».", "warning")
        return False

    def run(self, func: Callable[[], Any], on_done: Callable[[Any], None] | None = None,
            on_error: Callable[[BaseException], None] | None = None) -> None:
        self.app.run_task(func, on_done, on_error)

    def error(self, exc: BaseException) -> None:
        self.app.report_error(exc)

    def toast_ok(self, message: str) -> None:
        self.app.toasts.show(message, "success")

    def toast_warn(self, message: str) -> None:
        self.app.toasts.show(message, "warning")
