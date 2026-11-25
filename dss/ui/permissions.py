"""Editor de permisos: cuadrícula con casillas y editor tri-estado de overwrites."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Sequence

from ..constants import PERMISSIONS, PERMISSION_BY_KEY, PERMISSION_CATEGORIES
from ..models import bits
from .theme import C
from .widgets import Checkbox, ScrollFrame, SearchEntry, Table, TableColumn, Tooltip

STATE_LABELS = {0: "Heredar", 1: "Permitir", -1: "Denegar"}


class PermissionGrid(tk.Frame):
    """Lista de permisos con casillas, agrupada por categorías y con búsqueda."""

    def __init__(self, parent: tk.Misc, app: Any, bits_value: int = 0,
                 on_change: Callable[[int], None] | None = None, height: int = 330):
        super().__init__(parent, bg=C.CARD, height=height)
        self.app = app
        self._on_change = on_change
        self._variables: dict[str, tk.BooleanVar] = {}
        self._rows: dict[str, Checkbox] = {}
        self._headers: list[tuple[str, tk.Widget]] = []
        self._enabled = True
        self.pack_propagate(False)

        search_row = tk.Frame(self, bg=C.CARD)
        search_row.pack(fill="x", pady=(0, 6))
        self.search = SearchEntry(search_row, placeholder="Buscar permiso…",
                                  on_change=lambda _t: self._filter(), width=26,
                                  bg=C.CARD, theme=app.theme)
        self.search.pack(side="left", fill="x", expand=True)
        self.count_label = tk.Label(search_row, text="", bg=C.CARD, fg=C.MUTED,
                                    font=app.theme.font(8))
        self.count_label.pack(side="right", padx=(8, 0))
        for text, action in (("Todos", True), ("Ninguno", False)):
            ttk.Button(search_row, text=text, style="Small.TButton",
                       command=lambda value=action: self._bulk(value)).pack(
                side="right", padx=(4, 0))

        self.scroll = ScrollFrame(self, bg=C.CARD)
        self.scroll.pack(fill="both", expand=True)
        grid = tk.Frame(self.scroll.inner, bg=C.CARD)
        grid.pack(fill="both", expand=True)
        grid.grid_columnconfigure(0, weight=0)
        grid.grid_columnconfigure(1, weight=0)
        row = 0
        for category_key, category_label in PERMISSION_CATEGORIES:
            items = [p for p in PERMISSIONS if p[2] == category_key]
            if not items:
                continue
            header = tk.Label(grid, text=category_label.upper(), bg=C.CARD, fg=C.MUTED,
                              font=app.theme.font(8, "bold"), anchor="w")
            header.grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 2))
            self._headers.append((category_key, header))
            row += 1
            for index, (key, bit, _cat, label, description) in enumerate(items):
                var = tk.BooleanVar(value=bool(bits_value & (1 << bit)))
                checkbox = Checkbox(grid, label, variable=var, bg=C.CARD,
                                    font=app.theme.font(9), command=self._changed)
                checkbox.grid(row=row + index // 2, column=index % 2, sticky="w",
                              padx=(0, 12), pady=1)
                Tooltip(checkbox, description)
                self._variables[key] = var
                self._rows[key] = checkbox
            row += (len(items) + 1) // 2
        self._update_count()

    # -- API ---------------------------------------------------------------- #
    def get_bits(self) -> int:
        value = 0
        for key, var in self._variables.items():
            if var.get():
                value |= 1 << PERMISSION_BY_KEY[key][1]
        return value

    def set_bits(self, value: int) -> None:
        for key, var in self._variables.items():
            var.set(bool(value & (1 << PERMISSION_BY_KEY[key][1])))
        self._update_count()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        for checkbox in self._rows.values():
            checkbox.set_enabled(enabled)

    # -- interno ------------------------------------------------------------ #
    def _bulk(self, value: bool) -> None:
        if not self._enabled:
            return
        for key, var in self._variables.items():
            checkbox = self._rows[key]
            if checkbox.winfo_ismapped():
                var.set(value)
        self._changed()

    def _changed(self) -> None:
        self._update_count()
        if self._on_change:
            self._on_change(self.get_bits())

    def _update_count(self) -> None:
        count = sum(1 for var in self._variables.values() if var.get())
        label = "permiso marcado" if count == 1 else "permisos marcados"
        self.count_label.configure(text=f"{count} {label}")

    def _filter(self) -> None:
        needle = self.search.value().lower()
        for key, checkbox in self._rows.items():
            definition = PERMISSION_BY_KEY[key]
            match = needle in definition[3].lower() or needle in definition[4].lower()
            if match:
                checkbox.grid()
            else:
                checkbox.grid_remove()
        for _category, header in self._headers:
            header.grid()


class OverwriteEditor(tk.Frame):
    """Editor de permisos por rol/canal con estados permitir/denegar/heredar."""

    def __init__(self, parent: tk.Misc, app: Any, allow: int = 0, deny: int = 0,
                 height: int = 13):
        super().__init__(parent, bg=C.CARD)
        self.app = app
        self._state: dict[str, int] = {}
        for key, bit, _cat, _label, _desc in PERMISSIONS:
            if allow & (1 << bit):
                self._state[key] = 1
            elif deny & (1 << bit):
                self._state[key] = -1
            else:
                self._state[key] = 0

        legend = tk.Frame(self, bg=C.CARD)
        legend.pack(fill="x", pady=(0, 6))
        tk.Label(legend, text="Haz clic en una fila para alternar: Heredar → Permitir → Denegar.",
                 bg=C.CARD, fg=C.MUTED, font=app.theme.font(8), anchor="w").pack(side="left")
        for text, action in (("Permitir todo", 1), ("Denegar todo", -1), ("Heredar todo", 0)):
            ttk.Button(legend, text=text, style="Small.TButton",
                       command=lambda value=action: self._set_all(value)).pack(
                side="right", padx=(4, 0))

        columns = [TableColumn("perm", "Permiso", 260, stretch=True),
                   TableColumn("state", "Estado", 110, anchor="center")]
        self.table = Table(self, columns, height=height, multi=False, theme=app.theme)
        self.table.pack(fill="both", expand=True)
        self.table.tree.bind("<Button-1>", self._on_click)
        self._render()

    def _render(self) -> None:
        rows = []
        for key, _bit, _cat, label, _desc in PERMISSIONS:
            state = self._state[key]
            tags = ("success",) if state == 1 else (("danger",) if state == -1 else ("muted",))
            rows.append({"_id": key, "perm": label, "state": STATE_LABELS[state],
                         "_tags": tags, "_state": state})
        self.table.set_rows(rows)

    def _on_click(self, event: Any) -> None:
        row_id = self.table.tree.identify_row(event.y)
        if not row_id:
            return
        current = self._state.get(row_id, 0)
        self._state[row_id] = 1 if current == 0 else (-1 if current == 1 else 0)
        self._render()

    def _set_all(self, value: int) -> None:
        for key in self._state:
            self._state[key] = value
        self._render()

    def get_allow_deny(self) -> tuple[int, int]:
        allow = deny = 0
        for key, state in self._state.items():
            bit = PERMISSION_BY_KEY[key][1]
            if state == 1:
                allow |= 1 << bit
            elif state == -1:
                deny |= 1 << bit
        return allow, deny

    def set_allow_deny(self, allow: int, deny: int) -> None:
        for key, bit, _cat, _label, _desc in PERMISSIONS:
            if allow & (1 << bit):
                self._state[key] = 1
            elif deny & (1 << bit):
                self._state[key] = -1
            else:
                self._state[key] = 0
        self._render()
