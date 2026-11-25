"""Selector de servidor: se muestra al iniciar sesión y al cambiar de servidor."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from ..constants import APP_NAME
from ..models import GuildSummary
from ..util import plural
from .theme import C
from .widgets import (Avatar, Card, GuildTile, SearchEntry, ScrollFrame,
                      Tooltip, copy_to_clipboard)


class GuildCard(tk.Frame):
    def __init__(self, parent: tk.Misc, summary: GuildSummary, app: Any,
                 command: Any):
        super().__init__(parent, bg=C.CARD, highlightbackground=C.BORDER_SOFT,
                         highlightthickness=1, cursor="hand2")
        self.summary = summary
        self._command = command
        self._bg = C.CARD
        top = tk.Frame(self, bg=C.CARD)
        top.pack(fill="x", padx=16, pady=(16, 10))
        self.tile = GuildTile(top, summary.name, 54, bg=C.CARD, command=command)
        self.tile.pack(side="left")
        app.images.apply(self.tile, summary.icon_url, 54)
        info = tk.Frame(top, bg=C.CARD)
        info.pack(side="left", fill="x", expand=True, padx=(12, 0))
        self.name_label = tk.Label(info, text=summary.name, bg=C.CARD, fg=C.TEXT,
                                   font=app.theme.font(12, "bold"), anchor="w",
                                   cursor="hand2")
        self.name_label.pack(fill="x")
        meta = []
        if summary.member_count:
            meta.append(plural(summary.member_count, "miembro", "miembros"))
        meta.append(summary.access_label)
        bot_missing = bool(getattr(app, "bot_guild_ids_known", False)) \
            and summary.id not in app.bot_guild_ids
        if bot_missing:
            meta.append("falta el bot")
        self.meta_label = tk.Label(info, text=" · ".join(meta) or "Sin datos de acceso",
                                   bg=C.CARD, fg=C.YELLOW if bot_missing else C.MUTED,
                                   font=app.theme.font(9), anchor="w", cursor="hand2")
        self.meta_label.pack(fill="x", pady=(3, 0))
        self.arrow = tk.Label(top, text="→", bg=C.CARD, fg=C.FAINT,
                              font=app.theme.font(14, "bold"), cursor="hand2")
        self.arrow.pack(side="right")

        chips = tk.Frame(self, bg=C.CARD)
        chips.pack(fill="x", padx=16, pady=(0, 14))
        features = [f for f in summary.features if f in ("COMMUNITY", "VERIFIED",
                                                         "PARTNERED", "DISCOVERABLE",
                                                         "BANNER", "NEWS")][:3]
        labels = {"COMMUNITY": "Comunidad", "VERIFIED": "Verificado",
                  "PARTNERED": "Socio", "DISCOVERABLE": "Descubrible",
                  "BANNER": "Banner", "NEWS": "Anuncios"}
        for feature in features:
            tk.Label(chips, text=labels.get(feature, feature), bg=C.CARD_ALT,
                     fg=C.DIM, font=app.theme.font(8), padx=7, pady=2).pack(
                side="left", padx=(0, 6))
        if not features:
            tk.Label(chips, text="Servidor", bg=C.CARD_ALT, fg=C.DIM,
                     font=app.theme.font(8), padx=7, pady=2).pack(side="left")

        for widget in self._walk(self):
            widget.bind("<Button-1>", lambda _e: self._command())
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

    def _walk(self, widget: tk.Misc):
        yield widget
        for child in widget.winfo_children():
            yield from self._walk(child)

    def _paint(self, bg: str, fg: str = C.TEXT) -> None:
        self._bg = bg
        self.configure(bg=bg, highlightbackground=C.ACCENT if bg == C.CARD_ALT else C.BORDER_SOFT)
        for widget in self._walk(self):
            if widget is self:
                continue
            if isinstance(widget, GuildTile):
                widget.set_bg(bg)
            else:
                try:
                    widget.configure(bg=bg)
                except tk.TclError:
                    pass
        self.name_label.configure(bg=bg, fg=fg)
        self.meta_label.configure(bg=bg)
        self.arrow.configure(bg=bg, fg=C.DIM if bg == C.CARD_ALT else C.FAINT)
        for chip in self.winfo_children()[-1].winfo_children():
            chip.configure(bg=C.CARD_ALT if bg == C.CARD else C.BORDER)

    def _on_enter(self, _event: Any = None) -> None:
        self._paint(C.CARD_ALT)

    def _on_leave(self, _event: Any = None) -> None:
        self._paint(C.CARD)


class GuildPickerView(tk.Frame):
    """Pantalla para elegir servidor tras el login."""

    def __init__(self, master: tk.Misc, app: Any):
        super().__init__(master, bg=C.CONTENT)
        self.app = app
        self._cards: list[GuildCard] = []
        self._columns = 3
        self._relayout_after: str | None = None
        self._build()

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        app = self.app
        bar = tk.Frame(self, bg=C.SIDEBAR, height=64)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        brand = tk.Frame(bar, bg=C.SIDEBAR)
        brand.pack(side="left", padx=20)
        tk.Label(brand, text="DSS", bg=C.ACCENT, fg=C.WHITE,
                 font=app.theme.font(9, "bold"), padx=8, pady=4).pack(side="left")
        tk.Label(brand, text=APP_NAME, bg=C.SIDEBAR, fg=C.TEXT,
                 font=app.theme.font(11, "bold")).pack(side="left", padx=(10, 0))

        right = tk.Frame(bar, bg=C.SIDEBAR)
        right.pack(side="right", padx=18)
        chip = tk.Frame(right, bg=C.SIDEBAR)
        chip.pack(side="left", padx=(0, 12))
        self.user_avatar = Avatar(chip, app.user.display_name if app.user else "?", 30,
                                  bg=C.SIDEBAR, theme=app.theme)
        self.user_avatar.pack(side="left")
        text = tk.Frame(chip, bg=C.SIDEBAR)
        text.pack(side="left", padx=(8, 0))
        self.user_text = text
        self.user_name_label = tk.Label(
            text, text=app.user.display_name if app.user else "Sesión",
            bg=C.SIDEBAR, fg=C.TEXT, font=app.theme.font(9, "bold"), anchor="w")
        self.user_name_label.pack(fill="x")
        kind_label = {"bot": "Aplicación (bot)", "user": "Cuenta de usuario",
                      "oauth": "Cuenta (OAuth)", "demo": "Demostración"}.get(
            app.session_kind, "Sesión")
        tk.Label(text, text=kind_label, bg=C.SIDEBAR, fg=C.MUTED,
                 font=app.theme.font(8), anchor="w").pack(fill="x")
        self.nitro_label: tk.Label | None = None
        self.update_user(app.user)
        self.live_label = tk.Label(right, text="○ Manual · F5", bg=C.SIDEBAR, fg=C.FAINT,
                                   font=app.theme.font(8, "bold"))
        self.live_label.pack(side="left", padx=(0, 10))
        Tooltip(self.live_label,
                "Actualización manual: usa «Actualizar» o F5. El sondeo automático está "
                "desactivado.")
        ttk.Button(right, text="Actualizar", style="Ghost.TButton",
                   command=self.app.refresh_guilds).pack(side="left", padx=(0, 8))
        ttk.Button(right, text="Cerrar sesión", style="Ghost.TButton",
                   command=self.app.logout).pack(side="left")
        self.set_live_status(getattr(app, "live_status", "off"))

        body = tk.Frame(self, bg=C.CONTENT)
        body.pack(fill="both", expand=True)
        self.scroll = ScrollFrame(body, bg=C.CONTENT)
        self.scroll.pack(fill="both", expand=True)

        header = tk.Frame(self.scroll.inner, bg=C.CONTENT)
        header.pack(fill="x", padx=36, pady=(30, 6))
        titles = tk.Frame(header, bg=C.CONTENT)
        titles.pack(side="left", fill="x", expand=True)
        tk.Label(titles, text="Elige un servidor", bg=C.CONTENT, fg=C.TEXT,
                 font=app.theme.font(24, "bold"), anchor="w").pack(fill="x")
        self.subtitle_label = tk.Label(titles, text=self._summary_text(),
                                       bg=C.CONTENT, fg=C.MUTED,
                                       font=app.theme.font(10), anchor="w")
        self.subtitle_label.pack(fill="x", pady=(4, 0))

        filters = tk.Frame(header, bg=C.CONTENT)
        filters.pack(side="right", anchor="s", padx=(20, 0))
        self.search = SearchEntry(filters, placeholder="Filtrar servidores…",
                                  on_change=lambda _t: self._render_cards(),
                                  width=26, bg=C.CONTENT, theme=app.theme)
        self.search.pack(fill="x")

        if app.demo:
            banner = Card(self.scroll.inner, padding=14, bg=C.ACCENT_SOFT, border=C.ACCENT)
            banner.pack(fill="x", padx=36, pady=(14, 0))
            tk.Label(banner.body, text="Modo demostración",
                     bg=C.ACCENT_SOFT, fg=C.WHITE,
                     font=app.theme.font(10, "bold"), anchor="w").pack(fill="x")
            row = tk.Frame(banner.body, bg=C.ACCENT_SOFT)
            row.pack(fill="x", pady=(4, 0))
            tk.Label(row, text="Los datos son inventados y los cambios no salen de esta app.",
                     bg=C.ACCENT_SOFT, fg="#c7cdff", font=app.theme.font(9),
                     anchor="w").pack(side="left")
            ttk.Button(row, text="Conectar mi cuenta", style="SmallAccent.TButton",
                       command=self.app.logout).pack(side="right")

        self.grid_host = tk.Frame(self.scroll.inner, bg=C.CONTENT)
        self.grid_host.pack(fill="both", expand=True, padx=28, pady=18)
        for column in range(3):
            self.grid_host.grid_columnconfigure(column, weight=1, uniform="guilds")
        self.grid_host.bind("<Configure>", self._on_resize)

        self.empty = tk.Frame(self.scroll.inner, bg=C.CONTENT)

        self.hidden_label = tk.Label(self.scroll.inner, text="", bg=C.CONTENT,
                                     fg=C.YELLOW, font=app.theme.font(8),
                                     anchor="w", justify="left", wraplength=900)
        self.hidden_label.pack(fill="x", padx=36, pady=(2, 0))

        hint = tk.Frame(self.scroll.inner, bg=C.CONTENT)
        hint.pack(fill="x", padx=36, pady=(4, 30))
        tk.Label(hint,
                 text="Solo se muestran servidores donde eres propietario o tienes permisos "
                      "administrativos. Si esperabas ver otro, revisa tus permisos en Discord "
                      "y pulsa «Actualizar».",
                 bg=C.CONTENT, fg=C.FAINT, font=app.theme.font(8), anchor="w",
                 justify="left", wraplength=900).pack(fill="x")

        self._render_cards()

    # ------------------------------------------------------------------ #
    def _on_resize(self, event: Any) -> None:
        columns = 3 if event.width >= 900 else max(1, min(2, event.width // 330))
        if columns != self._columns:
            self._columns = columns
            self._reflow()

    def reload(self) -> None:
        position = self.scroll._canvas.yview()[0]
        self._render_cards()
        if position > 0:
            self.after_idle(lambda: self.scroll._canvas.yview_moveto(position))

    def set_live_status(self, state: str) -> None:
        palette = {
            "live": ("● Automático", C.GREEN),
            "paused": ("● En pausa", C.MUTED),
            "off": ("○ Manual · F5", C.FAINT),
            "error": ("● Sin conexión", C.RED),
        }
        text, color = palette.get(state, palette["live"])
        try:
            self.live_label.configure(text=text, fg=color)
        except tk.TclError:
            pass

    def update_user(self, user: Any) -> None:
        if user is None:
            return
        self.user_name_label.configure(text=user.display_name)
        self.app.images.apply(self.user_avatar, user.avatar_url, 30)
        has_nitro = bool(getattr(user, "has_nitro", False))
        if has_nitro and self.nitro_label is None:
            self.nitro_label = tk.Label(self.user_text, text="NITRO", bg=C.ACCENT,
                                        fg=C.WHITE, font=self.app.theme.font(6, "bold"),
                                        padx=5, pady=1)
            self.nitro_label.pack(anchor="w", pady=(2, 0))
        elif not has_nitro and self.nitro_label is not None:
            self.nitro_label.destroy()
            self.nitro_label = None

    def _reflow(self) -> None:
        visible = [card for card in self._cards if card.winfo_manager()]
        if not visible:
            return
        columns = max(1, min(self._columns, len(visible)))
        for column in range(3):
            self.grid_host.grid_columnconfigure(
                column, weight=1 if column < columns else 0,
                uniform="guilds" if column < columns else "")
        for index, card in enumerate(visible):
            card.grid(row=index // columns, column=index % columns,
                      sticky="nsew", padx=8, pady=8)

    def _summary_text(self) -> str:
        guilds = self.app.guilds or []
        if not guilds:
            return "Solo aparecen servidores donde eres propietario o administrador."
        owned = sum(1 for guild in guilds if guild.owner)
        administered = len(guilds) - owned
        parts = [plural(len(guilds), "servidor", "servidores")]
        if owned:
            parts.append(plural(owned, "propio", "propios"))
        if administered:
            parts.append(plural(administered, "administrado", "administrados"))
        return " · ".join(parts)

    def _render_cards(self) -> None:
        for card in self._cards:
            card.pack_forget()
            card.grid_forget()
            card.destroy()
        self._cards.clear()
        needle = self.search.value().lower() if hasattr(self, "search") else ""
        guilds = [g for g in (self.app.guilds or []) if needle in g.name.lower()]
        guilds.sort(key=lambda g: (0 if g.owner else 1,
                                   0 if (g.permissions == -1 or g.permissions & (1 << 3)) else 1,
                                   g.name.lower()))
        if hasattr(self, "subtitle_label"):
            self.subtitle_label.configure(text=self._summary_text())
        if hasattr(self, "hidden_label"):
            hidden = self.app.hidden_guilds
            if hidden == 1:
                text = "Se oculta 1 servidor donde no tienes permisos administrativos."
            elif hidden > 1:
                text = (f"Se ocultan {hidden} servidores donde no tienes permisos "
                        "administrativos.")
            else:
                text = ""
            self.hidden_label.configure(text=text)
        if not self.app.guilds:
            self._show_empty("sin-servidores")
            return
        if not guilds:
            self._show_empty("filtro")
            return
        self.empty.pack_forget()
        for summary in guilds:
            card = GuildCard(self.grid_host, summary, self.app,
                             command=lambda s=summary: self._open_guild(s))
            card.grid(sticky="nsew", padx=8, pady=8)
            self._cards.append(card)
        self._reflow()
        self.scroll.refresh_scroll()

    def _open_guild(self, summary: GuildSummary) -> None:
        if (getattr(self.app, "bot_guild_ids_known", False)
                and summary.id not in self.app.bot_guild_ids):
            self.app._show_bot_missing(summary)
            return
        self.app.open_guild(summary)

    def _show_empty(self, reason: str) -> None:
        for child in self.empty.winfo_children():
            child.destroy()
        if reason == "sin-servidores":
            title = "No administras ningún servidor"
            message = ("Solo se muestran servidores donde eres propietario o tienes permisos "
                       "de administración (Administrador o Gestionar servidor). Si esperabas "
                       "ver uno, revisa tus permisos en Discord y pulsa «Actualizar».")
            if self.app.hidden_guilds:
                message += (f"\nSe ocultaron {self.app.hidden_guilds} servidores donde no "
                            "tienes permisos administrativos.")
        else:
            title = "Ningún servidor coincide"
            message = "Prueba con otro texto en el buscador."
        self.empty.pack(fill="x", padx=36, pady=(20, 10), before=self.hidden_label)
        card = Card(self.empty, padding=24)
        card.pack(fill="x")
        container = card.body
        tk.Label(container, text=title, bg=C.CARD, fg=C.TEXT,
                 font=self.app.theme.font(12, "bold")).pack(pady=(6, 4))
        tk.Label(container, text=message, bg=C.CARD, fg=C.MUTED,
                 font=self.app.theme.font(9), wraplength=620,
                 justify="center").pack()
        self.scroll.refresh_scroll()

    def _copy_invite(self, url: str) -> None:
        copy_to_clipboard(self, url)
        self.app.toasts.show("URL de invitación copiada al portapapeles.", "success")
