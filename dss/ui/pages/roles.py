"""Gestión de roles: nombre, color, visibilidad y permisos."""
from __future__ import annotations

import base64
import re
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, ttk
from typing import Any

from ...constants import ROLE_COLOR_PRESETS
from ...models import Role, color_to_hex
from ..permissions import PermissionGrid
from ..theme import C
from ..widgets import (Card, Checkbox, ConfirmDialog, EmptyState, Field, Modal,
                       PageHeader, ScrollFrame, TabBar, copy_to_clipboard, round_rect)
from .base import Page
from .bulk_roles import BulkRolesTab

HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


def color_to_int(value: str) -> int | None:
    match = HEX_RE.match(value.strip())
    return int(match.group(1), 16) if match else None


class RolesPage(Page):
    key = "roles"
    label = "Roles"
    glyph = "◆"

    def build(self) -> None:
        app = self.app
        self.header = PageHeader(self, app, "Roles",
                                 "Los roles definen qué puede hacer cada miembro. "
                                 "La jerarquía va de arriba hacia abajo.")
        self.header.pack(fill="x", padx=28, pady=(22, 0))
        self._manage = app.can("MANAGE_ROLES")

        self.tabs = TabBar(self, [("roles", "Roles"),
                                  ("bulk", "Gestionar roles masivos")],
                           on_change=self._switch, theme=app.theme)
        self.tabs.pack(fill="x", padx=28, pady=(8, 0))
        self.container = tk.Frame(self, bg=C.CONTENT)
        self.container.pack(fill="both", expand=True)

        self.roles_tab = tk.Frame(self.container, bg=C.CONTENT)
        self.bulk = BulkRolesTab(self.container, app, self)
        self._active_tab = ""
        self._build_roles_tab()
        self.tabs.select("roles")

    def _build_roles_tab(self) -> None:
        app = self.app
        toolbar = tk.Frame(self.roles_tab, bg=C.CONTENT)
        toolbar.pack(fill="x", padx=28, pady=(10, 0))
        self.btn_new = ttk.Button(toolbar, text="Nuevo rol", style="Accent.TButton",
                                  command=self.create_role)
        self.btn_new.pack(side="left")
        if not self._manage:
            self.btn_new.configure(state="disabled")
        tk.Label(toolbar, text="Arrastra un rol para reordenar · cambios en el servidor actual.",
                 bg=C.CONTENT, fg=C.FAINT, font=app.theme.font(8)).pack(side="right")

        body = tk.Frame(self.roles_tab, bg=C.CONTENT)
        body.pack(fill="both", expand=True, padx=28, pady=(14, 20))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=0, minsize=280)
        body.grid_columnconfigure(1, weight=1)

        left = tk.Frame(body, bg=C.CARD, width=280, highlightbackground=C.BORDER_SOFT,
                        highlightthickness=1)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        left.grid_propagate(False)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)
        top = tk.Frame(left, bg=C.CARD)
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        self.count_label = tk.Label(top, text="", bg=C.CARD, fg=C.DIM,
                                    font=app.theme.font(9, "bold"), anchor="w")
        self.count_label.pack(side="left")
        tk.Label(top, text="de mayor a menor", bg=C.CARD, fg=C.FAINT,
                 font=app.theme.font(8)).pack(side="right")
        self.list_scroll = ScrollFrame(left, bg=C.CARD)
        self.list_scroll.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 8))

        self.right = tk.Frame(body, bg=C.CONTENT)
        self.right.grid(row=0, column=1, sticky="nsew")

        self.selected_id: str | None = None
        self._roles: list[Role] = []
        self.grid: PermissionGrid | None = None

    def _switch(self, key: str) -> None:
        if not hasattr(self, "roles_tab"):
            return
        self._active_tab = key
        for frame in (self.roles_tab, self.bulk):
            frame.pack_forget()
        if key == "roles":
            self.roles_tab.pack(fill="both", expand=True)
        else:
            self.bulk.pack(fill="both", expand=True)
            self.bulk.on_show()

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        self._roles = self._ordered_roles()
        ids = {role.id for role in self._roles}
        if self.selected_id not in ids:
            self.selected_id = self._roles[0].id if self._roles else None
        self.count_label.configure(text=f"{len(self._roles)} roles")
        self.bulk.set_roles(self._roles)
        self._render_list()
        self._render_editor()

    def on_guild_refreshed(self) -> None:
        if not self.is_dirty():
            self.refresh()
            return
        self._roles = self._ordered_roles()
        self.count_label.configure(text=f"{len(self._roles)} roles")
        self.bulk.set_roles(self._roles)
        self._render_list()

    def _ordered_roles(self) -> list[Role]:
        roles = self.app.guild.sorted_roles()
        everyone = [role for role in roles if role.is_everyone]
        return [role for role in roles if not role.is_everyone] + everyone

    def is_dirty(self) -> bool:
        if not hasattr(self, "name_var"):
            return False
        role = next((r for r in self._roles if r.id == self.selected_id), None)
        if role is None or self.grid is None:
            return False
        raw_color = self.hex_var.get().strip()
        color = 0 if not raw_color else color_to_int(raw_color)
        if color is None:
            return True
        return (self.name_var.get().strip() != role.name
                or color != role.color
                or bool(self.hoist_var.get()) != role.hoist
                or bool(self.mention_var.get()) != role.mentionable
                or self.grid.get_bits() != role.permissions
                or bool(getattr(self, "icon_dirty", False)))

    # ------------------------------------------------------------------ #
    def _render_list(self) -> None:
        self.list_scroll.clear()
        inner = self.list_scroll.inner
        self._drag_role = None
        self._drag_started = False
        self._drag_target = None
        self._drag_rows: list[tuple[Role, tk.Frame]] = []
        self._drop_line = tk.Frame(inner, bg=C.ACCENT, height=2)
        self._drop_line.place_forget()
        for role in self._roles:
            selected = role.id == self.selected_id
            bg = C.ACCENT_SOFT if selected else C.CARD
            row = tk.Frame(inner, bg=bg, cursor="hand2")
            row.pack(fill="x", padx=4, pady=1)
            line = tk.Frame(row, bg=bg)
            line.pack(fill="x", padx=10, pady=6)
            swatch = tk.Canvas(line, width=14, height=14, bg=bg, highlightthickness=0)
            swatch.pack(side="left")
            swatch.create_oval(1, 1, 13, 13, fill=role.color_hex,
                               outline=C.BORDER_SOFT if not role.color else "")
            name = tk.Label(line, text=role.name, bg=bg,
                            fg=C.TEXT if selected else C.DIM,
                            font=self.app.theme.font(9, "bold"), anchor="w")
            name.pack(side="left", padx=(8, 0), fill="x", expand=True)
            if role.is_everyone or role.managed or role.is_admin:
                badge = "@everyone" if role.is_everyone else ("Bot" if role.managed else "Admin")
                tk.Label(line, text=badge, bg=bg, fg=C.FAINT,
                         font=self.app.theme.font(8)).pack(side="right")
            tk.Label(line, text=str(role.position), bg=bg, fg=C.FAINT,
                     font=(self.app.theme.mono_family, 8)).pack(side="right", padx=(0, 6))
            widgets = [row, line, *line.winfo_children()]
            for widget in widgets:
                self._bind_drag(widget, role)
            if not selected:
                for widget in widgets:
                    widget.bind("<Enter>", lambda _e, r=row, ln=line: self._hover(r, ln, True))
                    widget.bind("<Leave>", lambda _e, r=row, ln=line: self._hover(r, ln, False))
            self._drag_rows.append((role, row))
        self.list_scroll.refresh_scroll()

    def _bind_drag(self, widget: tk.Widget, role: Role) -> None:
        widget.bind("<ButtonPress-1>", lambda event, r=role: self._drag_press(r, event))
        widget.bind("<B1-Motion>", self._drag_motion)
        widget.bind("<ButtonRelease-1>", self._drag_release)
        widget.bind("<Escape>", lambda _event: self._drag_cancel())

    def _drag_press(self, role: Role, event: tk.Event) -> None:
        if role.is_everyone:
            self._select(role)
            return
        if not self._manage or role.managed:
            self._select(role)
            return
        self._drag_role = role
        self._drag_started = False
        self._drag_target = None
        self._drag_origin = (event.x_root, event.y_root)
        self.list_scroll.inner.configure(cursor="fleur")

    def _drag_motion(self, event: tk.Event) -> None:
        if self._drag_role is None:
            return
        dx = abs(event.x_root - self._drag_origin[0])
        dy = abs(event.y_root - self._drag_origin[1])
        if not self._drag_started and dx + dy < 6:
            return
        self._drag_started = True
        inner = self.list_scroll.inner
        y = event.y_root - inner.winfo_rooty()
        target = len(self._drag_rows)
        for index, (_role, row) in enumerate(self._drag_rows):
            if y < row.winfo_y() + max(1, row.winfo_height()) / 2:
                target = index
                break
        target = self._bounded_drop_target(target)
        self._drag_target = target
        if target < len(self._drag_rows):
            line_y = self._drag_rows[target][1].winfo_y()
        elif self._drag_rows:
            last = self._drag_rows[-1][1]
            line_y = last.winfo_y() + last.winfo_height()
        else:
            line_y = 0
        self._drop_line.place(x=4, y=max(0, line_y - 1), relwidth=1, height=2)
        self._auto_scroll(event)

    def _bounded_drop_target(self, target: int) -> int:
        """@everyone nunca es un destino de inserción debajo de sí mismo."""
        if self._drag_rows and self._drag_rows[-1][0].is_everyone:
            return min(target, len(self._drag_rows) - 1)
        return target

    def _auto_scroll(self, event: tk.Event) -> None:
        canvas = self.list_scroll._canvas
        pointer = event.y_root - canvas.winfo_rooty()
        if pointer < 24:
            canvas.yview_scroll(-1, "units")
        elif pointer > canvas.winfo_height() - 24:
            canvas.yview_scroll(1, "units")

    def _drag_release(self, event: tk.Event) -> None:
        role = self._drag_role
        if role is None:
            return
        started = self._drag_started
        target = self._drag_target
        if target is not None:
            target = self._bounded_drop_target(target)
        self._reset_drag()
        if not started:
            self._select(role)
            return
        order = [item for item, _row in self._drag_rows if not item.is_everyone]
        if role not in order:
            return
        source = order.index(role)
        if target is None:
            self._select(role)
            return
        if target >= len(self._drag_rows) or self._drag_rows[target][0].is_everyone:
            insert = len(order)
        else:
            insert = target
        if insert > source:
            insert -= 1
        insert = max(0, min(insert, len(order)))
        new_order = order[:]
        new_order.pop(source)
        new_order.insert(insert, role)
        self._select(role)
        if new_order == order or not self._manage:
            return
        position = len(order) - insert
        self._reorder(role, position)

    def _reset_drag(self) -> None:
        self._drag_role = None
        self._drag_started = False
        self._drag_target = None
        if hasattr(self, "_drop_line"):
            try:
                self._drop_line.place_forget()
            except tk.TclError:
                pass
        try:
            self.list_scroll.inner.configure(cursor="")
        except tk.TclError:
            pass

    def _drag_cancel(self) -> None:
        self._reset_drag()

    @staticmethod
    def _hover(row: tk.Frame, line: tk.Frame, entering: bool) -> None:
        color = C.CARD_ALT if entering else C.CARD
        for widget in (row, line, *line.winfo_children()):
            try:
                widget.configure(bg=color)
            except tk.TclError:
                pass

    def _select(self, role: Role) -> None:
        self.selected_id = role.id
        self._render_list()
        self._render_editor()

    # ------------------------------------------------------------------ #
    def _render_editor(self) -> None:
        for child in self.right.winfo_children():
            child.destroy()
        role = next((r for r in self._roles if r.id == self.selected_id), None)
        if role is None:
            EmptyState(self.right, "Ningún rol seleccionado",
                       "Elige un rol de la lista para editarlo.", bg=C.CONTENT).pack(expand=True)
            return
        app = self.app
        panel = tk.Frame(self.right, bg=C.CONTENT)
        panel.pack(fill="both", expand=True)
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        scroll = ScrollFrame(panel, bg=C.CONTENT)
        scroll.grid(row=0, column=0, sticky="nsew")
        card = Card(scroll.inner, padding=20)
        card.pack(fill="both", expand=True)
        body = card.body

        head = tk.Frame(body, bg=C.CARD)
        head.pack(fill="x", pady=(0, 2))
        self.swatch = tk.Canvas(head, width=22, height=22, bg=C.CARD, highlightthickness=0)
        self.swatch.pack(side="left")
        round_rect(self.swatch, 1, 1, 21, 21, 7, fill=role.color_hex, outline=C.BORDER)
        tk.Label(head, text=role.name, bg=C.CARD, fg=C.TEXT,
                 font=app.theme.font(15, "bold")).pack(side="left", padx=(10, 8))
        if role.is_everyone:
            tk.Label(head, text="ROL BASE", bg=C.CARD_ALT, fg=C.DIM,
                     font=app.theme.font(8, "bold"), padx=7, pady=2).pack(side="left")
        if role.managed:
            tk.Label(head, text="GESTIONADO POR UNA APP", bg=C.CARD_ALT, fg=C.DIM,
                     font=app.theme.font(8, "bold"), padx=7, pady=2).pack(side="left")
        copy = tk.Label(head, text="copiar ID", bg=C.CARD, fg=C.LINK,
                        font=app.theme.font(8), cursor="hand2")
        copy.pack(side="right")
        copy.bind("<Button-1>", lambda _e: self._copy(role.id))
        tk.Label(body, text=f"Posición {role.position} · ID {role.id}", bg=C.CARD,
                 fg=C.FAINT, font=(app.theme.mono_family, 8), anchor="w").pack(
            fill="x", pady=(2, 14))

        if not self._manage:
            tk.Label(body, text="Solo lectura: falta el permiso «Gestionar roles».",
                     bg=C.YELLOW_SOFT, fg="#ffd98a", font=app.theme.font(8),
                     anchor="w", padx=10, pady=6).pack(fill="x", pady=(0, 12))
        if role.managed:
            tk.Label(
                body,
                text="ROL GESTIONADO POR UNA APP · Discord no permite editar sus permisos "
                     "desde el panel. Edítalo en Discord (Ajustes del servidor → Roles) o "
                     "vuelve a invitar el bot con Administrador. Para permisos propios, crea "
                     "un rol normal o usa @everyone.",
                bg=C.YELLOW_SOFT, fg="#ffd98a", font=app.theme.font(8),
                anchor="w", justify="left", padx=10, pady=6, wraplength=680).pack(
                    fill="x", pady=(0, 12))

        self._role_frames: dict[str, tk.Frame] = {}
        self._role = role
        self.role_tabs = TabBar(
            body,
            [("view", "Visualizar"), ("perms", "Permisos"), ("links", "Enlaces"),
             ("members", "Miembros")],
            on_change=self._switch_role_tab, theme=app.theme)
        self.role_tabs.pack(fill="x", pady=(0, 8))
        self.role_host = tk.Frame(body, bg=C.CARD)
        self.role_host.pack(fill="both", expand=True)
        self._build_view_tab(role)
        self._build_permissions_tab(role)
        self._build_links_tab(role)
        self._build_members_tab(role)
        self.role_tabs.select("view")

        footer = tk.Frame(panel, bg=C.CARD, highlightbackground=C.BORDER_SOFT,
                          highlightthickness=1)
        footer.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        footer_inner = tk.Frame(footer, bg=C.CARD)
        footer_inner.pack(fill="x", padx=16, pady=10)
        self.delete_button = ttk.Button(footer_inner, text="Eliminar rol",
                                        style="SmallDanger.TButton",
                                        command=lambda: self._delete(role))
        self.delete_button.pack(side="left")
        if role.is_everyone or role.managed:
            for button in (self.delete_button,):
                button.configure(state="disabled")
            self.name_entry.configure(state="readonly")
            self.hex_entry.configure(state="readonly")
            self.color_button.configure(state="disabled")
            self.hoist_check.set_enabled(False)
            self.mention_check.set_enabled(False)
        for text, delta in (("↑", -1), ("↓", 1)):
            ttk.Button(footer_inner, text=text, style="Small.TButton", width=2,
                       command=lambda d=delta: self._move(role, d)).pack(
                side="left", padx=(6, 0))
        self.save_button = ttk.Button(footer_inner, text="Guardar cambios",
                                      style="Accent.TButton",
                                      command=lambda: self._save(role))
        self.save_button.pack(side="right")
        if not self._manage or role.managed:
            self.save_button.configure(state="disabled")

    # ------------------------------------------------------------------ #
    def _tab_frame(self, key: str) -> tk.Frame:
        frame = tk.Frame(self.role_host, bg=C.CARD)
        self._role_frames[key] = frame
        return frame

    def _switch_role_tab(self, key: str) -> None:
        if not getattr(self, "_role_frames", None):
            return
        for frame in self._role_frames.values():
            frame.pack_forget()
        frame = self._role_frames.get(key)
        if frame is not None:
            frame.pack(fill="both", expand=True)
        if key == "members":
            self._ensure_role_members()

    def _build_view_tab(self, role: Role) -> None:
        app = self.app
        view = self._tab_frame("view")
        top_row = tk.Frame(view, bg=C.CARD)
        top_row.pack(fill="x", pady=(0, 12))
        name_field = Field(top_row, "Nombre del rol")
        name_field.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.name_var = tk.StringVar(value=role.name)
        self.name_entry = ttk.Entry(name_field.slot, textvariable=self.name_var)
        name_field.add(self.name_entry)

        color_field = Field(top_row, "Color", "Hex o paleta; vacío = sin color")
        color_field.pack(side="left", fill="x", expand=False)
        color_box = tk.Frame(color_field.slot, bg=C.CARD)
        color_box.pack(fill="x")
        self.hex_var = tk.StringVar(value="" if role.color == 0 else role.color_hex)
        self.hex_entry = ttk.Entry(color_box, textvariable=self.hex_var, width=9)
        self.hex_entry.pack(side="left")
        self.color_button = tk.Button(color_box, text="…", bg=C.CARD_ALT, fg=C.TEXT,
                                      activebackground=C.BORDER, activeforeground=C.TEXT,
                                      relief="flat", bd=0, padx=8, pady=3,
                                      font=app.theme.font(10, "bold"),
                                      command=self._pick_color)
        self.color_button.pack(side="left", padx=(6, 0))
        self.hex_var.trace_add("write", lambda *_: self._update_swatch())

        palette = tk.Frame(view, bg=C.CARD)
        palette.pack(fill="x", pady=(0, 12))
        for color in ROLE_COLOR_PRESETS:
            chip = tk.Canvas(palette, width=18, height=18, bg=C.CARD, highlightthickness=0,
                             cursor="hand2")
            chip.pack(side="left", padx=(0, 4))
            round_rect(chip, 1, 1, 17, 17, 5, fill=color, outline=C.BORDER_SOFT)
            chip.bind("<Button-1>", lambda _e, c=color: self.hex_var.set(c))
        clear = tk.Label(palette, text="sin color", bg=C.CARD, fg=C.LINK,
                         font=app.theme.font(8), cursor="hand2")
        clear.pack(side="left", padx=(8, 0))
        clear.bind("<Button-1>", lambda _e: self.hex_var.set(""))

        toggles = tk.Frame(view, bg=C.CARD)
        toggles.pack(fill="x", pady=(0, 10))
        self.hoist_var = tk.BooleanVar(value=role.hoist)
        self.mention_var = tk.BooleanVar(value=role.mentionable)
        self.hoist_check = Checkbox(toggles, "Mostrar por separado en la lista de miembros",
                                    variable=self.hoist_var, bg=C.CARD,
                                    font=app.theme.font(9))
        self.hoist_check.pack(fill="x")
        self.mention_check = Checkbox(toggles, "Permitir mencionar este rol",
                                      variable=self.mention_var, bg=C.CARD,
                                      font=app.theme.font(9))
        self.mention_check.pack(fill="x", pady=(4, 0))
        self._build_role_icon(view, role)

    def _build_role_icon(self, parent: tk.Frame, role: Role) -> None:
        app = self.app
        box = tk.Frame(parent, bg=C.CARD)
        box.pack(fill="x", pady=(0, 10))
        tk.Label(box, text="ICONO DEL ROL", bg=C.CARD, fg=C.MUTED,
                 font=app.theme.font(8, "bold"), anchor="w").pack(fill="x")
        row = tk.Frame(box, bg=C.CARD)
        row.pack(fill="x", pady=(4, 0))
        self.icon_preview = tk.Label(row, text="—", bg=C.CARD_ALT, fg=C.TEXT,
                                     font=app.theme.font(13, "bold"), width=4, height=2,
                                     anchor="center")
        self.icon_preview.pack(side="left")
        self.icon_data: str | None = None
        self.icon_dirty = False
        self._icon_photo = None
        self.icon_emoji_var = tk.StringVar(value=role.unicode_emoji or "")
        self.icon_emoji_var.trace_add("write", lambda *_: self._icon_emoji_changed())
        controls = tk.Frame(row, bg=C.CARD)
        controls.pack(side="left", fill="x", expand=True, padx=(10, 0))
        emoji_row = tk.Frame(controls, bg=C.CARD)
        emoji_row.pack(fill="x")
        tk.Label(emoji_row, text="Emoji", bg=C.CARD, fg=C.MUTED,
                 font=app.theme.font(8)).pack(side="left")
        self.icon_emoji_entry = ttk.Entry(emoji_row, textvariable=self.icon_emoji_var,
                                          width=8)
        self.icon_emoji_entry.pack(side="left", padx=(6, 8))
        self.icon_upload_button = ttk.Button(emoji_row, text="Imagen…",
                                             style="Small.TButton",
                                             command=self._pick_role_icon)
        self.icon_upload_button.pack(side="left")
        self.icon_clear_button = ttk.Button(emoji_row, text="Quitar",
                                            style="Small.TButton",
                                            command=self._clear_role_icon)
        self.icon_clear_button.pack(side="left", padx=(6, 0))
        tier = int(getattr(app.guild, "premium_tier", 0) or 0)
        enabled = (tier >= 2 and self._manage and not role.managed
                   and not role.is_everyone)
        self._icon_enabled = enabled
        if not enabled:
            for widget in (self.icon_emoji_entry, self.icon_upload_button,
                           self.icon_clear_button):
                widget.configure(state="disabled")
        if tier < 2:
            hint = f"Requiere Nivel 2 de mejoras (actual: {tier})."
        elif role.is_everyone:
            hint = "El rol @everyone no tiene icono."
        elif role.managed:
            hint = "Rol de app: no editable desde el panel."
        elif not self._manage:
            hint = "Falta «Gestionar roles»."
        else:
            hint = "PNG/JPG/GIF/WebP hasta 256 KB."
        tk.Label(controls, text=hint, bg=C.CARD, fg=C.FAINT,
                 font=app.theme.font(8), anchor="w").pack(fill="x", pady=(4, 0))
        self._show_role_icon(role)

    def _show_role_icon(self, role: Role) -> None:
        if self.icon_data:
            self.icon_preview.configure(text="IMG", image="")
            return
        emoji = self.icon_emoji_var.get().strip()
        if emoji:
            self.icon_preview.configure(text=emoji, image="")
            return
        if role.icon and not role.icon.startswith("data:"):
            url = (f"https://cdn.discordapp.com/role-icons/{role.id}/"
                   f"{role.icon}.png?size=64")
            self.icon_preview.configure(text="…", image="")

            def apply(photo: tk.PhotoImage | None) -> None:
                if photo is not None:
                    self._icon_photo = photo
                    try:
                        self.icon_preview.configure(image=photo, text="")
                    except tk.TclError:
                        pass

            self.app.images.get(url, 40, apply)
            return
        self.icon_preview.configure(text="—", image="")

    def _icon_emoji_changed(self) -> None:
        if not hasattr(self, "icon_data"):
            return
        self.icon_data = None
        self.icon_dirty = True
        self._show_role_icon(self._role)

    def _pick_role_icon(self) -> None:
        if not getattr(self, "_icon_enabled", False):
            return
        path = filedialog.askopenfilename(
            parent=self, title="Icono del rol",
            filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.gif *.webp"),
                       ("Todos", "*.*")])
        if not path:
            return
        try:
            raw = Path(path).read_bytes()
        except OSError as error:
            self.toast_warn(f"No se pudo leer la imagen: {error}")
            return
        if len(raw) > 256 * 1024:
            self.toast_warn("La imagen supera 256 KB.")
            return
        suffix = Path(path).suffix.lower()
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".gif": "image/gif", ".webp": "image/webp"}.get(suffix, "image/png")
        encoded = base64.b64encode(raw).decode("ascii")
        self.icon_emoji_var.set("")
        self.icon_data = f"data:{mime};base64,{encoded}"
        self.icon_dirty = True
        try:
            self._icon_photo = tk.PhotoImage(data=encoded)
            self.icon_preview.configure(image=self._icon_photo, text="")
        except tk.TclError:
            self._show_role_icon(self._role)

    def _clear_role_icon(self) -> None:
        if not getattr(self, "_icon_enabled", False):
            return
        self.icon_emoji_var.set("")
        self.icon_data = None
        self.icon_dirty = True
        self.icon_preview.configure(image="", text="—")

    def _build_permissions_tab(self, role: Role) -> None:
        app = self.app
        frame = self._tab_frame("perms")
        label_row = tk.Frame(frame, bg=C.CARD)
        label_row.pack(fill="x", pady=(4, 4))
        tk.Label(label_row, text="PERMISOS DEL ROL", bg=C.CARD, fg=C.MUTED,
                 font=app.theme.font(8, "bold"), anchor="w").pack(side="left")
        self.grid = PermissionGrid(frame, app, role.permissions,
                                   on_change=self._permissions_changed, height=300)
        self.grid.pack(fill="both", expand=True)
        if not self._manage or role.managed:
            self.grid.set_enabled(False)
        self._permissions_changed(role.permissions)

    def _build_links_tab(self, role: Role) -> None:
        app = self.app
        frame = self._tab_frame("links")
        tk.Label(frame, text="ENLACES · ROL VINCULADO", bg=C.CARD, fg=C.MUTED,
                 font=app.theme.font(8, "bold"), anchor="w").pack(fill="x", pady=(4, 6))
        tk.Label(
            frame,
            text="Discord no permite crear ni modificar los requisitos de un rol "
                 "vinculado mediante la API del bot. Los requisitos se configuran en "
                 "Discord: Ajustes del servidor → Roles → Enlaces.",
            bg=C.YELLOW_SOFT, fg="#ffd98a", font=app.theme.font(8),
            anchor="w", justify="left", wraplength=700, padx=10, pady=8).pack(
                fill="x", pady=(0, 10))
        tk.Label(
            frame,
            text="Condiciones de Discord:\n"
                 "• Solo se pueden añadir requisitos de conexión o aplicación a un rol "
                 "que no tenga miembros.\n"
                 "• Si el rol ya tiene miembros, crea un rol nuevo y configúralo como "
                 "vinculado en Discord.\n"
                 "• El JSON masivo muestra estos enlaces como «manual»: no los aplica.",
            bg=C.CARD, fg=C.DIM, font=app.theme.font(9), anchor="w", justify="left",
            wraplength=700).pack(fill="x")
        if role.is_everyone:
            tk.Label(frame, text="El rol @everyone no puede ser un rol vinculado.",
                     bg=C.CARD, fg=C.FAINT, font=app.theme.font(8),
                     anchor="w").pack(fill="x", pady=(10, 0))

    def _build_members_tab(self, role: Role) -> None:
        app = self.app
        frame = self._tab_frame("members")
        self._role_members: list[Any] = []
        self._members_loaded_for: str | None = None
        self._members_can_edit = (
            self._manage and not role.managed and not role.is_everyone)
        self.member_status = tk.Label(frame, text="Abre la pestaña para cargar miembros.",
                                      bg=C.CARD, fg=C.MUTED, font=app.theme.font(8),
                                      anchor="w")
        self.member_status.pack(fill="x", pady=(4, 6))
        add_row = tk.Frame(frame, bg=C.CARD)
        add_row.pack(fill="x", pady=(0, 8))
        tk.Label(add_row, text="ID de usuario", bg=C.CARD, fg=C.MUTED,
                 font=app.theme.font(8)).pack(side="left")
        self.member_add_var = tk.StringVar()
        self.member_add_entry = ttk.Entry(add_row, textvariable=self.member_add_var,
                                          width=24)
        self.member_add_entry.pack(side="left", padx=(6, 6))
        self.member_add_button = ttk.Button(add_row, text="Añadir", style="Small.TButton",
                                            command=self._add_member)
        self.member_add_button.pack(side="left")
        if not self._members_can_edit:
            self.member_add_entry.configure(state="disabled")
            self.member_add_button.configure(state="disabled")
        self.member_list = ScrollFrame(frame, bg=C.CARD)
        self.member_list.pack(fill="both", expand=True)
        self.member_note = tk.Label(frame, text="", bg=C.CARD, fg=C.FAINT,
                                    font=app.theme.font(8), anchor="w")
        self.member_note.pack(fill="x", pady=(4, 0))

    def _ensure_role_members(self) -> None:
        role = getattr(self, "_role", None)
        if role is None or self._members_loaded_for == role.id:
            return
        if self.app.client is None or self.app.guild is None:
            return
        self._members_loaded_for = role.id
        self.member_status.configure(text="Cargando miembros…")
        guild_id = self.app.guild.id

        def done(members: list[Any]) -> None:
            self._role_members = [m for m in members if role.id in m.roles]
            count = len(self._role_members)
            self.member_status.configure(text=f"{count} miembros con este rol")
            try:
                self.role_tabs._buttons["members"].configure(text=f"Miembros ({count})")
            except (KeyError, tk.TclError):
                pass
            self._render_role_members()

        def failed(error: BaseException) -> None:
            self._members_loaded_for = None
            if getattr(error, "status", None) == 50001:
                self.member_status.configure(
                    text="No se pudieron cargar: activa Server Members Intent en el "
                         "Portal de Desarrolladores → Bot → Privileged Gateway Intents. "
                         "No es un permiso del rol.")
            else:
                self.member_status.configure(text=f"No se pudieron cargar: {error}")

        self.run(lambda: self.app.client.list_members(guild_id, 1000), done, failed)

    def _render_role_members(self) -> None:
        self.member_list.clear()
        inner = self.member_list.inner
        if not self._role_members:
            tk.Label(inner, text="Ningún miembro tiene este rol.", bg=C.CARD,
                     fg=C.MUTED, font=self.app.theme.font(9)).pack(pady=12)
            self.member_note.configure(text="")
            return
        shown = self._role_members[:120]
        for member in shown:
            row = tk.Frame(inner, bg=C.CARD)
            row.pack(fill="x", padx=4, pady=2)
            tk.Label(row, text=member.user.display_name, bg=C.CARD, fg=C.TEXT,
                     font=self.app.theme.font(9, "bold"), anchor="w").pack(
                side="left", fill="x", expand=True)
            tk.Label(row, text=member.user.id, bg=C.CARD, fg=C.FAINT,
                     font=(self.app.theme.mono_family, 8)).pack(side="right", padx=(0, 6))
            button = ttk.Button(row, text="Quitar", style="SmallDanger.TButton",
                                command=lambda m=member: self._remove_member(m))
            button.pack(side="right", padx=(0, 8))
            if not self._members_can_edit:
                button.configure(state="disabled")
        extra = len(self._role_members) - len(shown)
        self.member_note.configure(
            text=(f"Mostrando {len(shown)} de {len(self._role_members)}; el contador "
                  "incluye los cargados (máx. 1000)." if extra > 0 else ""))

    def _add_member(self) -> None:
        if not self._members_can_edit:
            return
        user_id = self.member_add_var.get().strip()
        if not user_id:
            self.toast_warn("Escribe el ID de usuario.")
            return
        self._change_role_member(user_id, True)

    def _remove_member(self, member: Any) -> None:
        if self._members_can_edit:
            self._change_role_member(member.user.id, False)

    def _change_role_member(self, user_id: str, add: bool) -> None:
        role = self._role
        guild_id = self.app.guild.id
        client = self.app.client

        def work() -> None:
            member = client.get_member(guild_id, user_id)
            roles = set(member.roles)
            if add:
                roles.add(role.id)
            else:
                roles.discard(role.id)
            client.update_member(guild_id, user_id, {"roles": sorted(roles)})

        def done(_result: Any) -> None:
            self.toast_ok(
                f"{'Miembro añadido' if add else 'Miembro quitado'} del rol «{role.name}».")
            self.member_add_var.set("")
            self._members_loaded_for = None
            self._ensure_role_members()

        def failed(error: BaseException) -> None:
            self.toast_warn(f"No se pudo actualizar el miembro: {error}")

        self.run(work, done, failed)

    # ------------------------------------------------------------------ #
    def _permissions_changed(self, value: int) -> None:
        if getattr(self, "permission_count", None) is not None:
            count = bin(value & 0xFFFFFFFFFFFF).count("1")
            label = "permiso marcado" if count == 1 else "permisos marcados"
            extra = " · administrador total" if value & (1 << 3) else ""
            self.permission_count.configure(text=f"{count} {label}{extra}")

    def _update_swatch(self) -> None:
        value = color_to_int(self.hex_var.get()) if self.hex_var.get().strip() else 0
        color = color_to_hex(value or 0, default="#99aab5")
        self.swatch.delete("all")
        round_rect(self.swatch, 1, 1, 21, 21, 7, fill=color, outline=C.BORDER)

    def _pick_color(self) -> None:
        initial = self.hex_var.get() or "#5865f2"
        rgb, hex_color = colorchooser.askcolor(color=initial, parent=self,
                                               title="Color del rol")
        if hex_color:
            self.hex_var.set(hex_color)
            self._update_swatch()

    def _copy(self, value: str) -> None:
        copy_to_clipboard(self, value)
        self.toast_ok("ID copiado al portapapeles.")

    def _save(self, role: Role) -> None:
        if not self.require("MANAGE_ROLES", "editar roles"):
            return
        if role.managed:
            self.toast_warn(
                "Discord no permite editar un rol gestionado por una app desde el panel. "
                "Edítalo en Discord o crea un rol normal.")
            return
        name = self.name_var.get().strip()
        if not name:
            self.toast_warn("El nombre del rol no puede quedar vacío.")
            return
        raw_color = self.hex_var.get().strip()
        color_value = 0
        if raw_color:
            parsed = color_to_int(raw_color)
            if parsed is None:
                self.toast_warn("Color no válido. Usa el formato #RRGGBB.")
                return
            color_value = parsed
        fields: dict[str, Any] = {
            "name": name,
            "color": color_value,
            "hoist": bool(self.hoist_var.get()),
            "mentionable": bool(self.mention_var.get()),
            "permissions": str(self.grid.get_bits() if self.grid else role.permissions),
        }
        if getattr(self, "icon_dirty", False):
            if int(getattr(self.app.guild, "premium_tier", 0) or 0) < 2:
                self.toast_warn("El icono de rol requiere Nivel 2 de mejoras.")
                return
            emoji = self.icon_emoji_var.get().strip()
            if self.icon_data:
                fields["icon"] = self.icon_data
                fields["unicode_emoji"] = None
            elif emoji:
                fields["icon"] = None
                fields["unicode_emoji"] = emoji
            else:
                fields["icon"] = None
                fields["unicode_emoji"] = None
        if role.is_everyone:
            fields.pop("name", None)
            fields.pop("hoist", None)
        client = self.app.client
        guild_id = self.app.guild.id

        def done(_result: Any) -> None:
            self.toast_ok(f"Rol «{name}» actualizado.")
            self.app.refresh_guild()

        self.run(lambda: client.update_role(guild_id, role.id, fields), done)

    def _delete(self, role: Role) -> None:
        if not self.require("MANAGE_ROLES", "eliminar roles"):
            return
        if role.is_everyone or role.managed:
            self.toast_warn("No se puede eliminar un rol base o gestionado por una app.")
            return
        dialog = ConfirmDialog(self, "Eliminar rol",
                               f"Se eliminará el rol «{role.name}» y se quitará de todos los "
                               "miembros que lo tengan.",
                               confirm_text="Eliminar rol", danger=True,
                               theme=self.app.theme, require_text=role.name)
        if not dialog.show():
            return
        client = self.app.client
        guild_id = self.app.guild.id

        def done(_result: Any) -> None:
            self.selected_id = None
            self.toast_ok(f"Rol «{role.name}» eliminado.")
            self.app.refresh_guild()

        self.run(lambda: client.delete_role(guild_id, role.id), done)

    def _move(self, role: Role, delta: int) -> None:
        if role.is_everyone or role.managed:
            return
        order = [item for item in self._roles if not item.is_everyone]
        index = next((i for i, item in enumerate(order) if item.id == role.id), None)
        if index is None:
            return
        target = index + delta
        if target < 0 or target >= len(order):
            return
        self._reorder(role, len(order) - target)

    def _reorder(self, role: Role, position: int) -> None:
        if not self.require("MANAGE_ROLES", "reordenar roles"):
            return
        if role.is_everyone or role.managed:
            self.toast_warn("Los roles base o gestionados por apps no se reordenan en el panel.")
            return
        client = self.app.client
        guild_id = self.app.guild.id

        def done(_result: Any) -> None:
            order = [item for item in self._roles if not item.is_everyone]
            index = next((i for i, item in enumerate(order) if item.id == role.id), None)
            if index is not None:
                order.pop(index)
                target = max(0, min(len(order), len(order) - position))
                order.insert(target, role)
                role.position = max(1, position)
                self._roles = ([item for item in self._roles if item.is_everyone]
                               + order)
                self._render_list()
            self.toast_ok(f"Rol «{role.name}» reordenado.")

        def failed(error: BaseException) -> None:
            if getattr(error, "status", None) == 50013:
                self.toast_warn(
                    "Discord no permitió reordenar: el rol del bot debe estar por encima "
                    "de los roles que mueves y tener «Gestionar roles».")
            else:
                self.error(error)

        self.run(lambda: client.reorder_roles(
            guild_id, [{"id": role.id, "position": max(1, position)}]), done, failed)

    # ------------------------------------------------------------------ #
    def create_role(self) -> None:
        if not self.require("MANAGE_ROLES", "crear roles"):
            return
        RoleCreateModal(self, self.app).show()


class RoleCreateModal(Modal):
    def __init__(self, parent: tk.Misc, app: Any):
        super().__init__(parent, "Nuevo rol", width=460, theme=app.theme,
                         subtitle="Podrás ajustar permisos y color justo después.")
        self.app = app
        field = Field(self.body, "Nombre del rol", bg=C.CARD)
        field.pack(fill="x")
        self.name_var = tk.StringVar(value="Nuevo rol")
        entry = ttk.Entry(field.slot, textvariable=self.name_var)
        field.add(entry)
        entry.focus_set()
        entry.select_range(0, "end")
        self.add_button("Cancelar", self.close)
        self.add_button("Crear rol", self._submit, style="Accent.TButton")

    def _submit(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            self.show_error("Escribe un nombre.")
            return
        client = self.app.client
        guild_id = self.app.guild.id
        self.set_busy(True)

        def done(role: Role) -> None:
            self.app.toasts.show(f"Rol «{role.name}» creado.", "success")
            self.close()
            self.app.refresh_guild()

        def failed(error: BaseException) -> None:
            self.set_busy(False)
            self.show_error(str(error))

        self.app.run_task(
            lambda: client.create_role(guild_id, {"name": name, "permissions": "0"}),
            done, failed)
