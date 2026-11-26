"""Miembros del servidor: búsqueda, roles, apodo, aislamiento y sanciones."""
from __future__ import annotations

import tkinter as tk
import webbrowser
from datetime import datetime, timedelta, timezone
from tkinter import ttk
from typing import Any

from ...constants import DELETE_MESSAGE_WINDOWS, TIMEOUT_PRESETS
from ...models import Member, fmt_date, fmt_datetime, fmt_relative, snowflake_time
from ...util import plural
from ..theme import C
from ..widgets import (Avatar, Checkbox, ConfirmDialog, EmptyState, Field, Modal,
                       PageHeader, ScrollFrame, SearchEntry, Table, TableColumn,
                       Tooltip, copy_to_clipboard)
from .base import Page
from .modals import BanModal, DirectMessageModal

FILTERS = ["Todos", "Humanos", "Bots", "Aislados", "Pendientes"]


class MembersPage(Page):
    key = "members"
    label = "Miembros"
    glyph = "◉"

    def build(self) -> None:
        app = self.app
        self.header = PageHeader(self, app, "Miembros",
                                 "Busca, filtra y administra a las personas del servidor.")
        self.header.pack(fill="x", padx=28, pady=(22, 0))
        self.header.button("Actualizar", self.refresh)

        toolbar = tk.Frame(self, bg=C.CONTENT)
        toolbar.pack(fill="x", padx=28, pady=(14, 8))
        self.search = SearchEntry(toolbar, placeholder="Buscar por nombre o apodo…",
                                  on_change=lambda _t: self._on_search(), width=34,
                                  bg=C.CONTENT, theme=app.theme)
        self.search.pack(side="left")
        self.filter_var = tk.StringVar(value=FILTERS[0])
        filter_combo = ttk.Combobox(toolbar, values=FILTERS, state="readonly", width=14,
                                    textvariable=self.filter_var)
        filter_combo.pack(side="left", padx=(10, 0))
        filter_combo.bind("<<ComboboxSelected>>", lambda _e: self._render())
        self.count_label = tk.Label(toolbar, text="", bg=C.CONTENT, fg=C.MUTED,
                                    font=app.theme.font(9))
        self.count_label.pack(side="left", padx=(14, 0))
        self.more_button = ttk.Button(toolbar, text="Cargar más", style="Small.TButton",
                                      command=lambda: self._load(first=False))
        self.more_button.pack(side="right")
        self.more_button.configure(state="disabled")
        self.ban_button = ttk.Button(toolbar, text="Banear", style="SmallDanger.TButton",
                                     command=lambda: self._bulk_action("ban"))
        self.ban_button.pack(side="right", padx=(0, 6))
        Tooltip(self.ban_button, "Banear seleccionados · Ctrl+3")
        self.kick_button = ttk.Button(toolbar, text="Expulsar", style="SmallDanger.TButton",
                                      command=lambda: self._bulk_action("kick"))
        self.kick_button.pack(side="right", padx=(0, 6))
        Tooltip(self.kick_button, "Expulsar seleccionados · Ctrl+2")
        self.timeout_button = ttk.Button(toolbar, text="Suspender", style="SmallDanger.TButton",
                                         command=lambda: self._bulk_action("timeout"))
        self.timeout_button.pack(side="right", padx=(0, 6))
        Tooltip(self.timeout_button, "Suspender seleccionados · Ctrl+1")
        self.loading_label = tk.Label(toolbar, text="", bg=C.CONTENT, fg=C.FAINT,
                                      font=app.theme.font(8))
        self.loading_label.pack(side="right", padx=(0, 10))
        if not app.can("BAN_MEMBERS"):
            self.ban_button.configure(state="disabled")
        if not app.can("KICK_MEMBERS"):
            self.kick_button.configure(state="disabled")
        if not app.can("MODERATE_MEMBERS"):
            self.timeout_button.configure(state="disabled")

        columns = [
            TableColumn("user", "Usuario", 180, stretch=True),
            TableColumn("nick", "Apodo", 130),
            TableColumn("roles", "Roles", 220, stretch=True),
            TableColumn("joined", "Se unió al servidor", 140),
            TableColumn("discord", "Se unió a Discord", 140),
            TableColumn("status", "Estado", 120),
        ]
        self.table = Table(self, columns, height=18, on_double=self._open_member,
                           multi=True, theme=app.theme,
                           empty_text="No hay miembros que coincidan con el filtro.")
        self.table.pack(fill="both", expand=True, padx=28, pady=(0, 22))
        self._member_anchor: str | None = None
        self.table.tree.bind("<ButtonPress-1>", self._member_press)
        self.table.tree.bind("<Shift-Up>", lambda _e: self._member_extend(-1))
        self.table.tree.bind("<Shift-Down>", lambda _e: self._member_extend(1))
        self.table.tree.bind("<Shift-Prior>", lambda _e: self._member_extend(-18))
        self.table.tree.bind("<Shift-Next>", lambda _e: self._member_extend(18))
        self.table.tree.bind("<Control-Key-1>",
                             lambda _e: self._bulk_action("timeout"))
        self.table.tree.bind("<Control-Key-2>",
                             lambda _e: self._bulk_action("kick"))
        self.table.tree.bind("<Control-Key-3>",
                             lambda _e: self._bulk_action("ban"))
        self.table.tree.unbind("<Button-3>")
        self.table.tree.bind("<Button-3>", self._member_context)
        self._member_menu = tk.Menu(self, tearoff=0, bg=C.CARD, fg=C.TEXT,
                                    activebackground=C.ACCENT_SOFT,
                                    activeforeground=C.TEXT)
        self._member_menu.add_command(label="Ver ficha", command=self._context_profile)
        self._member_menu.add_command(label="Copiar ID", command=self._context_copy_id)
        self._member_menu.add_separator()
        self._member_menu.add_command(label="Suspender",
                                      command=lambda: self._bulk_action("timeout"))
        self._member_menu.add_command(label="Expulsar",
                                      command=lambda: self._bulk_action("kick"))
        self._member_menu.add_command(label="Banear",
                                      command=lambda: self._bulk_action("ban"))

        self._members: list[Member] = []
        self._after: str | None = None
        self._has_more = False
        self._loading = False
        self._search_note = ""

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        self._members = []
        self._after = None
        self._has_more = False
        self._search_note = ""
        self._load(first=True)

    def on_guild_refreshed(self) -> None:
        pass

    def _on_search(self) -> None:
        self._members = []
        self._after = None
        self._has_more = False
        self._search_note = ""
        self._load(first=True)

    def _load(self, first: bool) -> None:
        if self._loading:
            return
        client = self.app.client
        guild_id = self.app.guild.id
        query = self.search.value()
        after = None if first else self._after
        self._loading = True
        self.loading_label.configure(text="Cargando…")
        self.more_button.configure(state="disabled")

        if query:
            def work() -> list[Member]:
                return client.search_members(guild_id, query, 100)
        else:
            def work() -> list[Member]:
                return client.list_members(guild_id, 100, after)

        def done(members: list[Member]) -> None:
            self._loading = False
            self.loading_label.configure(text="")
            if first:
                self._members = list(members)
            else:
                known = {m.user.id for m in self._members}
                self._members.extend(m for m in members if m.user.id not in known)
            if not query and members:
                self._after = members[-1].user.id
            self._has_more = bool(members) and len(members) == 100 and not query
            self.more_button.configure(state="normal" if self._has_more else "disabled")
            self._render()

        def failed(error: BaseException) -> None:
            self._loading = False
            self.loading_label.configure(text="")
            from ...errors import DiscordError
            if query and isinstance(error, DiscordError) and error.status in (403, 50001):
                self._search_note = ("La búsqueda en el servidor requiere el intento "
                                     "«Server Members». Se filtra en local.")
                self._fallback_search()
            else:
                self.error(error)

        self.run(work, done, failed)

    def _fallback_search(self) -> None:
        """Si Discord no deja buscar, se filtra sobre la primera página de miembros."""
        client = self.app.client
        guild_id = self.app.guild.id

        def work() -> list[Member]:
            return client.list_members(guild_id, 100, None)

        def done(members: list[Member]) -> None:
            self._members = members
            self._after = members[-1].user.id if members else None
            self._has_more = len(members) == 100
            self.more_button.configure(state="normal" if self._has_more else "disabled")
            self._render()

        def failed(error: BaseException) -> None:
            self._search_note = ("No se pudo cargar la lista de miembros: el bot necesita el "
                                 "intento «Server Members» en el portal de desarrolladores.")
            self._render()

        self.run(work, done, failed)

    # ------------------------------------------------------------------ #
    def _filtered(self) -> list[Member]:
        choice = self.filter_var.get()
        members = self._members
        if choice == "Humanos":
            members = [m for m in members if not m.user.bot]
        elif choice == "Bots":
            members = [m for m in members if m.user.bot]
        elif choice == "Aislados":
            members = [m for m in members if m.is_timed_out]
        elif choice == "Pendientes":
            members = [m for m in members if m.pending]
        needle = self.search.value().lower()
        if needle and self._search_note:
            members = [m for m in members
                       if needle in m.user.username.lower()
                       or needle in m.user.display_name.lower()
                       or needle in (m.nick or "").lower()]
        return members

    def _render(self) -> None:
        members = self._filtered()
        role_names = {role.id: role.name for role in self.app.guild.roles}
        rows = []
        for member in members:
            names = [role_names[rid] for rid in member.roles
                     if rid in role_names and role_names[rid] != "@everyone"]
            status = "Activo"
            tags: tuple[str, ...] = ()
            if member.is_timed_out:
                status = "Aislado"
                tags = ("danger",)
            elif member.pending:
                status = "Pendiente"
                tags = ("warning",)
            elif member.user.bot:
                status = "Bot"
                tags = ("muted",)
            rows.append({
                "_id": member.user.id,
                "user": member.user.display_name,
                "nick": member.nick or "—",
                "roles": ", ".join(names[:3]) + (f" +{len(names) - 3}" if len(names) > 3 else "")
                         if names else "—",
                "joined": fmt_date(member.joined_at),
                "discord": fmt_date(member.user.created_at
                                    or snowflake_time(member.user.id)),
                "status": status,
                "_tags": tags,
                "_raw": {"user": member.user.display_name, "joined": member.joined_at,
                         "status": status},
                "_member": member,
            })
        self.table.set_rows(rows)
        total = len(self._members)
        self.count_label.configure(
            text=f"{len(members)} de {plural(total, 'miembro cargado', 'miembros cargados')}"
            + ("  ·  " + self._search_note if self._search_note else ""))
        if not members and not self._members and not self._loading:
            self.table.set_empty_text("Este servidor no devolvió miembros.")

    def _open_member(self, row: dict) -> None:
        member: Member | None = row.get("_member")
        if member is None:
            return
        MemberModal(self, self.app, self, member).show()

    def _selected_members(self) -> list[Member]:
        return [row["_member"] for row in self.table.selected_rows()
                if row.get("_member") is not None]

    def _member_press(self, event: tk.Event) -> str | None:
        row_id = self.table.tree.identify_row(event.y)
        if not row_id:
            return None
        ctrl = bool(event.state & 0x0004)
        shift = bool(event.state & 0x0001)
        if ctrl:
            selected = set(self.table.tree.selection())
            if row_id in selected:
                selected.discard(row_id)
            else:
                selected.add(row_id)
            self._member_set_selection(selected)
            self.table.tree.focus(row_id)
            return "break"
        if shift:
            selected = set(self.table.tree.selection())
            if row_id in selected:
                selected.discard(row_id)
                self._member_set_selection(selected)
                return "break"
            rows = list(self.table.tree.get_children())
            anchor = self._member_anchor if self._member_anchor in rows else row_id
            low, high = sorted((rows.index(anchor), rows.index(row_id)))
            self._member_set_selection(set(rows[low:high + 1]))
            self.table.tree.focus(row_id)
            return "break"
        self._member_anchor = row_id
        return None

    def _member_set_selection(self, selected: set[str]) -> None:
        rows = list(self.table.tree.get_children())
        ordered = [row for row in rows if row in selected]
        if ordered:
            self.table.tree.selection_set(*ordered)
        else:
            current = self.table.tree.selection()
            if current:
                self.table.tree.selection_remove(*current)

    def _member_extend(self, delta: int) -> str:
        rows = list(self.table.tree.get_children())
        if not rows:
            return "break"
        focus = self.table.tree.focus()
        if focus not in rows:
            focus = self._member_anchor if self._member_anchor in rows else rows[0]
        anchor = self._member_anchor if self._member_anchor in rows else focus
        target = max(0, min(rows.index(focus) + delta, len(rows) - 1))
        low, high = sorted((rows.index(anchor), target))
        self._member_set_selection(set(rows[low:high + 1]))
        self.table.tree.focus(rows[target])
        self.table.tree.see(rows[target])
        return "break"

    def _member_context(self, event: tk.Event) -> None:
        row_id = self.table.tree.identify_row(event.y)
        if not row_id:
            return
        if row_id not in self.table.tree.selection():
            self.table.tree.selection_set(row_id)
        self.table.tree.focus(row_id)
        self._member_anchor = row_id
        selected = len(self.table.tree.selection())
        self._member_menu.entryconfigure(0, label=("Ver ficha" if selected <= 1
                                                   else f"Ver ficha del primero"))
        try:
            self._member_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._member_menu.grab_release()
            except tk.TclError:
                pass

    def _context_profile(self) -> None:
        members = self._selected_members()
        if members:
            MemberModal(self, self.app, self, members[0]).show()

    def _context_copy_id(self) -> None:
        members = self._selected_members()
        if not members:
            return
        copy_to_clipboard(self, "\n".join(member.user.id for member in members))
        self.app.toasts.show(f"{len(members)} ID(s) copiados.", "success")

    def _bulk_action(self, mode: str) -> None:
        members = self._selected_members()
        if not members:
            self.toast_warn("Selecciona uno o varios miembros.")
            return
        permission = {"timeout": "MODERATE_MEMBERS", "kick": "KICK_MEMBERS",
                      "ban": "BAN_MEMBERS"}[mode]
        if not self.require(permission, f"la acción «{mode}»"):
            return
        MemberBulkActionModal(self, self.app, self, members, mode).show()


