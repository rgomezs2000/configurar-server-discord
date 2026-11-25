"""Selector de emojis: estándar (Unicode), del servidor (animados incluidos) y recientes."""
from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

from ..emojis import STANDARD_CATEGORIES
from ..models import Emoji
from .theme import C
from .widgets import ScrollFrame, SearchEntry, TabBar, Tooltip

COLUMNS = 8


class EmojiPicker(tk.Toplevel):
    """Ventana flotante que inserta el emoji elegido en el campo indicado."""

    WIDTH = 440
    HEIGHT = 500

    def __init__(self, parent: tk.Misc, app: Any, anchor: tk.Misc,
                 on_pick: Callable[[str], None]):
        existing = getattr(app, "_emoji_picker", None)
        if existing is not None:
            try:
                existing.destroy()
            except tk.TclError:
                pass
        super().__init__(parent)
        self.app = app
        self._on_pick = on_pick
        self._anchor = anchor
        self._guild_emojis: list[Emoji] | None = None
        self._guild_loading = False
        self._guild_error = ""
        self._tab = "standard"
        self._ready = False
        self._can_close = False

        self.overrideredirect(True)
        self.transient(parent.winfo_toplevel())
        self.configure(bg=C.BORDER)
        self._parent_grab = parent.grab_current()
        self._build()
        self._position()
        self._ready = True
        self._render()
        self._load_guild_emojis()
        if self._parent_grab is not None:
            try:
                self.grab_set()
            except tk.TclError:
                pass
        self.after(120, self._focus_search)
        self.after(300, lambda: setattr(self, "_can_close", True))
        self.bind("<Escape>", lambda _e: self.close())
        self.bind("<FocusOut>", self._on_focus_out)
        app._emoji_picker = self

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        app = self.app
        outer = tk.Frame(self, bg=C.CARD)
        outer.pack(fill="both", expand=True, padx=1, pady=1)

        head = tk.Frame(outer, bg=C.CARD)
        head.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(head, text="Insertar emoji", bg=C.CARD, fg=C.TEXT,
                 font=app.theme.font(10, "bold")).pack(side="left")
        nitro = bool(getattr(app.user, "has_nitro", False))
        nitro_badge = tk.Label(
            head, text="NITRO" if nitro else "SIN NITRO",
            bg=C.ACCENT if nitro else C.CARD_ALT,
            fg=C.WHITE if nitro else C.MUTED,
            font=app.theme.font(7, "bold"), padx=6, pady=1)
        nitro_badge.pack(side="left", padx=(8, 0))
        Tooltip(nitro_badge,
                "Nitro activo: puedes usar emojis animados en cualquier servidor."
                if nitro else
                "Sin Nitro: los emojis animados solo se muestran dentro del servidor "
                "donde están subidos.")
        close = tk.Label(head, text="✕", bg=C.CARD, fg=C.MUTED,
                         font=app.theme.font(9), cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda _e: self.close())

        self.search = SearchEntry(outer, placeholder="Buscar emoji…",
                                  on_change=lambda _t: self._render(), width=30,
                                  bg=C.CARD, theme=app.theme)
        self.search.pack(fill="x", padx=10, pady=(0, 4))

        self.tabs = TabBar(outer, [("standard", "Estándar"), ("guild", "Servidor"),
                                   ("recent", "Recientes")],
                           on_change=self._on_tab, theme=app.theme)
        self.tabs.pack(fill="x", padx=10)

        self.scroll = ScrollFrame(outer, bg=C.CARD)
        self.scroll.pack(fill="both", expand=True, padx=6, pady=(4, 2))
        self.grid_frame = tk.Frame(self.scroll.inner, bg=C.CARD)
        self.grid_frame.pack(fill="both", expand=True)
        for column in range(COLUMNS):
            self.grid_frame.grid_columnconfigure(column, weight=1, uniform="emoji")

        tk.Label(outer,
                 text="Los emojis del servidor se insertan con su mención real "
                      "(animados: <a:nombre:id>).",
                 bg=C.CARD, fg=C.FAINT, font=app.theme.font(8), wraplength=410,
                 justify="left").pack(fill="x", padx=10, pady=(0, 8))

    def _position(self) -> None:
        try:
            self._anchor.update_idletasks()
            ax = self._anchor.winfo_rootx()
            ay = self._anchor.winfo_rooty()
            aw = self._anchor.winfo_width()
            ah = self._anchor.winfo_height()
        except tk.TclError:
            ax = ay = 200
            aw = ah = 0
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = ax + aw - self.WIDTH
        x = max(8, min(x, screen_w - self.WIDTH - 8))
        y = ay - self.HEIGHT - 6
        if y < 8:
            y = ay + ah + 6
        y = max(8, min(y, screen_h - self.HEIGHT - 48))
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

    def _focus_search(self) -> None:
        if not self.winfo_exists():
            return
        try:
            self.lift()
            self.focus_force()
            self.search.focus()
        except tk.TclError:
            pass

    def _on_focus_out(self, _event: Any = None) -> None:
        self.after(160, self._check_focus)

    def _check_focus(self) -> None:
        if not self._can_close or not self.winfo_exists():
            return
        widget = self.focus_get()
        inside = False
        if widget is not None:
            try:
                inside = widget.winfo_toplevel() is self
            except tk.TclError:
                inside = False
        if not inside:
            self.close()

    def close(self) -> None:
        if getattr(self.app, "_emoji_picker", None) is self:
            self.app._emoji_picker = None
        try:
            self.grab_release()
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass
        parent_grab = getattr(self, "_parent_grab", None)
        if parent_grab is not None:
            try:
                if parent_grab.winfo_exists():
                    parent_grab.grab_set()
            except tk.TclError:
                pass

    # ------------------------------------------------------------------ #
    def _on_tab(self, key: str) -> None:
        self._tab = key
        if self._ready:
            self._render()

    def _render(self) -> None:
        if not self._ready:
            return
        for child in self.grid_frame.winfo_children():
            child.destroy()
        needle = self.search.value().lower()
        if self._tab == "standard":
            self._render_standard(needle)
        elif self._tab == "guild":
            self._render_guild(needle)
        else:
            self._render_recent(needle)
        self.scroll.refresh_scroll()

    def _render_standard(self, needle: str) -> None:
        row = 0
        for category, items in STANDARD_CATEGORIES:
            matches = [(char, name) for char, name in items
                       if not needle or needle in name.lower()]
            if not matches:
                continue
            header = tk.Label(self.grid_frame, text=category.upper(), bg=C.CARD,
                              fg=C.MUTED, font=self.app.theme.font(7, "bold"),
                              anchor="w")
            header.grid(row=row, column=0, columnspan=COLUMNS, sticky="w", pady=(6, 2))
            row += 1
            for index, (char, name) in enumerate(matches):
                self._emoji_cell(row + index // COLUMNS, index % COLUMNS, char, name, char)
            row += (len(matches) + COLUMNS - 1) // COLUMNS
        if row == 0:
            self._empty("Ningún emoji coincide con la búsqueda.")

    def _render_guild(self, needle: str) -> None:
        if self._guild_loading:
            self._empty("Cargando emojis del servidor…")
            return
        if self._guild_error:
            self._empty(self._guild_error)
            return
        emojis = [emoji for emoji in (self._guild_emojis or [])
                  if not needle or needle in emoji.name.lower()]
        if not emojis:
            self._empty("Este servidor no tiene emojis personalizados.")
            return
        for index, emoji in enumerate(emojis):
            row, column = index // COLUMNS, index % COLUMNS
            text = (f"<a:{emoji.name}:{emoji.id}>" if emoji.animated
                    else f"<:{emoji.name}:{emoji.id}>")
            label = f"{emoji.name}{' (animado)' if emoji.animated else ''}"
            cell = self._cell(row, column)
            inner = tk.Label(cell, text="", bg=C.CARD_ALT, fg=C.TEXT,
                             font=self.app.theme.font(7), cursor="hand2",
                             wraplength=44)
            inner.pack(expand=True, padx=2, pady=2)
            self._fill_guild_cell(inner, emoji)
            if emoji.animated:
                tk.Label(cell, text="▶", bg=C.CARD_ALT, fg=C.YELLOW,
                         font=self.app.theme.font(6, "bold")).place(relx=0.95, rely=0.08,
                                                                    anchor="ne")
            self._bind_cell(cell, inner, text, label)

    def _fill_guild_cell(self, label: tk.Label, emoji: Emoji) -> None:
        label.configure(text=emoji.name[:9])
        if not self.app.images.enabled or not emoji.id:
            return

        def apply(photo: tk.PhotoImage | None) -> None:
            if photo is None or not label.winfo_exists():
                return
            label.configure(image=photo, text="")

        self.app.images.get(emoji.image_url, 30, apply)

    def _render_recent(self, needle: str) -> None:
        items = list(self.app.settings.get("recent_emojis") or [])
        items = [item for item in items
                 if not needle or needle in str(item.get("label", "")).lower()]
        if not items:
            self._empty("Todavía no has usado emojis.")
            return
        for index, item in enumerate(items):
            text = str(item.get("text", ""))
            label = str(item.get("label", text))
            display = str(item.get("emoji", "")) or label[:9]
            self._emoji_cell(index // COLUMNS, index % COLUMNS, display, label, text)

    def _cell(self, row: int, column: int) -> tk.Frame:
        cell = tk.Frame(self.grid_frame, bg=C.CARD_ALT, width=46, height=42,
                        cursor="hand2")
        cell.grid(row=row, column=column, padx=2, pady=2, sticky="nsew")
        cell.pack_propagate(False)
        return cell

    def _emoji_cell(self, row: int, column: int, display: str, label: str,
                    insert_text: str) -> None:
        cell = self._cell(row, column)
        inner = tk.Label(cell, text=display, bg=C.CARD_ALT, fg=C.TEXT,
                         font=(self.app.theme.family, 15), cursor="hand2")
        inner.pack(expand=True)
        self._bind_cell(cell, inner, insert_text, label)

    def _bind_cell(self, cell: tk.Frame, inner: tk.Label, insert_text: str,
                   label: str) -> None:
        def enter(_event: Any = None) -> None:
            cell.configure(bg=C.BORDER)
            inner.configure(bg=C.BORDER)

        def leave(_event: Any = None) -> None:
            cell.configure(bg=C.CARD_ALT)
            inner.configure(bg=C.CARD_ALT)

        def click(_event: Any = None) -> None:
            self._pick(insert_text, label)

        for widget in (cell, inner):
            widget.bind("<Button-1>", click)
            widget.bind("<Enter>", enter)
            widget.bind("<Leave>", leave)
        Tooltip(cell, label)

    def _empty(self, message: str) -> None:
        tk.Label(self.grid_frame, text=message, bg=C.CARD, fg=C.MUTED,
                 font=self.app.theme.font(9), wraplength=360).grid(
            row=0, column=0, columnspan=COLUMNS, pady=30)

    # ------------------------------------------------------------------ #
    def _load_guild_emojis(self) -> None:
        if self.app.guild is None or self.app.client is None:
            self._guild_error = "Selecciona un servidor para ver sus emojis."
            return
        self._guild_loading = True
        client = self.app.client
        guild_id = self.app.guild.id

        def done(emojis: list[Emoji]) -> None:
            self._guild_loading = False
            self._guild_emojis = emojis
            if self._tab == "guild" and self.winfo_exists():
                self._render()

        def failed(error: BaseException) -> None:
            self._guild_loading = False
            self._guild_error = f"No se pudieron cargar los emojis: {error}"
            if self._tab == "guild" and self.winfo_exists():
                self._render()

        self.app.run_task(lambda: client.list_emojis(guild_id), done, failed, quiet=True)

    def _pick(self, insert_text: str, label: str) -> None:
        self._on_pick(insert_text)
        items = [item for item in (self.app.settings.get("recent_emojis") or [])
                 if item.get("text") != insert_text]
        items.insert(0, {"text": insert_text, "label": label,
                         "emoji": insert_text if len(insert_text) <= 3 else ""})
        self.app.settings.set("recent_emojis", items[:24])
        self.app.settings.save()
