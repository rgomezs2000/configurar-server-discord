"""Gestión de canales: crear, editar, ordenar, borrar y permisos por canal."""
from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import Any

from ...constants import (CREATABLE_CHANNEL_TYPES, CHANNEL_GLYPHS,
                          creatable_channel_types)
from ...font_styles import STYLE_NAMES, apply_font_style
from ...models import Channel, Invite, PermissionOverwrite, Webhook, bits
from ...util import normalize_channel_name, safe_int
from ..emoji_picker import EmojiPicker
from ..permissions import OverwriteEditor
from ..theme import C
from ..widgets import (Card, Checkbox, ConfirmDialog, EmptyState, Field, Modal,
                       PageHeader, ScrollFrame, SearchEntry, TabBar, Table,
                       TableColumn, Tooltip, copy_to_clipboard, labeled_combo,
                       labeled_text)
from .base import Page
from .bulk_channels import BulkChannelsTab


def _attach_name_normalizer(variable: tk.StringVar, entry: ttk.Entry) -> None:
    """Convierte en vivo el nombre a minúsculas, espacios a guiones y quita el resto."""
    state = {"guard": False}

    def on_write(*_args: Any) -> None:
        if state["guard"]:
            return
        current = variable.get()
        normalized = normalize_channel_name(current, strip=False)
        if normalized != current:
            state["guard"] = True
            variable.set(normalized)
            try:
                entry.icursor("end")
            except tk.TclError:
                pass
            state["guard"] = False

    variable.trace_add("write", on_write)


SLUG_CHANNEL_TYPES = {0, 5, 15}  # texto, anuncios, foro


def _channel_name(channel: Channel, raw: str) -> str:
    """Todos los canales conservan el texto tal cual, incluidos espacios extremos."""
    return raw