# --------------------------------------------------------------------------- #
# Ficha de miembro
# --------------------------------------------------------------------------- #

class MemberModal(Modal):
    def __init__(self, parent: tk.Misc, app: Any, page: MembersPage, member: Member):
        super().__init__(parent, member.display_name, width=700, theme=app.theme,
                         subtitle="Ficha de miembro")
        self.app = app
        self.page = page
        self.member = member
        self.can_roles = app.can("MANAGE_ROLES")
        self.can_nick = app.can("MANAGE_NICKNAMES")
        self.can_timeout = app.can("MODERATE_MEMBERS")
        self.can_kick = app.can("KICK_MEMBERS")
        self.can_ban = app.can("BAN_MEMBERS")
        self._build()

    def _build(self) -> None:
        app = self.app
        member = self.member
        body = self.body

        head = tk.Frame(body, bg=C.CARD)
        head.pack(fill="x", pady=(0, 12))
        avatar = Avatar(head, member.display_name, 48, bg=C.CARD, theme=app.theme)
        avatar.pack(side="left")
        if getattr(member, "user", None) is not None:
            app.images.apply(avatar, member.user.avatar_url, 48)
        info = tk.Frame(head, bg=C.CARD)
        info.pack(side="left", padx=(12, 0), fill="x", expand=True)
        tk.Label(info, text=member.display_name, bg=C.CARD, fg=C.TEXT,
                 font=app.theme.font(14, "bold"), anchor="w").pack(fill="x")
        tk.Label(info, text=f"{member.user.tag}  ·  ID {member.user.id}",
                 bg=C.CARD, fg=C.MUTED, font=(app.theme.mono_family, 8), anchor="w").pack(fill="x")
        created = member.user.created_at or snowflake_time(member.user.id)
        tk.Label(info, text=f"Se unió a Discord: {fmt_datetime(created)}  ·  "
                            f"Al servidor: {fmt_datetime(member.joined_at)}",
                 bg=C.CARD, fg=C.MUTED, font=app.theme.font(8), anchor="w").pack(fill="x")
        chips = tk.Frame(info, bg=C.CARD)
        chips.pack(fill="x", pady=(4, 0))
        if member.user.bot:
            tk.Label(chips, text="BOT", bg=C.CARD_ALT, fg=C.DIM, font=app.theme.font(8, "bold"),
                     padx=6, pady=1).pack(side="left", padx=(0, 4))
        if member.is_timed_out:
            tk.Label(chips, text="AISLADO", bg=C.RED_SOFT, fg="#ffb3b5",
                     font=app.theme.font(8, "bold"), padx=6, pady=1).pack(side="left", padx=(0, 4))
        if member.pending:
            tk.Label(chips, text="PENDIENTE", bg=C.YELLOW_SOFT, fg="#ffd98a",
                     font=app.theme.font(8, "bold"), padx=6, pady=1).pack(side="left")
        tk.Label(chips, text=f"Se unió {fmt_relative(member.joined_at)}", bg=C.CARD,
                 fg=C.FAINT, font=app.theme.font(8)).pack(side="right")
        copy = tk.Label(head, text="copiar ID", bg=C.CARD, fg=C.LINK,
                        font=app.theme.font(8), cursor="hand2")
        copy.pack(side="right", anchor="n")
        copy.bind("<Button-1>", lambda _e: self._copy_id())

        fields = tk.Frame(body, bg=C.CARD)
        fields.pack(fill="x", pady=(0, 10))
        nick_field = Field(fields, "Apodo en este servidor", "Vacío para usar el nombre global.")
        nick_field.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.nick_var = tk.StringVar(value=member.nick or "")
        self.nick_entry = ttk.Entry(nick_field.slot, textvariable=self.nick_var)
        nick_field.add(self.nick_entry)
        if not self.can_nick:
            self.nick_entry.configure(state="readonly")

        timeout_field = Field(fields, "Aislamiento temporal (timeout)")
        timeout_field.pack(side="left", fill="x", expand=False)
        row = tk.Frame(timeout_field.slot, bg=C.CARD)
        row.pack(fill="x")
        self.timeout_var = tk.StringVar(value=TIMEOUT_PRESETS[2][0])
        self.timeout_combo = ttk.Combobox(row, values=[label for label, _s in TIMEOUT_PRESETS],
                                          state="readonly", width=13, textvariable=self.timeout_var)
        self.timeout_combo.pack(side="left")
        ttk.Button(row, text="Aislar", style="Small.TButton",
                   command=self._apply_timeout).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Quitar", style="Small.TButton",
                   command=self._clear_timeout).pack(side="left", padx=(4, 0))
        if not self.can_timeout:
            self.timeout_combo.configure(state="disabled")

        label_row = tk.Frame(body, bg=C.CARD)
        label_row.pack(fill="x", pady=(4, 4))
        tk.Label(label_row, text="ROLES", bg=C.CARD, fg=C.MUTED,
                 font=app.theme.font(8, "bold")).pack(side="left")
        tk.Label(label_row, text="Marca o desmarca para asignar", bg=C.CARD, fg=C.FAINT,
                 font=app.theme.font(8)).pack(side="right")

        roles_box = tk.Frame(body, bg=C.CARD, highlightbackground=C.BORDER,
                             highlightthickness=1, height=196)
        roles_box.pack(fill="x")
        roles_box.pack_propagate(False)
        self.roles_scroll = ScrollFrame(roles_box, bg=C.CARD)
        self.roles_scroll.pack(fill="both", expand=True, padx=8, pady=8)
        grid = tk.Frame(self.roles_scroll.inner, bg=C.CARD)
        grid.pack(fill="both", expand=True)
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        self.role_vars: dict[str, tk.BooleanVar] = {}
        roles = [role for role in app.guild.sorted_roles() if not role.is_everyone]
        for index, role in enumerate(roles):
            var = tk.BooleanVar(value=role.id in member.roles)
            checkbox = Checkbox(grid, role.name, variable=var, bg=C.CARD,
                                font=app.theme.font(9),
                                disabled=not self.can_roles or role.managed)
            Tooltip(checkbox, "Sin color asignado" if role.color == 0 else role.color_hex)
            checkbox.grid(row=index // 2, column=index % 2, sticky="w", padx=(4, 10), pady=1)
            self.role_vars[role.id] = var
        if not roles:
            tk.Label(grid, text="Este servidor no tiene roles adicionales.", bg=C.CARD,
                     fg=C.MUTED, font=app.theme.font(9)).pack(pady=10)

        actions = tk.Frame(body, bg=C.CARD)
        actions.pack(fill="x", pady=(12, 0))
        for text, command, enabled in (
            ("Expulsar", self._kick, self.can_kick),
            ("Banear", self._ban, self.can_ban),
            ("Avatar", self._avatar, True),
            ("Registros", self._records, True),
            ("Enviar MD", self._dm, True),
        ):
            button = ttk.Button(actions, text=text, style="SmallDanger.TButton" if text != "Enviar MD" else "Small.TButton",
                                command=command)
            button.pack(side="left", padx=(0, 6))
            if not enabled:
                button.configure(state="disabled")

        self.add_button("Cerrar", self.close)
        self.add_button("Guardar cambios", self._save, style="Accent.TButton")

    # ------------------------------------------------------------------ #
    def _copy_id(self) -> None:
        copy_to_clipboard(self, self.member.user.id)
        self.app.toasts.show("ID copiado.", "success")

    def _save(self) -> None:
        member = self.member
        fields: dict[str, Any] = {}
        if self.can_nick:
            fields["nick"] = self.nick_var.get().strip() or None
        if self.can_roles:
            fields["roles"] = [role_id for role_id, var in self.role_vars.items() if var.get()]
        if not fields:
            self.show_error("No tienes permisos para modificar a este miembro.")
            return
        client = self.app.client
        guild_id = self.app.guild.id
        self.set_busy(True)

        def done(_result: Any) -> None:
            self.app.toasts.show("Miembro actualizado.", "success")
            self.page.refresh()
            self.app.refresh_guild()
            self.close()

        def failed(error: BaseException) -> None:
            self.set_busy(False)
            self.show_error(str(error))

        self.app.run_task(
            lambda: client.update_member(guild_id, member.user.id, fields), done, failed)

    def _apply_timeout(self) -> None:
        if not self.can_timeout:
            self.show_error("Falta el permiso «Aislar temporalmente».")
            return
        seconds = next((value for label, value in TIMEOUT_PRESETS
                        if label == self.timeout_var.get()), 600)
        until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        client = self.app.client
        guild_id = self.app.guild.id
        self.set_busy(True)

        def done(_result: Any) -> None:
            self.app.toasts.show(f"Miembro aislado durante {self.timeout_var.get()}.", "success")
            self.page.refresh()
            self.close()

        def failed(error: BaseException) -> None:
            self.set_busy(False)
            self.show_error(str(error))

        self.app.run_task(
            lambda: client.update_member(
                guild_id, self.member.user.id,
                {"communication_disabled_until": until.isoformat(timespec="seconds").replace("+00:00", "Z")}),
            done, failed)

    def _clear_timeout(self) -> None:
        if not self.can_timeout:
            self.show_error("Falta el permiso «Aislar temporalmente».")
            return
        client = self.app.client
        guild_id = self.app.guild.id
        self.set_busy(True)

        def done(_result: Any) -> None:
            self.app.toasts.show("Aislamiento retirado.", "success")
            self.page.refresh()
            self.close()

        def failed(error: BaseException) -> None:
            self.set_busy(False)
            self.show_error(str(error))

        self.app.run_task(
            lambda: client.update_member(guild_id, self.member.user.id,
                                         {"communication_disabled_until": None}),
            done, failed)

    def _kick(self) -> None:
        dialog = ConfirmDialog(self, "Expulsar miembro",
                               f"«{self.member.display_name}» saldrá del servidor. "
                               "Podrá volver con una invitación.",
                               confirm_text="Expulsar", danger=True, theme=self.app.theme)
        if not dialog.show():
            return
        client = self.app.client
        guild_id = self.app.guild.id
        self.set_busy(True)

        def done(_result: Any) -> None:
            self.app.toasts.show("Miembro expulsado.", "success")
            self.page.refresh()
            self.app.refresh_guild()
            self.close()

        def failed(error: BaseException) -> None:
            self.set_busy(False)
            self.show_error(str(error))

        self.app.run_task(lambda: client.kick_member(guild_id, self.member.user.id),
                          done, failed)

    def _ban(self) -> None:
        BanModal(self, self.app, user_id=self.member.user.id,
                 username=self.member.user.tag, on_done=self._after_ban)

    def _after_ban(self) -> None:
        self.page.refresh()
        self.app.refresh_guild()
        self.close()

    def _avatar(self) -> None:
        if self.member.user.avatar_url:
            webbrowser.open(self.member.user.avatar_url)

    def _records(self) -> None:
        MemberRecordsModal(self, self.app, self.member).show()

    def _dm(self) -> None:
        DirectMessageModal(self, self.app, self.member.user.id, self.member.display_name)


class MemberRecordsModal(Modal):
    def __init__(self, parent: tk.Misc, app: Any, member: Member):
        super().__init__(parent, f"Registros de {member.display_name}", width=760,
                         theme=app.theme,
                         subtitle="Acciones de auditoría que tuvieron a este usuario como objetivo.")
        self.app = app
        self.member = member
        columns = [TableColumn("date", "Fecha", 140),
                   TableColumn("action", "Acción", 220, stretch=True),
                   TableColumn("actor", "Moderador", 150),
                   TableColumn("reason", "Motivo", 240, stretch=True)]
        self.table = Table(self.body, columns, height=16, theme=app.theme,
                           empty_text="Sin registros de auditoría para este usuario.")
        self.table.pack(fill="both", expand=True)
        self.status = tk.Label(self.body, text="Cargando…", bg=C.CARD, fg=C.MUTED,
                               font=app.theme.font(8), anchor="w")
        self.status.pack(fill="x", pady=(6, 0))
        self.add_button("Cerrar", self.close)
        self._load()

    def _load(self) -> None:
        def work() -> list[Any]:
            return self.app.client.list_audit_logs(self.app.guild.id, limit=100)

        def done(entries: list[Any]) -> None:
            selected = [entry for entry in entries
                        if str(entry.target_id or "") == self.member.user.id]
            self.table.set_rows([{
                "_id": entry.id,
                "date": fmt_datetime(entry.created_at),
                "action": entry.action_label,
                "actor": entry.actor.display_name if entry.actor else "Sistema",
                "reason": entry.reason or "—",
            } for entry in selected])
            self.status.configure(text=f"{len(selected)} registros.", fg=C.MUTED)

        self.app.run_task(work, done, lambda error: self.status.configure(
            text=str(error), fg=C.RED))


class MemberBulkActionModal(Modal):
    def __init__(self, parent: tk.Misc, app: Any, page: MembersPage,
                 members: list[Member], mode: str):
        labels = {"timeout": "Suspender", "kick": "Expulsar", "ban": "Banear"}
        super().__init__(parent, f"{labels[mode]} {len(members)} miembro(s)",
                         width=560, theme=app.theme,
                         subtitle="La acción se aplicará a todos los seleccionados.")
        self.app = app
        self.page = page
        self.members = members
        self.mode = mode
        body = self.body
        tk.Label(body, text="MOTIVO", bg=C.CARD, fg=C.MUTED,
                 font=app.theme.font(8, "bold"), anchor="w").pack(fill="x")
        self.reason_text = tk.Text(
            body, height=3, bg=C.INPUT, fg=C.TEXT, insertbackground=C.TEXT,
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground=C.BORDER, font=app.theme.font(9),
            wrap="word", padx=8, pady=6)
        self.reason_text.pack(fill="x", pady=(2, 10))
        self.delete_var = tk.StringVar(value=DELETE_MESSAGE_WINDOWS[0][1])
        self.timeout_var = tk.StringVar(value=TIMEOUT_PRESETS[2][0])
        if mode == "ban":
            tk.Label(body, text="BORRAR MENSAJES", bg=C.CARD, fg=C.MUTED,
                     font=app.theme.font(8, "bold"), anchor="w").pack(fill="x")
            ttk.Combobox(body, values=[label for _v, label in DELETE_MESSAGE_WINDOWS],
                         state="readonly", textvariable=self.delete_var).pack(
                fill="x", pady=(2, 0))
        elif mode == "timeout":
            tk.Label(body, text="DURACIÓN DEL AISLAMIENTO", bg=C.CARD, fg=C.MUTED,
                     font=app.theme.font(8, "bold"), anchor="w").pack(fill="x")
            ttk.Combobox(body, values=[label for label, _s in TIMEOUT_PRESETS],
                         state="readonly", textvariable=self.timeout_var).pack(
                fill="x", pady=(2, 0))
        self.add_button("Cancelar", self.close)
        self.add_button(labels[mode], self._submit,
                        style="Danger.TButton" if mode != "timeout" else "Accent.TButton")

    def _submit(self) -> None:
        reason = self.reason_text.get("1.0", "end").strip() or None
        delete_seconds = next((value for value, label in DELETE_MESSAGE_WINDOWS
                               if label == self.delete_var.get()), 0)
        seconds = next((value for label, value in TIMEOUT_PRESETS
                        if label == self.timeout_var.get()), 600)
        until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        client = self.app.client
        guild_id = self.app.guild.id
        members = self.members
        mode = self.mode
        self.set_busy(True)

        def work() -> int:
            for member in members:
                if mode == "ban":
                    client.ban_member(guild_id, member.user.id, delete_seconds, reason)
                elif mode == "kick":
                    client.kick_member(guild_id, member.user.id, reason)
                else:
                    client.update_member(
                        guild_id, member.user.id,
                        {"communication_disabled_until":
                         until.isoformat(timespec="seconds").replace("+00:00", "Z")},
                        reason=reason)
            return len(members)

        def done(count: int) -> None:
            self.app.toasts.show(f"{count} miembros actualizados.", "success")
            self.page.refresh()
            self.app.refresh_guild()
            self.close()

        def failed(error: BaseException) -> None:
            self.set_busy(False)
            self.show_error(str(error))

        self.app.run_task(work, done, failed)
