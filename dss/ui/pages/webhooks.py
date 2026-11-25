"""Webhooks del servidor: crear, copiar URL y eliminar."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from ...models import Webhook
from ..theme import C
from ..widgets import (ConfirmDialog, Field, Modal, PageHeader, Table, TableColumn,
                       copy_to_clipboard)
from .base import Page


class WebhooksPage(Page):
    key = "webhooks"
    label = "Webhooks"
    glyph = "⇢"

    def build(self) -> None:
        app = self.app
        self.header = PageHeader(self, app, "Webhooks",
                                 "Canales de salida para integrar otros servicios.")
        self.header.pack(fill="x", padx=28, pady=(22, 0))
        self._manage = app.can("MANAGE_WEBHOOKS")
        self.create_button = self.header.button("Crear webhook", self._create,
                                                style="Accent.TButton")
        self.header.button("Actualizar", self.refresh)
        if not self._manage:
            self.create_button.configure(state="disabled")
            tk.Label(self, text="Solo lectura: falta el permiso «Gestionar webhooks».",
                     bg=C.YELLOW_SOFT, fg="#ffd98a", font=app.theme.font(8),
                     anchor="w", padx=10, pady=5).pack(fill="x", padx=28, pady=(10, 0))

        toolbar = tk.Frame(self, bg=C.CONTENT)
        toolbar.pack(fill="x", padx=28, pady=(12, 6))
        self.count_label = tk.Label(toolbar, text="", bg=C.CONTENT, fg=C.MUTED,
                                    font=app.theme.font(9))
        self.count_label.pack(side="left")
        self.delete_button = ttk.Button(toolbar, text="Eliminar", style="SmallDanger.TButton",
                                        command=self._delete)
        self.delete_button.pack(side="right")
        self.copy_button = ttk.Button(toolbar, text="Copiar URL", style="Small.TButton",
                                      command=self._copy)
        self.copy_button.pack(side="right", padx=(0, 6))
        if not self._manage:
            self.delete_button.configure(state="disabled")

        columns = [TableColumn("name", "Nombre", 240, stretch=True),
                   TableColumn("channel", "Canal", 180),
                   TableColumn("id", "ID", 200),
                   TableColumn("url", "URL", 120, anchor="center")]
        self.table = Table(self, columns, height=14, theme=app.theme, multi=False,
                           empty_text="No hay webhooks en este servidor.")
        self.table.pack(fill="both", expand=True, padx=28, pady=(0, 20))
        self._webhooks: list[Webhook] = []

    def refresh(self) -> None:
        client = self.app.client
        guild_id = self.app.guild.id
        self.run(lambda: client.list_webhooks(guild_id), self._done)

    def _done(self, webhooks: list[Webhook]) -> None:
        self._webhooks = webhooks
        channel_names = {c.id: c.display_name for c in self.app.channels}
        rows = [{
            "_id": webhook.id,
            "name": webhook.name,
            "channel": f"#{channel_names.get(webhook.channel_id, '—')}",
            "id": webhook.id,
            "url": "disponible" if webhook.token else "obtener",
            "_raw": {"name": webhook.name},
            "_webhook": webhook,
        } for webhook in webhooks]
        self.table.set_rows(rows)
        self.count_label.configure(text=f"{len(webhooks)} webhooks")

    def _selected(self) -> Webhook | None:
        rows = self.table.selected_rows()
        return rows[0].get("_webhook") if rows else None

    def _create(self) -> None:
        if not self.require("MANAGE_WEBHOOKS", "crear webhooks"):
            return
        WebhookCreateModal(self, self.app, self).show()

    def _copy(self) -> None:
        webhook = self._selected()
        if webhook is None:
            self.toast_warn("Selecciona un webhook.")
            return
        if webhook.token:
            self._copy_url(webhook.url)
            return
        client = self.app.client

        def done(full: Webhook) -> None:
            self._copy_url(full.url)

        self.run(lambda: client.get_webhook(webhook.id), done)

    def _copy_url(self, url: str) -> None:
        if not url:
            self.toast_warn("Discord no devolvió una URL para este webhook.")
            return
        copy_to_clipboard(self, url)
        self.toast_ok("URL del webhook copiada.")

    def _delete(self) -> None:
        webhook = self._selected()
        if webhook is None:
            self.toast_warn("Selecciona un webhook.")
            return
        if not self.require("MANAGE_WEBHOOKS", "eliminar webhooks"):
            return
        dialog = ConfirmDialog(self, "Eliminar webhook",
                               f"Se eliminará «{webhook.name}». Los servicios que lo usen "
                               "dejarán de funcionar.", confirm_text="Eliminar", danger=True,
                               theme=self.app.theme)
        if not dialog.show():
            return
        client = self.app.client

        def done(_result: Any) -> None:
            self.app.toasts.show("Webhook eliminado.", "success")
            self.refresh()

        self.run(lambda: client.delete_webhook(webhook.id), done)


class WebhookCreateModal(Modal):
    def __init__(self, parent: tk.Misc, app: Any, page: WebhooksPage):
        super().__init__(parent, "Crear webhook", width=500, theme=app.theme,
                         subtitle="El webhook pertenece a un canal de texto.")
        self.app = app
        self.page = page

        name_field = Field(self.body, "Nombre", bg=C.CARD)
        name_field.pack(fill="x", pady=(0, 12))
        self.name_var = tk.StringVar(value="Nuevo webhook")
        entry = ttk.Entry(name_field.slot, textvariable=self.name_var)
        name_field.add(entry)
        entry.focus_set()

        channel_field = Field(self.body, "Canal", bg=C.CARD)
        channel_field.pack(fill="x")
        self.channel_var = tk.StringVar()
        channels = [c for c in app.channels if c.is_text]
        self._channels = {f"#{c.display_name}": c.id for c in channels}
        combo = ttk.Combobox(channel_field.slot, values=list(self._channels),
                             state="readonly", textvariable=self.channel_var)
        if self._channels:
            self.channel_var.set(next(iter(self._channels)))
        channel_field.add(combo)

        self.add_button("Cancelar", self.close)
        self.add_button("Crear webhook", self._submit, style="Accent.TButton")

    def _submit(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            self.show_error("Ponle un nombre al webhook.")
            return
        channel_id = self._channels.get(self.channel_var.get())
        if not channel_id:
            self.show_error("Elige un canal de texto.")
            return
        client = self.app.client
        self.set_busy(True)

        def done(_result: Any) -> None:
            self.app.toasts.show("Webhook creado.", "success")
            self.close()
            self.page.refresh()

        def failed(error: BaseException) -> None:
            self.set_busy(False)
            self.show_error(str(error))

        self.app.run_task(lambda: client.create_webhook(channel_id, name), done, failed)