class ChannelsPage(Page):
    key = "channels"
    label = "Canales"
    glyph = "#"

    def build(self) -> None:
        app = self.app
        self.header = PageHeader(self, app, "Canales",
                                 "Crea, ordena y ajusta los canales del servidor.")
        self.header.pack(fill="x", padx=28, pady=(22, 0))
        self.header.button("Actualizar", self.refresh)
        self._manage = app.can("MANAGE_CHANNELS")
        self.tabs = TabBar(self, [("channels", "Canales"),
                                  ("bulk", "Gestionar canales masivo")],
                           on_change=self._switch, theme=app.theme)
        self.tabs.pack(fill="x", padx=28, pady=(8, 0))
        self.container = tk.Frame(self, bg=C.CONTENT)
        self.container.pack(fill="both", expand=True)
        self.channels_tab = tk.Frame(self.container, bg=C.CONTENT)
        self.bulk = BulkChannelsTab(self.container, app, self)
        self._active_tab = ""
        self._build_channels_tab()
        self.tabs.select("channels")

    def _build_channels_tab(self) -> None:
        app = self.app
        toolbar = tk.Frame(self.channels_tab, bg=C.CONTENT)
        toolbar.pack(fill="x", padx=28, pady=(10, 0))
        self.btn_category = ttk.Button(toolbar, text="Nueva categoría",
                                       command=self.create_category)
        self.btn_category.pack(side="left")
        self.btn_channel = ttk.Button(toolbar, text="Nuevo canal",
                                      style="Accent.TButton",
                                      command=self.create_channel)
        self.btn_channel.pack(side="left", padx=(6, 0))
        if not self._manage:
            for button in (self.btn_category, self.btn_channel):
                button.configure(state="disabled")

        body = tk.Frame(self.channels_tab, bg=C.CONTENT)
        body.pack(fill="both", expand=True, padx=28, pady=(14, 20))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=0, minsize=340)
        body.grid_columnconfigure(1, weight=1)

        left = tk.Frame(body, bg=C.CARD, highlightbackground=C.BORDER_SOFT,
                        highlightthickness=1)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)
        top = tk.Frame(left, bg=C.CARD)
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        self.count_label = tk.Label(top, text="", bg=C.CARD, fg=C.DIM,
                                    font=app.theme.font(9, "bold"), anchor="w")
        self.count_label.pack(side="left")
        tk.Label(top, text="↕ usa las flechas para ordenar", bg=C.CARD, fg=C.FAINT,
                 font=app.theme.font(8), anchor="e").pack(side="right")
        self.list_scroll = ScrollFrame(left, bg=C.CARD)
        self.list_scroll.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 8))

        self.right = tk.Frame(body, bg=C.CONTENT)
        self.right.grid(row=0, column=1, sticky="nsew")

        self.selected_id: str | None = None
        self._channels: list[Channel] = []

    def _switch(self, key: str) -> None:
        if not hasattr(self, "channels_tab"):
            return
        self._active_tab = key
        for frame in (self.channels_tab, self.bulk):
            frame.pack_forget()
        if key == "channels":
            self.channels_tab.pack(fill="both", expand=True)
        else:
            self.bulk.pack(fill="both", expand=True)
            self.bulk.on_show()

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        self._channels = sorted(self.app.channels, key=lambda c: (c.position, int(c.id)))
        self.category_map = {c.name: c.id for c in self._channels if c.is_category}
        ids = {c.id for c in self._channels}
        if self.selected_id not in ids:
            first = next((c for c in self._channels if not c.is_category), None)
            self.selected_id = first.id if first else None
        channels = [c for c in self._channels if not c.is_category]
        self.count_label.configure(text=f"{len(channels)} canales · {len(self._channels)} elementos")
        self._render_list()
        self._render_detail()

    def on_guild_refreshed(self) -> None:
        if not self.is_dirty():
            self.refresh()
            return
        self._channels = sorted(self.app.channels, key=lambda c: (c.position, int(c.id)))
        self.category_map = {c.name: c.id for c in self._channels if c.is_category}
        channels = [c for c in self._channels if not c.is_category]
        self.count_label.configure(text=f"{len(channels)} canales · "
                                        f"{len(self._channels)} elementos")
        self._render_list()

    def is_dirty(self) -> bool:
        if not hasattr(self, "name_var"):
            return False
        channel = next((c for c in self._channels if c.id == self.selected_id), None)
        if channel is None:
            return False
        try:
            return self._dirty_fields(channel)
        except tk.TclError:
            return False

    def _dirty_fields(self, channel: Channel) -> bool:
        if self.name_var.get() != (channel.name or ""):
            return True
        if not channel.is_category:
            parent = next((c.name for c in self._channels
                           if c.is_category and c.id == channel.parent_id), "Sin categoría")
            if self.category_var.get() != (parent or "Sin categoría"):
                return True
        if channel.is_text:
            topic = getattr(self, "topic_text", None)
            if topic is not None and topic.winfo_exists() and (
                    topic.get("1.0", "end").strip() != (channel.topic or "")):
                return True
            nsfw = getattr(self, "nsfw_var", None)
            if nsfw is not None and bool(nsfw.get()) != channel.nsfw:
                return True
            slow = getattr(self, "slow_var", None)
            if slow is not None and safe_int(slow.get()) != channel.rate_limit_per_user:
                return True
            archive = getattr(self, "archive_var", None)
            if archive is not None:
                expected = {"1 día": 1440, "3 días": 4320, "7 días": 10080}.get(
                    archive.get(), 1440)
                if expected != channel.default_auto_archive_duration:
                    return True
        if channel.is_voice:
            limit = getattr(self, "limit_var", None)
            if limit is not None and safe_int(limit.get()) != channel.user_limit:
                return True
            bitrate = getattr(self, "bitrate_var", None)
            if bitrate is not None and safe_int(bitrate.get()) * 1000 != channel.bitrate:
                return True
        return False

    # ------------------------------------------------------------------ #
    def _flat_list(self) -> list[tuple[Channel, int]]:
        items: list[tuple[Channel, int]] = []
        categories = [c for c in self._channels if c.is_category]
        used: set[str] = set()
        for category in categories:
            items.append((category, 0))
            for child in self._channels:
                if child.parent_id == category.id and not child.is_category:
                    items.append((child, 1))
                    used.add(child.id)
        for channel in self._channels:
            if channel.is_category or channel.id in used:
                continue
            items.append((channel, 1 if channel.parent_id else 0))
        return items

    def _render_list(self) -> None:
        self.list_scroll.clear()
        inner = self.list_scroll.inner
        for channel, indent in self._flat_list():
            selected = channel.id == self.selected_id
            bg = C.ACCENT_SOFT if selected else C.CARD
            row = tk.Frame(inner, bg=bg, cursor="hand2")
            row.pack(fill="x", padx=4, pady=1)
            line = tk.Frame(row, bg=bg)
            line.pack(fill="x", padx=(10 + indent * 20, 8), pady=5)
            glyph = tk.Label(line, text=CHANNEL_GLYPHS.get(channel.type, "#"), bg=bg,
                             fg=C.ACCENT if selected else C.MUTED,
                             font=(self.app.theme.mono_family, 10, "bold"), width=2)
            glyph.pack(side="left")
            name = tk.Label(line, text=channel.display_name, bg=bg,
                            fg=C.TEXT if selected else C.DIM,
                            font=self.app.theme.font(9, "bold" if channel.is_category else "normal"),
                            anchor="w", justify="left")
            name.pack(side="left", fill="x", expand=True)
            badges = []
            if channel.is_category:
                count = len([c for c in self._channels if c.parent_id == channel.id])
                badges.append(str(count))
            if channel.nsfw:
                badges.append("NSFW")
            if channel.rate_limit_per_user:
                badges.append(f"{channel.rate_limit_per_user}s")
            if channel.is_voice and channel.user_limit:
                badges.append(f"{channel.user_limit}★")
            if badges:
                tk.Label(line, text="  ".join(badges), bg=bg, fg=C.FAINT,
                         font=self.app.theme.font(8)).pack(side="right")
            widgets = [row, line, glyph, name]
            for widget in widgets:
                widget.bind("<Button-1>", lambda _e, c=channel: self._select(c))
            if not selected:
                for widget in widgets:
                    widget.bind("<Enter>", lambda _e, r=row, ln=line: self._hover(r, ln, True))
                    widget.bind("<Leave>", lambda _e, r=row, ln=line: self._hover(r, ln, False))
        self.list_scroll.refresh_scroll()

    @staticmethod
    def _hover(row: tk.Frame, line: tk.Frame, entering: bool) -> None:
        color = C.CARD_ALT if entering else C.CARD
        for widget in (row, line, *line.winfo_children()):
            try:
                widget.configure(bg=color)
            except tk.TclError:
                pass

    def _select(self, channel: Channel) -> None:
        self.selected_id = channel.id
        self._render_list()
        self._render_detail()

    # ------------------------------------------------------------------ #
    def _render_detail(self) -> None:
        for child in self.right.winfo_children():
            child.destroy()
        channel = next((c for c in self._channels if c.id == self.selected_id), None)
        if channel is None:
            EmptyState(self.right, "Ningún canal seleccionado",
                       "Elige un canal de la lista para editarlo.",
                       bg=C.CONTENT).pack(expand=True)
            return
        app = self.app
        card = Card(self.right, padding=20)
        card.pack(fill="both", expand=True)
        body = card.body

        head = tk.Frame(body, bg=C.CARD)
        head.pack(fill="x", pady=(0, 4))
        tk.Label(head, text=CHANNEL_GLYPHS.get(channel.type, "#"), bg=C.CARD,
                 fg=C.ACCENT, font=(app.theme.mono_family, 16, "bold")).pack(side="left")
        tk.Label(head, text=channel.display_name, bg=C.CARD, fg=C.TEXT,
                 font=app.theme.font(15, "bold")).pack(side="left", padx=(8, 8))
        tk.Label(head, text=channel.kind_label, bg=C.CARD_ALT, fg=C.DIM,
                 font=app.theme.font(8, "bold"), padx=7, pady=2).pack(side="left")
        if channel.nsfw:
            tk.Label(head, text="NSFW", bg=C.RED_SOFT, fg="#ffb3b5",
                     font=app.theme.font(8, "bold"), padx=7, pady=2).pack(side="left", padx=(6, 0))
        copy = tk.Label(head, text="copiar ID", bg=C.CARD, fg=C.LINK,
                        font=app.theme.font(8), cursor="hand2")
        copy.pack(side="right")
        copy.bind("<Button-1>", lambda _e: self._copy(channel.id))
        tk.Label(body, text=f"ID {channel.id}", bg=C.CARD, fg=C.FAINT,
                 font=(app.theme.mono_family, 8), anchor="w").pack(fill="x", pady=(0, 14))

        if not self._manage:
            tk.Label(body, text="Solo lectura: falta el permiso «Gestionar canales».",
                     bg=C.YELLOW_SOFT, fg="#ffd98a", font=app.theme.font(8),
                     anchor="w", padx=10, pady=6).pack(fill="x", pady=(0, 12))

        self._detail_frames: dict[str, tk.Frame] = {}
        self._detail_ready = False
        self.detail_tabs = TabBar(
            body,
            [("general", "Vista general"), ("perms", "Permisos"),
             ("invites", "Invitaciones"), ("integrations", "Integraciones")],
            on_change=lambda key: self._switch_detail_tab(key, channel),
            theme=app.theme)
        self.detail_tabs.pack(fill="x", pady=(0, 8))
        self._detail_host = tk.Frame(body, bg=C.CARD)
        self._detail_host.pack(fill="both", expand=True)
        self._detail_frames: dict[str, tk.Frame] = {}
        for key in ("general", "perms", "invites", "integrations"):
            frame = tk.Frame(self._detail_host, bg=C.CARD)
            self._detail_frames[key] = frame
        self._detail_ready = True
        body = self._detail_frames["general"]

        name_row = tk.Frame(body, bg=C.CARD)
        name_row.pack(fill="x", pady=(0, 12))
        name_field = Field(name_row, "Nombre del canal")
        name_field.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.name_var = tk.StringVar(value=channel.name or "")
        name_entry = ttk.Entry(name_field.slot, textvariable=self.name_var)
        name_field.add(name_entry)

        font_field = Field(body, "Tipografía del nombre",
                           "Convierte el texto a caracteres Unicode tipo Discord.")
        font_field.pack(fill="x", pady=(0, 12))
        self.detail_font_var = tk.StringVar(value="Normal")
        detail_font = ttk.Combobox(font_field.slot, values=STYLE_NAMES,
                                   state="readonly", textvariable=self.detail_font_var)
        font_field.add(detail_font)
        detail_font.bind("<<ComboboxSelected>>", lambda _e: self._apply_detail_font())
        self._detail_font_source = channel.name or ""
        self._detail_font_internal = False
        self.name_var.trace_add("write", self._detail_name_changed)

        categories = ["Sin categoría"] + [c.name or "" for c in self._channels if c.is_category]
        self.category_map = {c.name: c.id for c in self._channels if c.is_category}
        current_category = next((c.name for c in self._channels
                                 if c.is_category and c.id == channel.parent_id), "Sin categoría")
        cat_field = Field(name_row, "Categoría")
        cat_field.pack(side="left", fill="x", expand=True)
        self.category_var = tk.StringVar(value=current_category or "Sin categoría")
        cat_combo = ttk.Combobox(cat_field.slot, values=categories, state="readonly",
                                 textvariable=self.category_var)
        cat_field.add(cat_combo)
        if channel.is_category:
            cat_combo.configure(state="disabled")
            self.category_var.set("Sin categoría")

        if channel.is_text:
            topic_field, _topic = labeled_text(body, app, "Tema del canal",
                                               "Visible en la cabecera del canal.", height=3)
            topic_field.pack(fill="x", pady=(0, 6))
            self.topic_text = _topic
            self.topic_text.insert("1.0", channel.topic or "")
            topic_actions = tk.Frame(body, bg=C.CARD)
            topic_actions.pack(fill="x", pady=(0, 10))
            self._topic_emoji_button = ttk.Button(
                topic_actions, text="Insertar emoji", style="Small.TButton",
                command=self._open_topic_emojis)
            self._topic_emoji_button.pack(side="right")
            tk.Label(topic_actions, text="El tema admite emojis estándar y del servidor.",
                     bg=C.CARD, fg=C.FAINT, font=app.theme.font(8),
                     anchor="w").pack(side="left")
            options = tk.Frame(body, bg=C.CARD)
            options.pack(fill="x", pady=(0, 12))
            self.nsfw_var = tk.BooleanVar(value=channel.nsfw)
            Checkbox(options, "Canal para adultos (NSFW)", variable=self.nsfw_var,
                     bg=C.CARD, font=app.theme.font(9)).pack(side="left")
            slow_box = tk.Frame(options, bg=C.CARD)
            slow_box.pack(side="right")
            tk.Label(slow_box, text="Modo lento (s):", bg=C.CARD, fg=C.MUTED,
                     font=app.theme.font(8)).pack(side="left", padx=(0, 6))
            self.slow_var = tk.StringVar(value=str(channel.rate_limit_per_user))
            ttk.Spinbox(slow_box, from_=0, to=21600, increment=5, width=6,
                        textvariable=self.slow_var).pack(side="left")
            archive_box = tk.Frame(body, bg=C.CARD)
            archive_box.pack(fill="x", pady=(0, 12))
            tk.Label(archive_box, text="Archivar hilos automáticamente:",
                     bg=C.CARD, fg=C.MUTED,
                     font=app.theme.font(8)).pack(side="left", padx=(0, 6))
            self.archive_var = tk.StringVar(
                value={1440: "1 día", 4320: "3 días", 10080: "7 días"}.get(
                    channel.default_auto_archive_duration, "1 día"))
            ttk.Combobox(archive_box, values=["1 día", "3 días", "7 días"],
                         state="readonly", width=10,
                         textvariable=self.archive_var).pack(side="left")
        elif channel.is_voice:
            options = tk.Frame(body, bg=C.CARD)
            options.pack(fill="x", pady=(0, 10))
            tk.Label(options, text="Límite de usuarios (0 = sin límite):", bg=C.CARD,
                     fg=C.MUTED, font=app.theme.font(8)).pack(side="left", padx=(0, 6))
            self.limit_var = tk.StringVar(value=str(channel.user_limit))
            ttk.Spinbox(options, from_=0, to=99, width=6,
                        textvariable=self.limit_var).pack(side="left")

            max_kbps = max(8, app.guild.max_voice_bitrate // 1000)
            quality = tk.Frame(body, bg=C.CARD)
            quality.pack(fill="x", pady=(0, 12))
            tk.Label(quality, text="Calidad de audio (kbps):", bg=C.CARD,
                     fg=C.MUTED, font=app.theme.font(8)).pack(side="left", padx=(0, 6))
            self.bitrate_var = tk.StringVar(value=str(max(8, channel.bitrate // 1000)))
            ttk.Spinbox(quality, from_=8, to=max_kbps, increment=8, width=6,
                        textvariable=self.bitrate_var).pack(side="left")
            tk.Label(quality,
                     text=f"Máximo {max_kbps} kbps · Nivel {app.guild.boost_level}",
                     bg=C.CARD, fg=C.FAINT, font=app.theme.font(8)).pack(
                side="left", padx=(8, 0))

        footer = tk.Frame(body, bg=C.CARD)
        footer.pack(fill="x", side="bottom", pady=(8, 0))
        for text, delta in (("↑ Subir", -1), ("↓ Bajar", 1)):
            ttk.Button(footer, text=text, style="Small.TButton",
                       command=lambda d=delta: self._move(channel, d)).pack(
                side="left", padx=(0, 6))
        delete_button = ttk.Button(footer, text="Eliminar canal", style="SmallDanger.TButton",
                                   command=lambda: self._delete(channel))
        delete_button.pack(side="left")
        save_button = ttk.Button(footer, text="Guardar cambios", style="Accent.TButton",
                                 command=lambda: self._save(channel))
        save_button.pack(side="right")
        if not self._manage:
            delete_button.configure(state="disabled")
            save_button.configure(state="disabled")
            name_entry.configure(state="readonly")

        self._build_permissions_tab(channel)
        self._build_invites_tab(channel)
        self._build_integrations_tab(channel)
        self.detail_tabs.select("general")

    def _switch_detail_tab(self, key: str, channel: Channel) -> None:
        if not getattr(self, "_detail_ready", False):
            return
        for frame in self._detail_frames.values():
            frame.pack_forget()
        frame = self._detail_frames.get(key)
        if frame is not None:
            frame.pack(fill="both", expand=True)
        if key == "invites":
            self._load_invites(channel)
        elif key == "integrations":
            self._load_integrations(channel)

    def _build_permissions_tab(self, channel: Channel) -> None:
        app = self.app
        frame = self._detail_frames["perms"]
        self._perm_channel = channel
        self._perm_values: dict[str, tuple[int, int]] = {
            ow.id: (ow.allow, ow.deny) for ow in channel.permission_overwrites
        }
        self._perm_types: dict[str, int] = {
            ow.id: ow.type for ow in channel.permission_overwrites
        }
        self._perm_members: list[Any] = []
        self._perm_current = ""
        self._perm_editor: OverwriteEditor | None = None
        top = tk.Frame(frame, bg=C.CARD)
        top.pack(fill="x", pady=(0, 6))
        self._perm_status = tk.Label(
            top, text=f"Permisos ({len(channel.permission_overwrites)})",
            bg=C.CARD, fg=C.TEXT, font=app.theme.font(9, "bold"), anchor="w")
        self._perm_status.pack(side="left")
        self._perm_private = tk.Label(
            top, text="Privado" if self._is_private(channel) else "Público",
            bg=C.CARD_ALT, fg=C.MUTED, font=app.theme.font(8), padx=6)
        self._perm_private.pack(side="right")
        picker = tk.Frame(frame, bg=C.CARD)
        picker.pack(fill="x", pady=(0, 6))
        self._perm_target_var = tk.StringVar()
        self._perm_combo = ttk.Combobox(picker, textvariable=self._perm_target_var,
                                        state="readonly")
        self._perm_combo.pack(side="left", fill="x", expand=True)
        ttk.Button(picker, text="Agregar", style="Small.TButton",
                   command=lambda: self._add_perm_target(channel)).pack(
            side="left", padx=(6, 0))
        ttk.Button(picker, text="Quitar", style="SmallDanger.TButton",
                   command=lambda: self._remove_perm_target(channel)).pack(
            side="left", padx=(6, 0))
        split = tk.Frame(frame, bg=C.CARD)
        split.pack(fill="both", expand=True)
        split.grid_columnconfigure(1, weight=1)
        split.grid_rowconfigure(0, weight=1)
        left = tk.Frame(split, bg=C.CARD)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._perm_table = Table(
            left, [TableColumn("target", "Rol / usuario", 180),
                   TableColumn("kind", "Tipo", 70),
                   TableColumn("allow", "Permitir", 80),
                   TableColumn("deny", "Denegar", 80)],
            height=7, theme=app.theme, multi=True,
            empty_text="Sin permisos propios.", hscroll=False)
        self._perm_table.pack(fill="both", expand=True)
        self._perm_table.tree.bind("<<TreeviewSelect>>",
                                   lambda _e: self._select_perm_target())
        self._perm_anchor: str | None = None
        self._perm_drag_mode: str | None = None
        self._perm_drag_start: str | None = None
        self._perm_drag_base: set[str] = set()
        self._perm_drag_toggled: set[str] = set()
        self._perm_drag_deselect = False
        self._perm_drag_moved = False
        self._perm_table.tree.unbind("<Button-3>")
        self._perm_table.tree.bind("<Button-3>", self._perm_context)
        self._perm_table.tree.bind("<ButtonPress-1>", self._perm_button_press)
        self._perm_table.tree.bind("<B1-Motion>", self._perm_drag_motion, add="+")
        self._perm_table.tree.bind("<ButtonRelease-1>", self._perm_drag_release, add="+")
        self._perm_table.tree.bind("<Shift-Up>", lambda _e: self._perm_extend(-1))
        self._perm_table.tree.bind("<Shift-Down>", lambda _e: self._perm_extend(1))
        self._perm_table.tree.bind("<Shift-Prior>", lambda _e: self._perm_extend(-7))
        self._perm_table.tree.bind("<Shift-Next>", lambda _e: self._perm_extend(7))
        self._perm_menu = tk.Menu(self, tearoff=0, bg=C.CARD, fg=C.TEXT,
                                  activebackground=C.ACCENT_SOFT)
        self._perm_menu.add_command(label="Quitar seleccionados",
                                    command=lambda: self._remove_perm_target(channel))
        right = tk.Frame(split, bg=C.CARD)
        right.grid(row=0, column=1, sticky="nsew")
        self._perm_editor_host = tk.Frame(right, bg=C.CARD)
        self._perm_editor_host.pack(fill="both", expand=True)
        ttk.Button(right, text="Guardar permisos del canal",
                   style="Accent.TButton",
                   command=lambda: self._save_permissions(channel)).pack(
            anchor="e", pady=(6, 0))
        if not self._manage or channel.is_category:
            for child in (self._perm_combo,):
                child.configure(state="disabled")
        self._render_perm_targets()
        self._load_perm_members(channel)

    def _is_private(self, channel: Channel) -> bool:
        everyone = self.app.guild.everyone_role
        if everyone is None:
            return False
        return any(ow.id == everyone.id and ow.deny & (1 << 10)
                   for ow in channel.permission_overwrites)

    def _target_label(self, target_id: str) -> str:
        if target_id in {role.id for role in self.app.guild.roles}:
            role = next(role for role in self.app.guild.roles if role.id == target_id)
            return f"@{role.name}"
        member = next((m for m in self._perm_members if m.user.id == target_id), None)
        return member.display_name if member else target_id

    def _perm_targets(self) -> list[tuple[str, str, int]]:
        result = []
        if self.app.guild.everyone_role:
            result.append((self.app.guild.everyone_role.id, "Rol · @everyone", 0))
        result += [(role.id, f"Rol · @{role.name}", 0)
                   for role in self.app.guild.sorted_roles() if not role.is_everyone]
        result += [(member.user.id, f"Usuario · {member.display_name}", 1)
                   for member in self._perm_members]
        return result

    def _render_perm_targets(self) -> None:
        roles = []
        users = []
        for target_id, (allow, deny) in self._perm_values.items():
            row = {"_id": target_id, "target": self._target_label(target_id),
                   "kind": "Usuario" if self._perm_types.get(target_id) else "Rol",
                   "allow": str(allow.bit_count()), "deny": str(deny.bit_count())}
            (users if self._perm_types.get(target_id) else roles).append(row)
        rows = []
        if roles:
            rows.append({"_id": "__roles", "target": "ROLES", "kind": "",
                         "allow": "", "deny": ""})
            rows.extend(roles)
        if users:
            rows.append({"_id": "__users", "target": "USUARIOS", "kind": "",
                         "allow": "", "deny": ""})
            rows.extend(users)
        self._perm_table.set_rows(rows)
        labels = [label for _id, label, _kind in self._perm_targets()]
        current = self._perm_target_var.get()
        self._perm_combo.configure(values=labels)
        if current in labels:
            self._perm_target_var.set(current)
        elif labels:
            self._perm_target_var.set(labels[0])

    def _load_perm_members(self, channel: Channel) -> None:
        def done(members: list[Any]) -> None:
            try:
                self._perm_members = members
                self._render_perm_targets()
            except tk.TclError:
                pass

        def failed(_error: BaseException) -> None:
            pass

        self.run(lambda: self.app.client.list_members(self.app.guild.id, limit=100), done,
                 failed)

    def _add_perm_target(self, channel: Channel) -> None:
        wanted = self._perm_target_var.get()
        target = next((entry for entry in self._perm_targets()
                       if entry[1] == wanted), None)
        if target is None:
            self.toast_warn("Elige un rol o usuario.")
            return
        target_id, _label, kind = target
        self._perm_values.setdefault(target_id, (0, 0))
        self._perm_types[target_id] = kind
        self._perm_current = target_id
        self._open_perm_editor(target_id)
        self._render_perm_targets()

    def _selected_perm_id(self) -> str:
        rows = self._perm_table.selected_rows()
        for row in rows:
            target_id = str(row.get("_id") or "")
            if target_id:
                return target_id
        return ""

    def _selected_perm_ids(self) -> list[str]:
        return [str(row.get("_id")) for row in self._perm_table.selected_rows()
                if row.get("_id") and not str(row.get("_id")).startswith("__")]

    def _remove_perm_target(self, channel: Channel) -> None:
        target_ids = self._selected_perm_ids()
        if not target_ids:
            self.toast_warn("Selecciona al menos un rol o usuario.")
            return
        for target_id in target_ids:
            self._perm_values.pop(target_id, None)
            self._perm_types.pop(target_id, None)
        self._render_perm_targets()
        if self._perm_editor is not None:
            self._perm_editor.destroy()
            self._perm_editor = None
        self._perm_current = ""

    def _perm_context(self, event: tk.Event) -> None:
        row_id = self._perm_table.tree.identify_row(event.y)
        if row_id:
            if row_id not in self._perm_table.tree.selection():
                self._perm_table.tree.selection_set(row_id)
            self._perm_table.tree.focus(row_id)
        try:
            self._perm_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._perm_menu.grab_release()
            except tk.TclError:
                pass

    def _perm_button_press(self, event: tk.Event) -> str | None:
        row_id = self._perm_table.tree.identify_row(event.y)
        if not row_id or not self._perm_table.tree.set(row_id, "kind"):
            self._perm_drag_mode = None
            return None
        shift = bool(event.state & 0x0001)
        ctrl = bool(event.state & 0x0004)
        if ctrl:
            self._perm_drag_mode = "ctrl"
            self._perm_drag_start = row_id
            self._perm_drag_toggled = set()
            self._perm_drag_moved = False
            self._perm_toggle(row_id)
            return "break"
        if shift:
            self._perm_drag_mode = "shift"
            self._perm_drag_start = row_id
            self._perm_drag_base = set(self._perm_table.tree.selection())
            self._perm_drag_deselect = row_id in self._perm_drag_base
            self._perm_drag_moved = False
            self._perm_apply_shift(row_id)
            return "break"
        self._perm_drag_mode = None
        self._perm_anchor = row_id
        return None

    def _perm_drag_motion(self, event: tk.Event) -> str | None:
        if self._perm_drag_mode is None:
            return None
        row_id = self._perm_table.tree.identify_row(event.y)
        if not row_id or not self._perm_table.tree.set(row_id, "kind"):
            return "break"
        if row_id != self._perm_drag_start:
            self._perm_drag_moved = True
        if self._perm_drag_mode == "ctrl":
            if row_id not in self._perm_drag_toggled:
                self._perm_toggle(row_id)
        else:
            self._perm_apply_shift(row_id)
        self._perm_table.tree.focus(row_id)
        self._perm_table.tree.see(row_id)
        return "break"

    def _perm_drag_release(self, _event: tk.Event) -> str | None:
        mode = self._perm_drag_mode
        if mode is None:
            return None
        if mode == "shift" and not self._perm_drag_moved and not self._perm_drag_deselect:
            start = self._perm_drag_start
            if start:
                rows = list(self._perm_table.tree.get_children())
                anchor = self._perm_anchor if self._perm_anchor in rows else start
                low, high = sorted((rows.index(start), rows.index(anchor)))
                selected = self._perm_drag_base | set(rows[low:high + 1])
                self._perm_set_selection(selected)
        self._perm_drag_mode = None
        self._perm_drag_start = None
        return "break"

    def _perm_apply_shift(self, current: str) -> None:
        start = self._perm_drag_start
        if not start:
            return
        rows = list(self._perm_table.tree.get_children())
        if start not in rows or current not in rows:
            return
        low, high = sorted((rows.index(start), rows.index(current)))
        block = set(rows[low:high + 1])
        selected = (self._perm_drag_base - block
                    if self._perm_drag_deselect else self._perm_drag_base | block)
        self._perm_set_selection(selected)
        self._perm_table.tree.focus(current)
        self._perm_table.tree.see(current)

    def _perm_toggle(self, row_id: str) -> None:
        selected = set(self._perm_table.tree.selection())
        selected.discard(row_id) if row_id in selected else selected.add(row_id)
        self._perm_drag_toggled.add(row_id)
        self._perm_set_selection(selected)
        self._perm_table.tree.focus(row_id)
        self._perm_table.tree.see(row_id)

    def _perm_set_selection(self, selected: set[str]) -> None:
        rows = list(self._perm_table.tree.get_children())
        ordered = [row for row in rows if row in selected]
        if ordered:
            self._perm_table.tree.selection_set(*ordered)
        else:
            current = self._perm_table.tree.selection()
            if current:
                self._perm_table.tree.selection_remove(*current)

    def _perm_extend(self, delta: int) -> str:
        rows = list(self._perm_table.tree.get_children())
        if not rows:
            return "break"
        focus = self._perm_table.tree.focus()
        if focus not in rows:
            focus = self._perm_anchor if self._perm_anchor in rows else rows[0]
        anchor = self._perm_anchor if self._perm_anchor in rows else focus
        target = max(0, min(rows.index(focus) + delta, len(rows) - 1))
        low, high = sorted((rows.index(anchor), target))
        self._perm_set_selection(set(rows[low:high + 1]))
        self._perm_table.tree.focus(rows[target])
        self._perm_table.tree.see(rows[target])
        return "break"

    def _select_perm_target(self) -> None:
        ids = self._selected_perm_ids()
        if len(ids) == 1:
            self._open_perm_editor(ids[0])
        elif self._perm_editor is not None:
            self._perm_editor.destroy()
            self._perm_editor = None
            self._perm_current = ""

    def _open_perm_editor(self, target_id: str) -> None:
        if self._perm_current == target_id and self._perm_editor is not None:
            return
        if self._perm_editor is not None:
            self._perm_editor.destroy()
        self._perm_current = target_id
        allow, deny = self._perm_values.get(target_id, (0, 0))
        self._perm_editor = OverwriteEditor(
            self._perm_editor_host, self.app, allow, deny, height=7)
        self._perm_editor.pack(fill="both", expand=True)

    def _save_permissions(self, channel: Channel) -> None:
        if not self.require("MANAGE_CHANNELS", "editar permisos de canal"):
            return
        if self._perm_editor is not None and self._perm_current:
            self._perm_values[self._perm_current] = self._perm_editor.get_allow_deny()
        payload = [
            {"id": target_id, "type": self._perm_types.get(target_id, 0),
             "allow": str(allow), "deny": str(deny)}
            for target_id, (allow, deny) in self._perm_values.items()
        ]

        def done(_result: Any) -> None:
            self.toast_ok("Permisos actualizados.")
            self.app.refresh_guild()

        self.run(lambda: self.app.client.update_channel(
            channel.id, {"permission_overwrites": payload}), done)

    def _build_invites_tab(self, channel: Channel) -> None:
        app = self.app
        frame = self._detail_frames["invites"]
        self.invites_status = tk.Label(frame, text="", bg=C.CARD, fg=C.MUTED,
                                       font=app.theme.font(8), anchor="w")
        self.invites_status.pack(fill="x", pady=(0, 6))
        columns = [TableColumn("code", "Código", 160),
                   TableColumn("uses", "Usos", 90),
                   TableColumn("creator", "Creador", 160),
                   TableColumn("expires", "Expira", 150)]
        self.invites_table = Table(frame, columns, height=7, theme=app.theme,
                                   multi=False, empty_text="Sin invitaciones en este canal.")
        self.invites_table.pack(fill="both", expand=True)
        buttons = tk.Frame(frame, bg=C.CARD)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Revocar seleccionada", style="SmallDanger.TButton",
                   command=lambda: self._revoke_invites(channel, False)).pack(side="left")
        ttk.Button(buttons, text="Revocar todas", style="SmallDanger.TButton",
                   command=lambda: self._revoke_invites(channel, True)).pack(
            side="left", padx=(6, 0))
        self._invites_loaded_for = None

    def _load_invites(self, channel: Channel) -> None:
        if self._invites_loaded_for == channel.id:
            return
        self._invites_loaded_for = channel.id
        self.invites_status.configure(text="Cargando invitaciones…")

        def done(invites: list[Invite]) -> None:
            self._channel_invites = [invite for invite in invites
                                     if invite.channel_id == channel.id]
            try:
                self.invites_status.configure(
                    text=f"{len(self._channel_invites)} invitaciones en este canal.")
                self.invites_table.set_rows([{
                    "_id": invite.code, "code": invite.code,
                    "uses": invite.uses_label,
                    "creator": invite.inviter.display_name if invite.inviter else "—",
                    "expires": invite.expiry_label,
                } for invite in self._channel_invites])
            except tk.TclError:
                pass

        self.run(lambda: self.app.client.list_guild_invites(self.app.guild.id), done)

    def _revoke_invites(self, channel: Channel, all_invites: bool) -> None:
        if not self.require("MANAGE_CHANNELS", "revocar invitaciones"):
            return
        codes = [invite.code for invite in getattr(self, "_channel_invites", [])
                 if all_invites or invite.code in self.invites_table.selected_ids()]
        if not codes:
            self.toast_warn("Selecciona una invitación.")
            return
        client = self.app.client

        def work() -> None:
            for code in codes:
                client.delete_invite(code)

        def done(_result: Any) -> None:
            self._invites_loaded_for = None
            self._load_invites(channel)
            self.toast_ok("Invitaciones revocadas.")

        self.run(work, done)

    def _build_integrations_tab(self, channel: Channel) -> None:
        app = self.app
        frame = self._detail_frames["integrations"]
        self.integrations_status = tk.Label(frame, text="", bg=C.CARD, fg=C.MUTED,
                                            font=app.theme.font(8), anchor="w")
        self.integrations_status.pack(fill="x", pady=(0, 6))
        self.integrations_host = tk.Frame(frame, bg=C.CARD)
        self.integrations_host.pack(fill="both", expand=True)
        self._integrations_loaded_for = None

    def _load_integrations(self, channel: Channel) -> None:
        if self._integrations_loaded_for == channel.id:
            return
        self._integrations_loaded_for = channel.id
        self.integrations_status.configure(text="Cargando integraciones…")
        guild_id = self.app.guild.id
        client = self.app.client

        def done(data: tuple[list[Webhook], list[dict]]) -> None:
            webhooks, followers = data
            for child in self.integrations_host.winfo_children():
                child.destroy()
            channel_webhooks = [w for w in webhooks if w.channel_id == channel.id]
            self.integrations_status.configure(
                text=f"{len(channel_webhooks)} webhooks · "
                     f"{len(followers)} canales que siguen.")
            tk.Label(self.integrations_host,
                     text=f"Webhooks ({len(channel_webhooks)})", bg=C.CARD,
                     fg=C.TEXT, font=self.app.theme.font(9, "bold"),
                     anchor="w").pack(fill="x", pady=(4, 2))
            for webhook in channel_webhooks:
                row = tk.Frame(self.integrations_host, bg=C.CARD)
                row.pack(fill="x", pady=1)
                tk.Label(row, text=webhook.name, bg=C.CARD, fg=C.DIM,
                         font=self.app.theme.font(8), anchor="w").pack(
                    side="left", fill="x", expand=True)
                ttk.Button(row, text="Eliminar", style="SmallDanger.TButton",
                           command=lambda w=webhook: self._delete_webhook(channel, w)).pack(
                    side="right")
            if not channel_webhooks:
                tk.Label(self.integrations_host, text="Sin webhooks.", bg=C.CARD,
                         fg=C.FAINT, font=self.app.theme.font(8), anchor="w").pack(fill="x")
            ttk.Button(self.integrations_host, text="Crear webhook",
                       style="Small.TButton",
                       command=lambda: self._create_webhook(channel)).pack(
                anchor="w", pady=(6, 10))
            tk.Label(self.integrations_host,
                     text=f"Canales que siguen ({len(followers)})", bg=C.CARD,
                     fg=C.TEXT, font=self.app.theme.font(9, "bold"),
                     anchor="w").pack(fill="x", pady=(4, 2))
            for follower in followers:
                tk.Label(self.integrations_host,
                         text=str(follower.get("webhook_id") or follower.get("channel_id") or "—"),
                         bg=C.CARD, fg=C.DIM, font=self.app.theme.font(8),
                         anchor="w").pack(fill="x")
            if not followers:
                tk.Label(self.integrations_host, text="Sin canales que sigan este canal.",
                         bg=C.CARD, fg=C.FAINT, font=self.app.theme.font(8),
                         anchor="w").pack(fill="x")
            ttk.Button(self.integrations_host, text="Más información",
                       style="Small.TButton",
                       command=lambda: webbrowser.open(
                           "https://support.discord.com/hc/articles/360028384531")).pack(
                anchor="w", pady=(6, 0))

        def work() -> tuple[list[Webhook], list[dict]]:
            webhooks = client.list_webhooks(guild_id)
            if channel.type == 5:
                followers = client.list_channel_followers(channel.id)
            else:
                followers = []
            return webhooks, followers

        self.run(work, done)

    def _create_webhook(self, channel: Channel) -> None:
        if not self.require("MANAGE_WEBHOOKS", "crear webhooks"):
            return
        client = self.app.client

        def done(_result: Any) -> None:
            self._integrations_loaded_for = None
            self._load_integrations(channel)

        self.run(lambda: client.create_webhook(channel.id, "DS Studio"), done)

    def _delete_webhook(self, channel: Channel, webhook: Webhook) -> None:
        if not self.require("MANAGE_WEBHOOKS", "eliminar webhooks"):
            return
        client = self.app.client

        def done(_result: Any) -> None:
            self._integrations_loaded_for = None
            self._load_integrations(channel)

        self.run(lambda: client.delete_webhook(webhook.id), done)

    # ------------------------------------------------------------------ #
    def _copy(self, value: str) -> None:
        copy_to_clipboard(self, value)
        self.toast_ok("ID copiado al portapapeles.")

    def _open_topic_emojis(self) -> None:
        EmojiPicker(self, self.app, self._topic_emoji_button, self._insert_topic_emoji)

    def _insert_topic_emoji(self, text: str) -> None:
        topic = getattr(self, "topic_text", None)
        if topic is None:
            return
        try:
            topic.insert("insert", text)
            topic.focus_set()
        except tk.TclError:
            pass

    def _detail_name_changed(self, *_args: Any) -> None:
        if getattr(self, "_detail_font_internal", False):
            return
        self._detail_font_source = self.name_var.get()

    def _apply_detail_font(self) -> None:
        source = self._detail_font_source or self.name_var.get()
        converted = apply_font_style(source, self.detail_font_var.get())
        self._detail_font_internal = True
        try:
            self.name_var.set(converted)
        finally:
            self._detail_font_internal = False

    def _save(self, channel: Channel) -> None:
        if not self.require("MANAGE_CHANNELS", "editar canales"):
            return
        raw_name = self.name_var.get()
        name = _channel_name(channel, raw_name)
        if not name.strip():
            self.toast_warn("El nombre del canal no puede quedar vacío.")
            return
        fields: dict[str, Any] = {"name": name}
        if not channel.is_category:
            parent = self.category_map.get(self.category_var.get())
            fields["parent_id"] = parent
        if channel.is_text:
            fields["topic"] = getattr(self, "topic_text", None) and self.topic_text.get(
                "1.0", "end").strip() or None
            fields["nsfw"] = bool(getattr(self, "nsfw_var", tk.BooleanVar()).get())
            fields["rate_limit_per_user"] = safe_int(getattr(self, "slow_var", tk.StringVar()).get())
            fields["default_auto_archive_duration"] = {
                "1 día": 1440, "3 días": 4320, "7 días": 10080}.get(
                    getattr(self, "archive_var", tk.StringVar(value="1 día")).get(), 1440)
        elif channel.is_voice:
            fields["user_limit"] = safe_int(getattr(self, "limit_var", tk.StringVar()).get())
            fields["bitrate"] = max(8000, safe_int(
                getattr(self, "bitrate_var", tk.StringVar(value="64")).get()) * 1000)
        client = self.app.client

        def done(_result: Any) -> None:
            self.toast_ok(f"Canal «{name}» actualizado.")
            self.app.refresh_guild()

        def failed(error: BaseException) -> None:
            self.error(error)

        self.run(lambda: client.update_channel(channel.id, fields), done, failed)

    def _delete(self, channel: Channel) -> None:
        if not self.require("MANAGE_CHANNELS", "eliminar canales"):
            return
        client = self.app.client
        shown = channel.display_name
        required = shown
        dialog = ConfirmDialog(self, "Eliminar canal",
                               f"Se eliminará «{shown}» y todos sus mensajes. "
                               "Esta acción no se puede deshacer.",
                               confirm_text="Eliminar definitivamente", danger=True,
                               theme=self.app.theme, require_text=required)
        if not dialog.show():
            return

        def done(_result: Any) -> None:
            self.toast_ok(f"Canal «{channel.display_name}» eliminado.")
            self.selected_id = None
            self.app.refresh_guild()

        self.run(lambda: client.delete_channel(channel.id), done)

    def _move(self, channel: Channel, delta: int) -> None:
        if not self.require("MANAGE_CHANNELS", "reordenar canales"):
            return
        if channel.is_category:
            categories = [item for item in self._channels if item.is_category]
            index = next((i for i, item in enumerate(categories) if item.id == channel.id), None)
            if index is None:
                return
            target_index = index + delta
            if target_index < 0 or target_index >= len(categories):
                return
            other = categories[target_index]
            positions = [{"id": channel.id, "position": other.position},
                         {"id": other.id, "position": channel.position}]
            client = self.app.client

            def reorder_categories(_result: Any) -> None:
                channel.position, other.position = other.position, channel.position
                self._channels.sort(key=lambda c: (c.position, int(c.id)))
                self._render_list()

            self.run(lambda: client.reorder_channels(self.app.guild.id, positions),
                     reorder_categories)
            return
        items = [item for item, _indent in self._flat_list()]
        index = next((i for i, item in enumerate(items) if item.id == channel.id), None)
        if index is None:
            return
        target_index = index + delta
        if target_index < 0 or target_index >= len(items):
            return
        other = items[target_index]
        if other.parent_id != channel.parent_id or other.is_category != channel.is_category:
            return
        positions = [
            {"id": channel.id, "position": other.position},
            {"id": other.id, "position": channel.position},
        ]
        client = self.app.client

        def done(_result: Any) -> None:
            channel.position, other.position = other.position, channel.position
            self._channels.sort(key=lambda c: (c.position, int(c.id)))
            self._render_list()

        self.run(lambda: client.reorder_channels(self.app.guild.id, positions), done)

    # ------------------------------------------------------------------ #
    def create_channel(self) -> None:
        if not self.require("MANAGE_CHANNELS", "crear canales"):
            return
        ChannelCreateModal(self, self.app, self).show()

    def create_category(self) -> None:
        if not self.require("MANAGE_CHANNELS", "crear categorías"):
            return
        ChannelCreateModal(self, self.app, self, category_only=True).show()

    def _edit_overwrites(self, channel: Channel) -> None:
        if not self.require("MANAGE_CHANNELS", "editar permisos de canal"):
            return
        OverwritesModal(self, self.app, channel).show()


# --------------------------------------------------------------------------- #
# Modales
# --------------------------------------------------------------------------- #

class ChannelCreateModal(Modal):
    def __init__(self, parent: tk.Misc, app: Any, page: ChannelsPage,
                 category_only: bool = False):
        super().__init__(parent, "Nueva categoría" if category_only else "Nuevo canal",
                         width=520, theme=app.theme,
                         subtitle="Los canales nuevos se crean al final de su categoría.")
        self.app = app
        self.page = page
        self._category_only = category_only
        body = self.body

        name_field = Field(body, "Nombre", bg=C.CARD)
        name_field.pack(fill="x", pady=(0, 12))
        self.name_var = tk.StringVar()
        entry = ttk.Entry(name_field.slot, textvariable=self.name_var)
        name_field.add(entry)
        entry.focus_set()

        font_field = Field(body, "Tipografía del nombre",
                           "Escribe el nombre y elige un estilo Unicode.")
        font_field.pack(fill="x", pady=(0, 12))
        self.font_var = tk.StringVar(value="Normal")
        font_combo = ttk.Combobox(font_field.slot, values=STYLE_NAMES,
                                  state="readonly", textvariable=self.font_var)
        font_field.add(font_combo)
        font_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply_font())
        self._font_source = ""
        self._font_internal = False
        self.name_var.trace_add("write", self._name_changed)

        if not category_only:
            type_field = Field(body, "Tipo de canal", bg=C.CARD)
            type_field.pack(fill="x", pady=(0, 12))
            self._types = creatable_channel_types(app.guild.is_community)
            self.type_var = tk.StringVar(value=self._types[0][1])
            combo = ttk.Combobox(type_field.slot, state="readonly",
                                 values=[label for _value, label in self._types],
                                 textvariable=self.type_var)
            type_field.add(combo)
            if not app.guild.is_community:
                tk.Label(type_field.slot,
                         text="Anuncios, foro, media y escenario requieren la comunidad "
                              "activada en el servidor.",
                         bg=C.CARD, fg=C.FAINT, font=app.theme.font(7),
                         wraplength=440, justify="left", anchor="w").pack(
                    fill="x", pady=(4, 0))

            cat_field = Field(body, "Categoría", bg=C.CARD)
            cat_field.pack(fill="x", pady=(0, 12))
            categories = ["Sin categoría"] + [c.name or "" for c in page._channels if c.is_category]
            self.category_var = tk.StringVar(value="Sin categoría")
            cat_combo = ttk.Combobox(cat_field.slot, values=categories, state="readonly",
                                     textvariable=self.category_var)
            cat_field.add(cat_combo)

            topic_field, self.topic_text = labeled_text(body, app, "Tema (opcional)", height=2)
            topic_field.pack(fill="x", pady=(0, 12))

        self.add_button("Cancelar", self.close)
        self.add_button("Crear", self._submit, style="Accent.TButton")

    def _name_changed(self, *_args: Any) -> None:
        if getattr(self, "_font_internal", False):
            return
        self._font_source = self.name_var.get()

    def _apply_font(self) -> None:
        source = self._font_source or self.name_var.get()
        converted = apply_font_style(source, self.font_var.get())
        self._font_internal = True
        try:
            self.name_var.set(converted)
        finally:
            self._font_internal = False

    def _submit(self) -> None:
        raw_name = self.name_var.get()
        if self._category_only:
            name = raw_name
            error = "El nombre de la categoría no puede quedar vacío."
        else:
            type_value = next((value for value, label in self._types
                               if label == self.type_var.get()), 0)
            name = raw_name
            error = "El nombre del canal no puede quedar vacío."
        if not name.strip():
            self.show_error(error)
            return
        fields: dict[str, Any] = {"name": name}
        if self._category_only:
            fields["type"] = 4
        else:
            fields["type"] = type_value
            category = self.page.category_map.get(self.category_var.get())
            if category:
                fields["parent_id"] = category
            topic = self.topic_text.get("1.0", "end").strip()
            if topic:
                fields["topic"] = topic
            if type_value == 0:
                fields["nsfw"] = False
        client = self.app.client
        self.set_busy(True)

        def done(channel: Channel) -> None:
            self.page.selected_id = channel.id
            self.app.toasts.show(f"«{channel.display_name}» creado.", "success")
            self.close()
            self.app.refresh_guild()

        def failed(error: BaseException) -> None:
            self.set_busy(False)
            self.show_error(str(error))

        self.app.run_task(lambda: client.create_channel(self.app.guild.id, fields),
                          done, failed)


class OverwritesModal(Modal):
    """Editor de permisos por rol para un canal."""

    def __init__(self, parent: tk.Misc, app: Any, channel: Channel):
        super().__init__(parent, f"Permisos de #{channel.display_name}", width=600,
                         theme=app.theme,
                         subtitle="Elige un rol y ajusta sus permisos en este canal.")
        self.app = app
        self.channel = channel
        self.values: dict[str, tuple[int, int]] = {
            overwrite.id: (overwrite.allow, overwrite.deny)
            for overwrite in channel.permission_overwrites
        }
        self.types: dict[str, int] = {overwrite.id: overwrite.type
                                      for overwrite in channel.permission_overwrites}
        self.roles = [role for role in app.guild.sorted_roles() if not role.managed]
        self._current_id = ""
        self._editor: OverwriteEditor | None = None

        selector = tk.Frame(self.body, bg=C.CARD)
        selector.pack(fill="x", pady=(0, 10))
        tk.Label(selector, text="ROL O MIEMBRO", bg=C.CARD, fg=C.MUTED,
                 font=app.theme.font(8, "bold")).pack(anchor="w")
        self.target_var = tk.StringVar()
        self.combo = ttk.Combobox(selector, values=self._target_values(), state="readonly",
                                  textvariable=self.target_var)
        self.combo.pack(fill="x", pady=(4, 0))
        self.combo.bind("<<ComboboxSelected>>", lambda _e: self._change_target())
        self.host = tk.Frame(self.body, bg=C.CARD)
        self.host.pack(fill="both", expand=True)
        self.add_button("Cancelar", self.close)
        self.add_button("Guardar permisos", self._save, style="Accent.TButton")
        values = self._target_values()
        if values:
            self.target_var.set(values[0])
            self._change_target()

    def _target_values(self) -> list[str]:
        values = [f"@everyone"]
        for role in self.roles:
            values.append(role.name)
        return values

    def _target_id(self, label: str) -> str:
        if label == "@everyone":
            everyone = self.app.guild.everyone_role
            return everyone.id if everyone else self.app.guild.id
        role = next((r for r in self.roles if r.name == label), None)
        return role.id if role else ""

    def _change_target(self) -> None:
        if self._editor is not None and self._current_id:
            self.values[self._current_id] = self._editor.get_allow_deny()
        target_id = self._target_id(self.target_var.get())
        if not target_id:
            return
        self._current_id = target_id
        allow, deny = self.values.get(target_id, (0, 0))
        self.types.setdefault(target_id, 0)
        if self._editor is not None:
            self._editor.destroy()
        self._editor = OverwriteEditor(self.host, self.app, allow, deny)
        self._editor.pack(fill="both", expand=True)

    def _save(self) -> None:
        if self._editor is not None and self._current_id:
            self.values[self._current_id] = self._editor.get_allow_deny()
        payload = [
            {"id": target_id, "type": self.types.get(target_id, 0),
             "allow": str(allow), "deny": str(deny)}
            for target_id, (allow, deny) in self.values.items() if allow or deny
        ]
        client = self.app.client
        self.set_busy(True)

        def done(_result: Any) -> None:
            self.app.toasts.show("Permisos del canal actualizados.", "success")
            self.close()
            self.app.refresh_guild()

        def failed(error: BaseException) -> None:
            self.set_busy(False)
            self.show_error(str(error))

        self.app.run_task(
            lambda: client.update_channel(self.channel.id,
                                          {"permission_overwrites": payload}),
            done, failed)
