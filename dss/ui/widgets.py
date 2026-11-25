"""Widgets reutilizables sobre Tk clásico (sin dependencias externas)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Iterable, Sequence

from ..util import truncate
from .theme import C, Theme, enable_dark_titlebar


# --------------------------------------------------------------------------- #
# Utilidades de dibujo
# --------------------------------------------------------------------------- #

def round_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
               radius: float, **options: Any) -> int:
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **options)


def bind_recursive(widget: tk.Misc, sequence: str, callback: Callable[[Any], None],
                   cursor: str = "hand2") -> None:
    widget.bind(sequence, callback)
    try:
        widget.configure(cursor=cursor)
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        bind_recursive(child, sequence, callback, cursor)


def name_color(name: str) -> str:
    return C.GUILD_COLORS[sum(ord(ch) for ch in (name or "?")) % len(C.GUILD_COLORS)]


def initials_of(name: str, limit: int = 2) -> str:
    parts = [p for p in (name or "?").replace("_", " ").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:limit].upper()
    return "".join(part[0] for part in parts[:limit]).upper()


# --------------------------------------------------------------------------- #
# Contenedores y textos
# --------------------------------------------------------------------------- #

class Card(tk.Frame):
    def __init__(self, parent: tk.Misc, padding: int = 18, bg: str = C.CARD,
                 border: str = C.BORDER_SOFT, **kwargs: Any):
        super().__init__(parent, bg=bg, highlightbackground=border,
                         highlightthickness=1, bd=0, **kwargs)
        self.body = tk.Frame(self, bg=bg)
        self.body.pack(fill="both", expand=True, padx=padding, pady=padding)


class ScrollFrame(tk.Frame):
    """Área desplazable vertical con rueda del ratón multiplataforma.

    Con ``center=True`` el contenido se centra verticalmente cuando sobra espacio
    (útil para formularios que deben quedar centrados pero poder desplazarse).
    """

    def __init__(self, parent: tk.Misc, bg: str = C.CONTENT, padding: int = 0,
                 center: bool = False):
        super().__init__(parent, bg=bg)
        self._bg = bg
        self._center = center
        self._canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self._vbar = ttk.Scrollbar(self, orient="vertical", style="Vertical.TScrollbar",
                                   command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._vbar.set)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._vbar.grid(row=0, column=1, sticky="ns")
        self._bar_visible = True
        self.inner = tk.Frame(self._canvas, bg=bg)
        self._window = self._canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<Enter>", self._bind_wheel)
        self._canvas.bind("<Leave>", self._unbind_wheel)
        if padding:
            self.inner.configure(padx=padding)

    def _on_inner_configure(self, _event: Any = None) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        self._center_content()
        self._sync_scrollbar()

    def _on_canvas_configure(self, event: Any) -> None:
        self._canvas.itemconfigure(self._window, width=event.width)
        self._center_content()
        self._sync_scrollbar()

    def _center_content(self) -> None:
        if not self._center:
            return
        canvas_height = self._canvas.winfo_height()
        canvas_width = self._canvas.winfo_width()
        content_height = self.inner.winfo_reqheight()
        offset = max(0, (canvas_height - content_height) // 2)
        self._canvas.coords(self._window, 0, offset)
        self._canvas.configure(scrollregion=(0, 0, canvas_width,
                                             max(canvas_height, content_height)))

    def _sync_scrollbar(self) -> None:
        bbox = self._canvas.bbox("all")
        if not bbox:
            return
        height = bbox[3] - bbox[1]
        needs = height > self._canvas.winfo_height() + 1
        if needs and not self._bar_visible:
            self._vbar.grid()
            self._bar_visible = True
        elif not needs and self._bar_visible:
            self._vbar.grid_remove()
            self._bar_visible = False

    def _bind_wheel(self, _event: Any = None) -> None:
        self._canvas.bind_all("<MouseWheel>", self._on_wheel, add="+")
        self._canvas.bind_all("<Button-4>", self._on_wheel_x11, add="+")
        self._canvas.bind_all("<Button-5>", self._on_wheel_x11, add="+")

    def _unbind_wheel(self, _event: Any = None) -> None:
        self._canvas.unbind_all("<MouseWheel>")
        self._canvas.unbind_all("<Button-4>")
        self._canvas.unbind_all("<Button-5>")

    def _on_wheel(self, event: Any) -> None:
        first, last = self._canvas.yview()
        if first <= 0.0 and last >= 1.0:
            return
        delta = -1 * int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1)
        self._canvas.yview_scroll(delta * 3, "units")

    def _on_wheel_x11(self, event: Any) -> None:
        first, last = self._canvas.yview()
        if first <= 0.0 and last >= 1.0:
            return
        self._canvas.yview_scroll(-3 if event.num == 4 else 3, "units")

    def scroll_to_top(self) -> None:
        self._canvas.yview_moveto(0.0)

    def clear(self) -> None:
        for child in self.inner.winfo_children():
            child.destroy()

    def refresh_scroll(self) -> None:
        self.inner.update_idletasks()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))


class SectionTitle(tk.Frame):
    def __init__(self, parent: tk.Misc, title: str, subtitle: str = "",
                 bg: str = C.CONTENT, theme: Theme | None = None):
        super().__init__(parent, bg=bg)
        family = theme.font(13, "bold") if theme else ("Segoe UI", 13, "bold")
        tk.Label(self, text=title, bg=bg, fg=C.TEXT, font=family, anchor="w").pack(fill="x")
        if subtitle:
            tk.Label(self, text=subtitle, bg=bg, fg=C.MUTED,
                     font=(family[0], 9), anchor="w", justify="left").pack(fill="x", pady=(2, 0))


class PageHeader(tk.Frame):
    def __init__(self, parent: tk.Misc, app: Any, title: str, subtitle: str = ""):
        super().__init__(parent, bg=C.CONTENT)
        left = tk.Frame(self, bg=C.CONTENT)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=title, bg=C.CONTENT, fg=C.TEXT,
                 font=app.theme.font(20, "bold"), anchor="w").pack(fill="x")
        self.subtitle = tk.Label(left, text=subtitle, bg=C.CONTENT, fg=C.MUTED,
                                 font=app.theme.font(10), anchor="w", justify="left")
        self.subtitle.pack(fill="x", pady=(3, 0))
        self.actions = tk.Frame(self, bg=C.CONTENT)
        self.actions.pack(side="right", anchor="n", padx=(16, 0))

    def button(self, text: str, command: Callable[[], None], style: str = "TButton",
               **kwargs: Any) -> ttk.Button:
        button = ttk.Button(self.actions, text=text, command=command, style=style, **kwargs)
        button.pack(side="left", padx=(8, 0))
        return button


class Separator(tk.Frame):
    def __init__(self, parent: tk.Misc, color: str = C.BORDER_SOFT, pady: int = 0):
        super().__init__(parent, bg=color, height=1)
        self.pack(fill="x", pady=pady)


class Badge(tk.Label):
    def __init__(self, parent: tk.Misc, text: str, fg: str = C.DIM, bg: str = C.CARD_ALT,
                 font: tuple | None = None, padx: int = 8, pady: int = 2):
        super().__init__(parent, text=text, fg=fg, bg=bg, font=font or ("Segoe UI", 8, "bold"),
                         padx=padx, pady=pady)


class EmptyState(tk.Frame):
    def __init__(self, parent: tk.Misc, title: str, message: str = "",
                 action_text: str = "", command: Callable[[], None] | None = None,
                 bg: str = C.CARD):
        super().__init__(parent, bg=bg)
        tk.Label(self, text="◇", bg=bg, fg=C.FAINT,
                 font=("Segoe UI", 28)).pack(pady=(18, 6))
        tk.Label(self, text=title, bg=bg, fg=C.TEXT,
                 font=("Segoe UI", 11, "bold")).pack()
        if message:
            tk.Label(self, text=message, bg=bg, fg=C.MUTED, font=("Segoe UI", 9),
                     wraplength=420, justify="center").pack(pady=(4, 0))
        if action_text and command:
            ttk.Button(self, text=action_text, command=command,
                       style="Accent.TButton").pack(pady=(12, 18))
        else:
            self.pack_configure(pady=10)


# --------------------------------------------------------------------------- #
# Botones y navegación
# --------------------------------------------------------------------------- #

class FlatButton(tk.Frame):
    """Botón plano con hover, útil en barras y tarjetas."""

    def __init__(self, parent: tk.Misc, text: str, command: Callable[[], None],
                 bg: str = C.SIDEBAR, fg: str = C.DIM, hover_bg: str = C.CARD_ALT,
                 hover_fg: str = C.TEXT, font: tuple | None = None, padx: int = 10,
                 pady: int = 6, anchor: str = "w", width: int = 0):
        super().__init__(parent, bg=bg, cursor="hand2")
        self._bg = bg
        self._hover_bg = hover_bg
        self._fg = fg
        self._hover_fg = hover_fg
        self._command = command
        self._label = tk.Label(self, text=text, bg=bg, fg=fg,
                               font=font or ("Segoe UI", 10), anchor=anchor,
                               padx=padx, pady=pady, cursor="hand2",
                               width=width if width else 0)
        self._label.pack(fill="both", expand=True)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self._label.bind("<Enter>", self._on_enter)
        self._label.bind("<Leave>", self._on_leave)
        self._label.bind("<Button-1>", self._on_click)
        self.bind("<Button-1>", self._on_click)
        self._enabled = True

    def _on_enter(self, _event: Any = None) -> None:
        if self._enabled:
            self.configure(bg=self._hover_bg)
            self._label.configure(bg=self._hover_bg, fg=self._hover_fg)

    def _on_leave(self, _event: Any = None) -> None:
        self.configure(bg=self._bg)
        self._label.configure(bg=self._bg, fg=self._fg)

    def _on_click(self, _event: Any = None) -> None:
        if self._enabled:
            self._command()

    def set_text(self, text: str) -> None:
        self._label.configure(text=text)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._label.configure(fg=self._fg if enabled else C.FAINT, cursor="hand2" if enabled else "")
        self.configure(cursor="hand2" if enabled else "")

    def set_active(self, active: bool) -> None:
        self._bg = C.CARD_ALT if active else self._bg
        self.configure(bg=self._bg)
        self._label.configure(bg=self._bg, fg=C.TEXT if active else self._fg)


class NavButton(tk.Frame):
    def __init__(self, parent: tk.Misc, text: str, command: Callable[[], None],
                 glyph: str = "", badge: str = "", bg: str = C.SIDEBAR,
                 theme: Theme | None = None):
        super().__init__(parent, bg=bg, cursor="hand2", height=38)
        self._bg = bg
        self._command = command
        self._active = False
        self._glyph = glyph
        self._badge_text = badge
        self._theme = theme
        self.indicator = tk.Frame(self, bg=bg, width=3)
        self.indicator.pack(side="left", fill="y", padx=(0, 0))
        self._glyph_label = tk.Label(self, text=glyph, bg=bg, fg=C.MUTED,
                                     font=(theme.family if theme else "Segoe UI", 12),
                                     width=2, anchor="center", cursor="hand2")
        self._glyph_label.pack(side="left", padx=(8, 0))
        self._label = tk.Label(self, text=text, bg=bg, fg=C.DIM,
                               font=theme.font(10, "bold") if theme else ("Segoe UI", 10, "bold"),
                               anchor="w", cursor="hand2")
        self._label.pack(side="left", fill="x", expand=True, padx=(4, 6))
        self._badge = None
        if badge:
            self._badge = tk.Label(self, text=badge, bg=C.CARD_ALT, fg=C.DIM,
                                   font=("Segoe UI", 8, "bold"), padx=6, pady=1, cursor="hand2")
            self._badge.pack(side="right", padx=(0, 8))
        for widget in (self, self._label, self._glyph_label, self.indicator):
            widget.bind("<Button-1>", self._on_click)
        for widget in (self, self._label, self._glyph_label, self.indicator):
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

    def _on_click(self, _event: Any = None) -> None:
        self._command()

    def _paint(self, bg: str, fg: str, glyph_fg: str | None = None) -> None:
        self.configure(bg=bg)
        self._label.configure(bg=bg, fg=fg)
        self._glyph_label.configure(bg=bg, fg=glyph_fg or fg)
        self.indicator.configure(bg=C.ACCENT if self._active else bg)

    def _on_enter(self, _event: Any = None) -> None:
        if not self._active:
            self._paint(C.CARD_ALT, C.TEXT, C.DIM)

    def _on_leave(self, _event: Any = None) -> None:
        if not self._active:
            self._paint(self._bg, C.DIM, C.MUTED)

    def set_active(self, active: bool) -> None:
        self._active = active
        if active:
            self._paint(C.CARD_ALT, C.TEXT, C.TEXT)
        else:
            self._paint(self._bg, C.DIM, C.MUTED)

    def set_badge(self, text: str) -> None:
        if text:
            if self._badge is None:
                self._badge = tk.Label(self, text=text, bg=C.CARD_ALT, fg=C.DIM,
                                       font=("Segoe UI", 8, "bold"), padx=6, pady=1)
                self._badge.pack(side="right", padx=(0, 8))
            else:
                self._badge.configure(text=text)
        elif self._badge is not None:
            self._badge.destroy()
            self._badge = None


class TabBar(tk.Frame):
    def __init__(self, parent: tk.Misc, tabs: Sequence[tuple[str, str]],
                 on_change: Callable[[str], None], theme: Theme):
        super().__init__(parent, bg=C.CONTENT)
        self._on_change = on_change
        self._buttons: dict[str, tk.Label] = {}
        self._active = ""
        self._theme = theme
        self._bar = tk.Frame(self, bg=C.CONTENT)
        self._bar.pack(fill="x")
        for key, label in tabs:
            widget = tk.Label(self._bar, text=label, bg=C.CONTENT, fg=C.MUTED,
                              font=theme.font(10, "bold"), padx=14, pady=7,
                              cursor="hand2")
            widget.pack(side="left", padx=(0, 2))
            widget.bind("<Button-1>", lambda _e, k=key: self.select(k))
            self._buttons[key] = widget
        self._underline = tk.Frame(self, bg=C.CARD, height=1)
        self._underline.pack(fill="x")
        if tabs:
            self.select(tabs[0][0])

    def select(self, key: str) -> None:
        self._active = key
        for name, widget in self._buttons.items():
            widget.configure(fg=C.TEXT if name == key else C.MUTED,
                             bg=C.CARD if name == key else C.CONTENT)
        self._on_change(key)


# --------------------------------------------------------------------------- #
# Formularios
# --------------------------------------------------------------------------- #

class Field(tk.Frame):
    def __init__(self, parent: tk.Misc, label: str, hint: str = "", bg: str = C.CONTENT):
        super().__init__(parent, bg=bg)
        self.bg = bg
        self.label = tk.Label(self, text=label.upper(), bg=bg, fg=C.MUTED,
                              font=("Segoe UI", 8, "bold"), anchor="w")
        self.label.pack(fill="x")
        self.slot = tk.Frame(self, bg=bg)
        self.slot.pack(fill="x", pady=(4, 0))
        self.hint_label = None
        if hint:
            self.hint_label = tk.Label(self, text=hint, bg=bg, fg=C.FAINT,
                                       font=("Segoe UI", 8), anchor="w", justify="left")
            self.hint_label.pack(fill="x", pady=(4, 0))

    def add(self, widget: tk.Widget) -> tk.Widget:
        widget.pack(fill="x")
        return widget

    def set_hint(self, text: str, color: str = C.FAINT) -> None:
        if self.hint_label is None:
            self.hint_label = tk.Label(self, text="", bg=self.bg, fg=color,
                                       font=("Segoe UI", 8), anchor="w", justify="left")
            self.hint_label.pack(fill="x", pady=(4, 0))
        self.hint_label.configure(text=text, fg=color)


class Checkbox(tk.Frame):
    def __init__(self, parent: tk.Misc, text: str = "", variable: tk.BooleanVar | None = None,
                 command: Callable[[], None] | None = None, bg: str = C.CONTENT,
                 fg: str = C.TEXT, font: tuple | None = None, disabled: bool = False):
        super().__init__(parent, bg=bg, cursor="hand2" if not disabled else "")
        self.var = variable or tk.BooleanVar(value=False)
        self._command = command
        self._bg = bg
        self._fg = fg
        self._disabled = disabled
        self._box = tk.Canvas(self, width=18, height=18, bg=bg, highlightthickness=0,
                              bd=0, cursor="hand2" if not disabled else "")
        self._box.pack(side="left")
        self._label = tk.Label(self, text=text, bg=bg, fg=fg if not disabled else C.FAINT,
                               font=font or ("Segoe UI", 10), anchor="w", justify="left",
                               cursor="hand2" if not disabled else "")
        self._label.pack(side="left", padx=(8, 0))
        for widget in (self, self._box, self._label):
            widget.bind("<Button-1>", self._toggle)
        self._trace = self.var.trace_add("write", lambda *_: self._safe_redraw())
        self._redraw()

    def _safe_redraw(self) -> None:
        try:
            self._redraw()
        except tk.TclError:
            pass

    def _toggle(self, _event: Any = None) -> None:
        if self._disabled:
            return
        self.var.set(not self.var.get())
        if self._command:
            self._command()

    def _redraw(self) -> None:
        self._box.delete("all")
        checked = bool(self.var.get())
        fill = C.ACCENT if checked else C.INPUT
        outline = C.ACCENT if checked else C.BORDER
        if self._disabled:
            fill, outline = C.CARD, C.BORDER_SOFT
        round_rect(self._box, 2, 2, 16, 16, 4, fill=fill, outline=outline, width=1)
        if checked:
            self._box.create_line(5.5, 9.5, 8, 12, 12.5, 6, fill=C.WHITE, width=2,
                                  capstyle="round", joinstyle="round")

    def set_enabled(self, enabled: bool) -> None:
        self._disabled = not enabled
        self._label.configure(fg=self._fg if enabled else C.FAINT)
        self._redraw()

    def set_text(self, text: str) -> None:
        self._label.configure(text=text)


class Switch(tk.Frame):
    def __init__(self, parent: tk.Misc, variable: tk.BooleanVar, command: Callable[[], None] | None = None,
                 bg: str = C.CONTENT):
        super().__init__(parent, bg=bg, cursor="hand2")
        self.var = variable
        self._command = command
        self._canvas = tk.Canvas(self, width=40, height=22, bg=bg, highlightthickness=0,
                                 bd=0, cursor="hand2")
        self._canvas.pack()
        self._canvas.bind("<Button-1>", self._toggle)
        self._trace = self.var.trace_add("write", lambda *_: self._safe_redraw())
        self._redraw()

    def _safe_redraw(self) -> None:
        try:
            self._redraw()
        except tk.TclError:
            pass

    def _toggle(self, _event: Any = None) -> None:
        self.var.set(not self.var.get())
        if self._command:
            self._command()

    def _redraw(self) -> None:
        self._canvas.delete("all")
        on = bool(self.var.get())
        round_rect(self._canvas, 1, 2, 39, 20, 9,
                   fill=C.ACCENT if on else C.CARD_ALT,
                   outline=C.ACCENT if on else C.BORDER)
        x = 30 if on else 10
        self._canvas.create_oval(x - 7, 4, x + 7, 18, fill=C.WHITE, outline="")


class SearchEntry(tk.Frame):
    def __init__(self, parent: tk.Misc, placeholder: str = "Buscar…",
                 on_change: Callable[[str], None] | None = None, width: int = 30,
                 bg: str = C.CARD, theme: Theme | None = None):
        super().__init__(parent, bg=bg)
        self._placeholder = placeholder
        self._on_change = on_change
        self._active = False
        self._var = tk.StringVar()
        self.entry = tk.Entry(self, textvariable=self._var, bg=C.INPUT, fg=C.TEXT,
                              insertbackground=C.TEXT, relief="flat", bd=0,
                              highlightthickness=1, highlightbackground=C.BORDER,
                              highlightcolor=C.ACCENT, font=theme.font(10) if theme else ("Segoe UI", 10),
                              width=width)
        self.entry.pack(fill="x", ipady=5, padx=1, pady=1)
        self.entry.bind("<FocusIn>", self._focus_in)
        self.entry.bind("<FocusOut>", self._focus_out)
        self.entry.bind("<KeyRelease>", self._changed)
        self._show_placeholder()

    def _show_placeholder(self) -> None:
        if not self._var.get():
            self._active = True
            self.entry.configure(fg=C.FAINT)
            self._var.set(self._placeholder)

    def _focus_in(self, _event: Any = None) -> None:
        if self._active:
            self._var.set("")
            self._active = False
            self.entry.configure(fg=C.TEXT)

    def _focus_out(self, _event: Any = None) -> None:
        if not self._var.get().strip():
            self._show_placeholder()

    def _changed(self, _event: Any = None) -> None:
        if self._active:
            return
        if self._on_change:
            self._on_change(self.value())

    def value(self) -> str:
        return "" if self._active else self._var.get().strip()

    def clear(self) -> None:
        self._active = False
        self._var.set("")
        self.entry.configure(fg=C.TEXT)
        if self._on_change:
            self._on_change("")

    def focus(self) -> None:
        self.entry.focus_set()


def labeled_entry(parent: tk.Misc, app: Any, label: str, hint: str = "",
                  value: str = "", show: str | None = None) -> tuple[tk.Frame, tk.StringVar, ttk.Entry]:
    field = Field(parent, label, hint)
    variable = tk.StringVar(value=value)
    entry = ttk.Entry(field.slot, textvariable=variable, show=show or "")
    field.add(entry)
    return field, variable, entry


def labeled_text(parent: tk.Misc, app: Any, label: str, hint: str = "",
                 height: int = 3) -> tuple[tk.Frame, tk.Text]:
    field = Field(parent, label, hint)
    text = tk.Text(field.slot, height=height, bg=C.INPUT, fg=C.TEXT, bd=0,
                   highlightthickness=1, highlightbackground=C.BORDER,
                   highlightcolor=C.ACCENT, insertbackground=C.TEXT,
                   font=app.theme.font(10), wrap="word", padx=8, pady=6)
    field.add(text)
    return field, text


def labeled_combo(parent: tk.Misc, app: Any, label: str, hint: str = "",
                  values: Sequence[str] = (), value: str = "",
                  variable: tk.StringVar | None = None) -> tuple[tk.Frame, ttk.Combobox]:
    field = Field(parent, label, hint)
    combo = ttk.Combobox(field.slot, values=list(values), state="readonly",
                         textvariable=variable)
    if value:
        combo.set(value)
    field.add(combo)
    return field, combo


class KeyValue(tk.Frame):
    def __init__(self, parent: tk.Misc, key: str, value: str, bg: str = C.CARD,
                 mono: bool = False, theme: Theme | None = None):
        super().__init__(parent, bg=bg)
        tk.Label(self, text=key, bg=bg, fg=C.MUTED, font=("Segoe UI", 9),
                 anchor="w", width=16).pack(side="left")
        tk.Label(self, text=value or "—", bg=bg, fg=C.TEXT,
                 font=(theme.mono_family if mono and theme else "Segoe UI", 9),
                 anchor="w", justify="left").pack(side="left", fill="x", expand=True)


class StatCard(Card):
    def __init__(self, parent: tk.Misc, label: str, value: str, hint: str = "",
                 accent: str = C.ACCENT, theme: Theme | None = None):
        super().__init__(parent, padding=14)
        tk.Frame(self.body, bg=accent, height=3, width=26).pack(anchor="w", pady=(0, 8))
        tk.Label(self.body, text=value, bg=C.CARD, fg=C.TEXT,
                 font=(theme.family if theme else "Segoe UI", 19, "bold"),
                 anchor="w").pack(fill="x")
        tk.Label(self.body, text=label, bg=C.CARD, fg=C.DIM,
                 font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(1, 0))
        if hint:
            tk.Label(self.body, text=hint, bg=C.CARD, fg=C.FAINT,
                     font=("Segoe UI", 8), anchor="w").pack(fill="x")


# --------------------------------------------------------------------------- #
# Iconos y avatares
# --------------------------------------------------------------------------- #

class Avatar(tk.Canvas):
    def __init__(self, parent: tk.Misc, name: str, size: int = 40, bg: str = C.CONTENT,
                 theme: Theme | None = None):
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0)
        self._size = size
        self._bg = bg
        self._theme = theme
        self._photo = None
        self._name = name
        self.set_name(name)

    def set_name(self, name: str) -> None:
        self._name = name
        self.delete("all")
        size = self._size
        self.create_oval(1, 1, size - 1, size - 1, fill=name_color(name), outline="")
        family = self._theme.family if self._theme else "Segoe UI"
        self.create_text(size / 2, size / 2 + 1, text=initials_of(name),
                         fill=C.WHITE, font=(family, max(8, int(size / 3.1)), "bold"))

    def set_photo(self, photo: tk.PhotoImage | None) -> None:
        if photo is None:
            self._photo = None
            self.set_name(self._name)
            return
        self.delete("all")
        self._photo = photo
        self.create_image(self._size / 2, self._size / 2, image=photo)


class GuildTile(tk.Canvas):
    """Icono cuadrado redondeado de un servidor."""

    def __init__(self, parent: tk.Misc, name: str, size: int = 48, bg: str = C.RAIL,
                 command: Callable[[], None] | None = None):
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0,
                         bd=0, cursor="hand2")
        self._name = name
        self._size = size
        self._bg = bg
        self._command = command
        self._selected = False
        self._photo = None
        self._hover = False
        self.bind("<Button-1>", lambda _e: command() if command else None)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self._redraw()

    def _on_enter(self, _event: Any = None) -> None:
        self._hover = True
        self._redraw()

    def _on_leave(self, _event: Any = None) -> None:
        self._hover = False
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        size = self._size
        pad = 4
        color = name_color(self._name)
        outline = C.WHITE if self._selected else (C.BORDER if self._hover else "")
        round_rect(self, pad, pad, size - pad, size - pad, 12,
                   fill=color, outline=outline, width=2)
        if self._selected:
            self.create_rectangle(0, 14, 3, size - 14, fill=C.WHITE, outline="")
        if self._photo is not None:
            self.create_image(size / 2, size / 2, image=self._photo)
        else:
            self.create_text(size / 2, size / 2, text=initials_of(self._name),
                             fill=C.WHITE, font=("Segoe UI", max(9, int(size / 3.6)), "bold"))

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._redraw()

    def set_photo(self, photo: tk.PhotoImage | None) -> None:
        self._photo = photo
        self._redraw()

    def set_name(self, name: str) -> None:
        self._name = name
        self._redraw()

    def set_bg(self, color: str) -> None:
        self._bg = color
        self.configure(bg=color)
        self._redraw()


# --------------------------------------------------------------------------- #
# Tabla
# --------------------------------------------------------------------------- #

class TableColumn:
    def __init__(self, key: str, heading: str, width: int = 140, anchor: str = "w",
                 stretch: bool = False, sortable: bool = True):
        self.key = key
        self.heading = heading
        self.width = width
        self.anchor = anchor
        self.stretch = stretch
        self.sortable = sortable


class Table(tk.Frame):
    def __init__(self, parent: tk.Misc, columns: Sequence[TableColumn], height: int = 12,
                 on_double: Callable[[dict], None] | None = None,
                 on_select: Callable[[list[dict]], None] | None = None,
                 multi: bool = True, empty_text: str = "No hay datos para mostrar.",
                 bg: str = C.CARD, theme: Theme | None = None,
                 hscroll: bool = False):
        super().__init__(parent, bg=bg)
        self._columns = list(columns)
        self._rows: list[dict] = []
        self._on_double = on_double
        self._on_select = on_select
        self._sort_key: str | None = None
        self._sort_reverse = False
        self._theme = theme
        self._empty_text = empty_text
        self.tree = ttk.Treeview(self, columns=[c.key for c in columns], show="headings",
                                 height=height, selectmode="extended" if multi else "browse")
        for column in columns:
            self.tree.heading(column.key, text=column.heading, anchor=column.anchor,
                              command=(lambda c=column: self.sort_by(c.key)) if column.sortable else "")
            self.tree.column(column.key, width=column.width, anchor=column.anchor,
                             stretch=column.stretch, minwidth=40)
        self._vbar = ttk.Scrollbar(self, orient="vertical", style="Vertical.TScrollbar",
                                   command=self.tree.yview)
        self.tree.configure(yscrollcommand=self._vbar.set)
        if hscroll:
            self.grid_rowconfigure(0, weight=1)
            self.grid_columnconfigure(0, weight=1)
            self.tree.grid(row=0, column=0, sticky="nsew")
            self._vbar.grid(row=0, column=1, sticky="ns")
            self._hbar = ttk.Scrollbar(self, orient="horizontal",
                                       style="Horizontal.TScrollbar",
                                       command=self.tree.xview)
            self._hbar.grid(row=1, column=0, sticky="ew")
            self.tree.configure(xscrollcommand=self._hbar.set)
        else:
            self.tree.pack(side="left", fill="both", expand=True)
            self._vbar.pack(side="right", fill="y")
        self.tree.tag_configure("danger", foreground="#ff8f92")
        self.tree.tag_configure("muted", foreground=C.MUTED)
        self.tree.tag_configure("success", foreground="#57d98a")
        self.tree.tag_configure("warning", foreground=C.YELLOW)
        self.tree.tag_configure("accent", foreground="#8ea1ff")
        self._empty = tk.Label(self, text=empty_text, bg=C.CARD, fg=C.MUTED,
                               font=("Segoe UI", 10))
        if on_double:
            self.tree.bind("<Double-1>", self._double_click)
        self.tree.bind("<<TreeviewSelect>>", self._selected)
        self.tree.bind("<Button-3>", self._right_click)

    # -- datos -------------------------------------------------------------- #
    def set_rows(self, rows: Iterable[dict]) -> None:
        self._rows = list(rows)
        self._render()

    def _sorted_rows(self) -> list[dict]:
        if not self._sort_key:
            return self._rows
        def key(row: dict) -> Any:
            raw = row.get("_raw", {})
            value = raw.get(self._sort_key, row.get(self._sort_key, ""))
            return (value is None, str(value).lower() if isinstance(value, str) else value)
        return sorted(self._rows, key=key, reverse=self._sort_reverse)

    def _render(self) -> None:
        selected = set(self.tree.selection())
        position = self.tree.yview()[0]
        self.tree.delete(*self.tree.get_children())
        for row in self._sorted_rows():
            values = [row.get(column.key, "") for column in self._columns]
            tags = tuple(row.get("_tags", ()))
            self.tree.insert("", "end", iid=str(row.get("_id", "")), values=values, tags=tags)
        for iid in selected:
            if self.tree.exists(iid):
                self.tree.selection_add(iid)
        if position > 0:
            self.after_idle(lambda: self.tree.yview_moveto(position))
        if self._rows:
            self._empty.place_forget()
        else:
            self._empty.place(relx=0.5, rely=0.5, anchor="center")
        self._update_headings()

    def _update_headings(self) -> None:
        for column in self._columns:
            text = column.heading
            if column.key == self._sort_key:
                text += " ▲" if not self._sort_reverse else " ▼"
            self.tree.heading(column.key, text=text)

    def sort_by(self, key: str) -> None:
        if self._sort_key == key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_key = key
            self._sort_reverse = False
        self._render()

    # -- selección ---------------------------------------------------------- #
    def selected_rows(self) -> list[dict]:
        by_id = {str(row.get("_id")): row for row in self._rows}
        return [by_id[iid] for iid in self.tree.selection() if iid in by_id]

    def selected_ids(self) -> list[str]:
        return [str(iid) for iid in self.tree.selection()]

    def select_all(self) -> None:
        self.tree.selection_set(self.tree.get_children())

    def clear_selection(self) -> None:
        self.tree.selection_remove(self.tree.selection())

    def _selected(self, _event: Any = None) -> None:
        if self._on_select:
            self._on_select(self.selected_rows())

    def _double_click(self, _event: Any = None) -> None:
        rows = self.selected_rows()
        if rows and self._on_double:
            self._on_double(rows[0])

    def _right_click(self, event: Any) -> None:
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self.tree.selection_set(row_id)

    def set_empty_text(self, text: str) -> None:
        self._empty.configure(text=text)


# --------------------------------------------------------------------------- #
# Modales
# --------------------------------------------------------------------------- #

class Modal(tk.Toplevel):
    def __init__(self, parent: tk.Misc, title: str, width: int = 560,
                 subtitle: str = "", theme: Theme | None = None, resizable: bool = False):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.configure(bg=C.CARD)
        self.transient(parent.winfo_toplevel())
        self.resizable(resizable, resizable)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _e: self.close())
        self._theme = theme
        self._base_width = width
        self._result: Any = None
        self._closed = False

        header = tk.Frame(self, bg=C.CARD)
        header.pack(fill="x", padx=24, pady=(20, 0))
        tk.Label(header, text=title, bg=C.CARD, fg=C.TEXT,
                 font=(theme.font(14, "bold") if theme else ("Segoe UI", 14, "bold")),
                 anchor="w").pack(fill="x")
        if subtitle:
            tk.Label(header, text=subtitle, bg=C.CARD, fg=C.MUTED,
                     font=("Segoe UI", 9), anchor="w", justify="left",
                     wraplength=width - 48).pack(fill="x", pady=(3, 0))

        self.body = tk.Frame(self, bg=C.CARD)
        self.body.pack(fill="both", expand=True, padx=24, pady=(14, 0))
        self.footer = tk.Frame(self, bg=C.CARD)
        self.footer.pack(fill="x", padx=24, pady=(12, 18))
        self._buttons: list[ttk.Button] = []
        self._primary: ttk.Button | None = None
        self._error = tk.Label(self.footer, text="", bg=C.CARD, fg=C.RED,
                               font=("Segoe UI", 9), anchor="w", justify="left",
                               wraplength=width - 200)
        self._error.pack(side="left", fill="x", expand=True)
        self.bind("<Return>", self._on_return)

    # -- API ---------------------------------------------------------------- #
    def add_button(self, text: str, command: Callable[[], None], style: str = "TButton",
                   side: str | None = None) -> ttk.Button:
        button = ttk.Button(self.footer, text=text, command=command, style=style)
        self._buttons.append(button)
        if style in ("Accent.TButton", "Danger.TButton") and self._primary is None:
            self._primary = button
        self._relayout_footer()
        return button

    def _relayout_footer(self) -> None:
        for button in self._buttons:
            button.pack_forget()
        primary = self._primary
        if primary is not None:
            primary.pack(side="right", padx=(8, 0))
        for button in reversed([b for b in self._buttons if b is not primary]):
            button.pack(side="right", padx=(8, 0))

    def set_busy(self, busy: bool, text: str = "Guardando…") -> None:
        for button in self._buttons:
            button.configure(state="disabled" if busy else "normal")
        if busy:
            self._error.configure(text=text, fg=C.MUTED)
        elif self._error.cget("fg") == C.MUTED:
            self._error.configure(text="")

    def show_error(self, message: str) -> None:
        self._error.configure(text=message, fg=C.RED)
        self._relayout()

    def show_info(self, message: str) -> None:
        self._error.configure(text=message, fg=C.MUTED)

    def _on_return(self, _event: Any = None) -> None:
        focus = self.focus_get()
        if focus is not None and focus.winfo_class() in ("Text", "TCombobox"):
            return
        if self._primary is not None and str(self._primary.cget("state")) != "disabled":
            self._primary.invoke()

    def _relayout(self) -> None:
        try:
            self.update_idletasks()
        except tk.TclError:
            return

    def show(self) -> Any:
        self.update_idletasks()
        width = max(self._base_width, self.winfo_reqwidth())
        height = self.winfo_reqheight()
        screen_h = self.winfo_screenheight()
        if height > screen_h - 120:
            height = screen_h - 120
            self.resizable(True, True)
        parent = self.master.winfo_toplevel()
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - height) // 3
        except tk.TclError:
            x = (self.winfo_screenwidth() - width) // 2
            y = (screen_h - height) // 2
        x = max(10, min(x, self.winfo_screenwidth() - width - 10))
        y = max(10, min(y, screen_h - height - 40))
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()
        enable_dark_titlebar(self)
        self._dark_after = self.after(80, lambda: enable_dark_titlebar(self))
        self.lift()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_force()
        self.wait_window(self)
        return self._result

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        dark_after = getattr(self, "_dark_after", None)
        if dark_after is not None:
            try:
                self.after_cancel(dark_after)
            except tk.TclError:
                pass
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def finish(self, result: Any = True) -> None:
        self._result = result
        self.close()


class ConfirmDialog(Modal):
    def __init__(self, parent: tk.Misc, title: str, message: str,
                 confirm_text: str = "Confirmar", cancel_text: str = "Cancelar",
                 danger: bool = True, theme: Theme | None = None,
                 require_text: str = "", checkbox_text: str = ""):
        super().__init__(parent, title, width=460, theme=theme)
        tk.Label(self.body, text=message, bg=C.CARD, fg=C.DIM, font=("Segoe UI", 10),
                 justify="left", wraplength=400, anchor="w").pack(fill="x")
        self.require_var: tk.StringVar | None = None
        if require_text:
            tk.Label(self.body, text=f"Escribe «{require_text}» para confirmar:",
                     bg=C.CARD, fg=C.MUTED, font=("Segoe UI", 9),
                     anchor="w").pack(fill="x", pady=(14, 4))
            self.require_var = tk.StringVar()
            entry = ttk.Entry(self.body, textvariable=self.require_var)
            entry.pack(fill="x")
        self.checkbox_var: tk.BooleanVar | None = None
        if checkbox_text:
            self.checkbox_var = tk.BooleanVar(value=False)
            Checkbox(self.body, checkbox_text, variable=self.checkbox_var, bg=C.CARD).pack(
                fill="x", pady=(12, 0))

        self.add_button(cancel_text, self.close, style="TButton")
        self.confirm_button = self.add_button(confirm_text, self._confirm,
                                              style="Danger.TButton" if danger else "Accent.TButton")
        self._require_text = require_text
        self.bind("<Return>", lambda _e: self._confirm())

    def _confirm(self) -> None:
        if self._require_text and self.require_var is not None:
            typed = self.require_var.get().strip().casefold()
            expected = self._require_text.strip().casefold()
            if typed != expected:
                self.show_error("El texto no coincide.")
                return
        if self.checkbox_var is not None and not self.checkbox_var.get():
            self.show_error("Debes marcar la casilla para continuar.")
            return
        self.finish(True)


# --------------------------------------------------------------------------- #
# Toasts y tooltips
# --------------------------------------------------------------------------- #

class ToastManager:
    def __init__(self, root: tk.Misc):
        self._root = root
        self.host = tk.Frame(root, bg=C.CONTENT)
        self._place_host()
        self._count = 0
        self._visible = False
        self._timers: dict[tk.Frame, str] = {}

    def _place_host(self) -> None:
        self.host.place(relx=1.0, rely=1.0, x=-22, y=-74, anchor="se")

    def show(self, message: str, kind: str = "info", timeout: int = 4200) -> None:
        palette = {
            "info": (C.CARD_ALT, C.TEXT, C.BORDER),
            "success": (C.GREEN_SOFT, "#8ef0b4", C.GREEN),
            "error": (C.RED_SOFT, "#ffb3b5", C.RED),
            "warning": (C.YELLOW_SOFT, "#ffd98a", C.YELLOW),
        }
        bg, fg, border = palette.get(kind, palette["info"])
        if not self._visible:
            self._place_host()
            self._visible = True
        container = tk.Frame(self.host, bg=bg, highlightbackground=border,
                             highlightthickness=1)
        container.pack(side="bottom", pady=(8, 0), anchor="e")
        icon = {"info": "i", "success": "✓", "error": "!", "warning": "!"}.get(kind, "i")
        tk.Label(container, text=icon, bg=bg, fg=fg,
                 font=("Segoe UI", 10, "bold")).pack(side="left", padx=(12, 6), pady=10)
        tk.Label(container, text=truncate(message, 220), bg=bg, fg=fg,
                 font=("Segoe UI", 9), justify="left", wraplength=380,
                 anchor="w").pack(side="left", padx=(0, 8), pady=10)
        close = tk.Label(container, text="✕", bg=bg, fg=fg, font=("Segoe UI", 8),
                         cursor="hand2")
        close.pack(side="right", padx=(0, 10))
        close.bind("<Button-1>", lambda _e: self._dismiss(container))
        self._count += 1
        container.lift()
        self.host.lift()
        try:
            timer = container.after(timeout, lambda: self._dismiss(container))
            self._timers[container] = timer
        except tk.TclError:
            pass

    def _dismiss(self, container: tk.Frame) -> None:
        timer = self._timers.pop(container, None)
        if timer is not None:
            try:
                container.after_cancel(timer)
            except tk.TclError:
                pass
        try:
            container.destroy()
        except tk.TclError:
            pass
        try:
            if not self.host.winfo_children():
                self.host.place_forget()
                self._visible = False
        except tk.TclError:
            pass

    def shutdown(self) -> None:
        for container, timer in list(self._timers.items()):
            try:
                container.after_cancel(timer)
            except tk.TclError:
                pass
            try:
                container.destroy()
            except tk.TclError:
                pass
        self._timers.clear()


class Tooltip:
    def __init__(self, widget: tk.Misc, text: str, delay: int = 450):
        self._widget = widget
        self._text = text
        self._delay = delay
        self._after_id: str | None = None
        self._window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def update_text(self, text: str) -> None:
        self._text = text

    def _schedule(self, _event: Any = None) -> None:
        self._cancel()
        try:
            self._after_id = self._widget.after(self._delay, self._show)
        except tk.TclError:
            self._after_id = None

    def _cancel(self) -> None:
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _show(self) -> None:
        if self._window is not None or not self._text:
            return
        try:
            x = self._widget.winfo_rootx() + 12
            y = self._widget.winfo_rooty() + self._widget.winfo_height() + 6
        except tk.TclError:
            return
        window = tk.Toplevel(self._widget)
        window.wm_overrideredirect(True)
        window.configure(bg=C.BORDER)
        window.wm_geometry(f"+{x}+{y}")
        label = tk.Label(window, text=self._text, bg=C.CARD_ALT, fg=C.TEXT,
                         font=("Segoe UI", 8), justify="left", padx=8, pady=5,
                         wraplength=320)
        label.pack(padx=1, pady=1)
        self._window = window

    def _hide(self, _event: Any = None) -> None:
        self._cancel()
        if self._window is not None:
            try:
                self._window.destroy()
            except tk.TclError:
                pass
            self._window = None


def copy_to_clipboard(widget: tk.Misc, text: str) -> None:
    try:
        widget.clipboard_clear()
        widget.clipboard_append(text)
        widget.update_idletasks()
    except tk.TclError:
        pass


class ScrollableModal(Modal):
    """Modal con cuerpo desplazable para formularios largos."""

    def __init__(self, parent: tk.Misc, title: str, width: int = 620,
                 subtitle: str = "", theme: Theme | None = None,
                 desired_height: int = 620):
        super().__init__(parent, title, width=width, subtitle=subtitle, theme=theme)
        self._desired_height = desired_height
        self.scroll = ScrollFrame(self.body, bg=C.CARD)
        self.scroll.pack(fill="both", expand=True)
        self.content = self.scroll.inner

    def show(self) -> Any:
        self.update_idletasks()
        width = max(self._base_width, self.winfo_reqwidth())
        screen_h = self.winfo_screenheight()
        height = min(max(self.winfo_reqheight(), self._desired_height), screen_h - 140)
        parent = self.master.winfo_toplevel()
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + max(20, (parent.winfo_height() - height) // 4)
        x = max(10, min(x, self.winfo_screenwidth() - width - 10))
        y = max(10, min(y, screen_h - height - 40))
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()
        enable_dark_titlebar(self)
        self._dark_after = self.after(80, lambda: enable_dark_titlebar(self))
        self.lift()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_force()
        self.wait_window(self)
        return self._result
