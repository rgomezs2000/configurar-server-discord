"""Invitaciones del servidor: crear, copiar y revocar."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from ...constants import INVITE_MAX_AGES
from ...models import Invite, fmt_datetime
from ...util import safe_int
from ..theme import C
from ..widgets import (Card, Checkbox, ConfirmDialog, Field, PageHeader, Table,
                       TableColumn, copy_to_clipboard)
from .base import Page


class InvitesPage(Page):
    key = "invites"
    label = "Invitaciones"
    glyph = "⇉"

    def build(self) -> None:
        app = self.app
        self.header = PageHeader(self, app, "Invitaciones",
                                 "Gestiona los enlaces de entrada al servidor.")
        self.header.pack(fill="x", padx=28, pady=(22, 0))
        self.header.button("Actualizar", self.refresh)

        form = Card(self, padding=14)
        form.pack(fill="x", padx=28, pady=(14, 10))
        self._can_create = app.can("CREATE_INSTANT_INVITE")
        row = tk.Frame(form.body, bg=C.CARD)
        row.pack(fill="x")

        channel_field = Field(row, "Canal", bg=C.CARD)
        channel_field.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.channel_var = tk.StringVar()
        self.channel_combo = ttk.Combobox(channel_field.slot, values=self._text_channels(),
                                          state="readonly", textvariable=self.channel_var)
        channel_field.add(self.channel_combo)

        uses_field = Field(row, "Usos máximos (0 = ∞)", bg=C.CARD)
        uses_field.pack(side="left", padx=(0, 12))
        self.uses_var = tk.StringVar(value="0")
        ttk.Spinbox(uses_field.slot, from_=0, to=1000, width=6,
                    textvariable=self.uses_var).pack(fill="x")

        age_field = Field(row, "Duración", bg=C.CARD)
        age_field.pack(side="left", padx=(0, 12))
        self.age_var = tk.StringVar(value=INVITE_MAX_AGES[0][1])
        ttk.Combobox(age_field.slot, values=[label for _v, label in INVITE_MAX_AGES],
                     state="readonly", width=14, textvariable=self.age_var).pack(fill="x")

        self.temp_var = tk.BooleanVar(value=False)
        temp = Checkbox(row, "Solo miembros nuevos", variable=self.temp_var,
                        bg=C.CARD, font=app.theme.font(9))
        temp.pack(side="left", padx=(0, 12), pady=(14, 0))

        self.create_button = ttk.Button(row, text="Crear invitación", style="Accent.TButton",
                                        command=self._create)
        self.create_button.pack(side="right", pady=(12, 0))
        if not self._can_create:
            self.create_button.configure(state="disabled")

        toolbar = tk.Frame(self, bg=C.CONTENT)
        toolbar.pack(fill="x", padx=28, pady=(4, 6))
        self.count_label = tk.Label(toolbar, text="", bg=C.CONTENT, fg=C.MUTED,
                                    font=app.theme.font(9))
        self.count_label.pack(side="left")
        self.delete_button = ttk.Button(toolbar, text="Revocar invitación",
                                        style="SmallDanger.TButton", command=self._delete)
        self.delete_button.pack(side="right")
        self.copy_button = ttk.Button(toolbar, text="Copiar enlace", style="Small.TButton",
                                      command=self._copy)
        self.copy_button.pack(side="right", padx=(0, 6))

        columns = [TableColumn("code", "Código", 210, stretch=True),
                   TableColumn("channel", "Canal", 150),
                   TableColumn("creator", "Creador", 160),
                   TableColumn("uses", "Usos", 80, anchor="center"),
                   TableColumn("expires", "Expira", 150),
                   TableColumn("created", "Creada", 140)]
        self.table = Table(self, columns, height=14, theme=app.theme, multi=True,
                           empty_text="No hay invitaciones activas.")
        self.table.pack(fill="both", expand=True, padx=28, pady=(0, 20))
        self.table.tree.bind("<Double-1>", self._open_detail)
        self._invites: list[Invite] = []

    def _open_detail(self, event: tk.Event) -> None:
        row_id = self.table.tree.identify_row(event.y)
        if not row_id:
            return
        row = next((item for item in self.table._rows
                    if str(item.get("_id")) == row_id), None)
        if row is None or row.get("_invite") is None:
            return
        InviteDetailWindow(self, self.app, row["_invite"])

    def _text_channels(self) -> list[str]:
        return [f"#{c.display_name}" for c in self.app.channels if c.is_text]

    def refresh(self) -> None:
        if self.channel_combo["values"]:
            if not self.channel_var.get():
                self.channel_var.set(self.channel_combo["values"][0])
        client = self.app.client
        guild_id = self.app.guild.id
        self.run(lambda: client.list_guild_invites(guild_id), self._done)

    def _done(self, invites: list[Invite]) -> None:
        self._invites = invites
        rows = [{
            "_id": invite.code,
            "code": invite.code,
            "channel": f"#{invite.channel_name}" if invite.channel_name else "—",
            "creator": invite.inviter.display_name if invite.inviter else "—",
            "uses": invite.uses_label,
            "expires": invite.expires_label,
            "created": fmt_datetime(invite.created_at),
            "_raw": {"uses": invite.uses, "created": invite.created_at},
            "_invite": invite,
        } for invite in invites]
        self.table.set_rows(rows)
        self.count_label.configure(text=f"{len(invites)} invitaciones")

    def _channel_id(self) -> str:
        label = self.channel_var.get()
        channel = next((c for c in self.app.channels if c.is_text and f"#{c.display_name}" == label),
                       None)
        return channel.id if channel else ""

    def _create(self) -> None:
        if not self.require("CREATE_INSTANT_INVITE", "crear invitaciones"):
            return
        channel_id = self._channel_id()
        if not channel_id:
            self.toast_warn("Elige un canal de texto.")
            return
        max_uses = safe_int(self.uses_var.get(), 0)
        max_age = next((value for value, label in INVITE_MAX_AGES
                        if label == self.age_var.get()), 86400)
        temporary = bool(self.temp_var.get())
        client = self.app.client

        def done(invite: Invite) -> None:
            self.app.toasts.show(f"Invitación creada: discord.gg/{invite.code}", "success")
            self.refresh()

        self.run(lambda: client.create_invite(channel_id, max_age, max_uses, temporary), done)

    def _selected(self) -> Invite | None:
        rows = self.table.selected_rows()
        return rows[0].get("_invite") if rows else None

    def _copy(self) -> None:
        invite = self._selected()
        if invite is None:
            self.toast_warn("Selecciona una invitación.")
            return
        if not self.require("CREATE_INSTANT_INVITE", "compartir invitaciones"):
            return
        url = f"https://discord.gg/{invite.code}"
        copy_to_clipboard(self, url)
        self.toast_ok(f"Enlace copiado: {url}")

    def _delete(self) -> None:
        rows = self.table.selected_rows()
        if not rows:
            self.toast_warn("Selecciona una invitación.")
            return
        if not self.require("MANAGE_GUILD", "revocar invitaciones"):
            return
        codes = [str(row["_id"]) for row in rows]
        dialog = ConfirmDialog(self, "Revocar invitaciones",
                               f"Se revocarán {len(codes)} enlaces. Quien los tenga no podrá "
                               "usarlos.", confirm_text="Revocar", danger=True,
                               theme=self.app.theme)
        if not dialog.show():
            return
        client = self.app.client

        def work() -> int:
            for code in codes:
                client.delete_invite(code)
            return len(codes)

        def done(count: int) -> None:
            self.app.toasts.show(f"{count} invitaciones revocadas.", "success")
            self.refresh()

        self.run(work, done)


class InviteDetailWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc, app: Any, invite: Invite):
        super().__init__(parent)
        self.app = app
        self.invite = invite
        self.title(f"Invitación {invite.code}")
        self.geometry("560x430")
        self.configure(bg=C.CONTENT)
        self.transient(parent.winfo_toplevel())
        self._build()

    def _build(self) -> None:
        tk.Label(self, text=f"Invitación discord.gg/{self.invite.code}",
                 bg=C.CONTENT, fg=C.TEXT, font=self.app.theme.font(13, "bold"),
                 anchor="w").pack(fill="x", padx=18, pady=(16, 4))
        card = Card(self, padding=14)
        card.pack(fill="x", padx=18, pady=(4, 8))
        for label, value in (
                ("Canal", f"#{self.invite.channel_name}" if self.invite.channel_name else "—"),
                ("Creador", self.invite.inviter.display_name
                 if self.invite.inviter else "—"),
                ("Creada", fmt_datetime(self.invite.created_at)),
                ("Expira", self.invite.expires_label),
                ("Usos", self.invite.uses_label),
                ("Solo miembros nuevos", "Sí" if self.invite.temporary else "No")):
            row = tk.Frame(card.body, bg=C.CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, bg=C.CARD, fg=C.MUTED,
                     font=self.app.theme.font(9), width=20, anchor="w").pack(side="left")
            tk.Label(row, text=value, bg=C.CARD, fg=C.TEXT,
                     font=self.app.theme.font(9), anchor="w").pack(
                side="left", fill="x", expand=True)
        tk.Label(self,
                 text="Discord no expone la lista nominal de usuarios que usaron "
                      "una invitación. Solo informa el número de usos.",
                 bg=C.CARD_ALT, fg=C.MUTED, font=self.app.theme.font(8),
                 anchor="w", justify="left", wraplength=500).pack(
            fill="x", padx=18, pady=(4, 8))
        actions = tk.Frame(self, bg=C.CONTENT)
        actions.pack(fill="x", padx=18, pady=(0, 14))
        ttk.Button(actions, text="Copiar enlace", style="SmallAccent.TButton",
                   command=self._copy).pack(side="left")
        ttk.Button(actions, text="Cerrar", style="Small.TButton",
                   command=self.destroy).pack(side="right")

    def _copy(self) -> None:
        url = f"https://discord.gg/{self.invite.code}"
        copy_to_clipboard(self, url)
        self.app.toasts.show(f"Enlace copiado: {url}", "success")
