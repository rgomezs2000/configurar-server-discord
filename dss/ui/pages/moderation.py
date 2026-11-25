"""Moderación: sanciones, registro de auditoría y limpieza de mensajes."""
from __future__ import annotations

import json
import queue
import tkinter as tk
from tkinter import ttk
from typing import Any

from ...constants import (AUDIT_CATEGORIES, DELETE_MESSAGE_WINDOWS, audit_action_category)
from ...gateway import DiscordGateway
from ...models import (AuditEntry, Ban, Message, fmt_date, fmt_datetime)
from ..emoji_picker import EmojiPicker
from ..theme import C
from ..widgets import (Card, ConfirmDialog, EmptyState, Field, Modal, PageHeader,
                       SearchEntry, Table, TableColumn, TabBar, labeled_entry)
from .base import Page
from .modals import BanModal
from .moderation_extra import AudioTab, ForumsTab
from ..voice_process import VoiceProcess


class ModerationPage(Page):
    key = "moderation"
    label = "Moderación"
    glyph = "⊘"

    def build(self) -> None:
        app = self.app
        self.header = PageHeader(self, app, "Moderación",
                                 "Sanciones, historial de acciones y limpieza de mensajes.")
        self.header.pack(fill="x", padx=28, pady=(22, 0))
        self.header.button("Actualizar", lambda: self._switch(self._current, force=True))

        self._frames: dict[str, Any] = {}
        self._current = "bans"
        self.gateway: DiscordGateway | None = None
        self.gateway_status = "off"
        self.voice_process = VoiceProcess()
        self.voice_states: dict[str, dict[str, list[dict]]] = {}
        self.voice_joined_channel: str | None = None
        self.voice_recording = False
        self.voice_last_recording: str | None = None
        self._voice_poll_after: str | None = None
        self._gateway_after: str | None = None
        self.tabbar = TabBar(
            self, [("bans", "Sanciones"), ("audit", "Registro de auditoría"),
                   ("messages", "Mensajes"), ("audio", "Audios"),
                   ("audience", "Audiencia"), ("forums", "Foros")],
            on_change=self._switch, theme=app.theme)
        self.tabbar.pack(fill="x", padx=28, pady=(10, 0))
        self.container = tk.Frame(self, bg=C.CONTENT)
        self.container.pack(fill="both", expand=True, padx=28, pady=(10, 20))

        self._frames["bans"] = BansTab(self.container, app, self)
        self._frames["audit"] = AuditTab(self.container, app, self)
        self._frames["messages"] = MessagesTab(self.container, app, self)
        self._frames["audio"] = AudioTab(self.container, app, self)
        self._frames["audience"] = AudioTab(self.container, app, self, stage=True)
        self._frames["forums"] = ForumsTab(self.container, app, self)
        self.tabbar.select("bans")

    def _switch(self, key: str, force: bool = False) -> None:
        if not self._frames:
            return
        frame = self._frames.get(key)
        if frame is None:
            return
        self._current = key
        for other in self._frames.values():
            other.pack_forget()
        frame.pack(fill="both", expand=True)
        if force or not frame.loaded:
            frame.load()

    def refresh(self) -> None:
        self._switch(self._current, force=True)

    def on_guild_refreshed(self) -> None:
        for frame in self._frames.values():
            frame.loaded = False

    def ensure_gateway(self) -> None:
        if self.gateway is not None or self.app.session_kind == "demo":
            return
        token = getattr(self.app, "bot_token", "") or getattr(
            self.app.client, "token", "")
        if not token:
            self.gateway_status = "sin token"
            return
        self.gateway = DiscordGateway(token)
        self.gateway.start()
        self.gateway_status = "conectando"
        self._poll_gateway()

    def start_voice_poll(self) -> None:
        if self._voice_poll_after is not None:
            return
        self._poll_voice_events()

    def _poll_voice_events(self) -> None:
        while True:
            try:
                event = self.voice_process.events.get_nowait()
            except queue.Empty:
                break
            name = event.get("event")
            if name == "joined":
                self.voice_joined_channel = str(event.get("channel_id") or "")
                self.voice_recording = False
            elif name == "left":
                self.voice_joined_channel = None
                self.voice_recording = False
            elif name == "recording":
                self.voice_recording = True
            elif name == "recorded":
                self.voice_recording = False
                self.voice_last_recording = str(event.get("file") or "")
            elif name == "exit":
                self.voice_joined_channel = None
                self.voice_recording = False
            for key in ("audio", "audience"):
                frame = self._frames.get(key)
                if frame is not None and frame.loaded:
                    frame.handle_voice_event(event)
        self._voice_poll_after = self.after(400, self._poll_voice_events)

    def _poll_gateway(self) -> None:
        if self.gateway is not None:
            while True:
                try:
                    event, data = self.gateway.events.get_nowait()
                except queue.Empty:
                    break
                if event == "status":
                    self.gateway_status = self.gateway.status if self.gateway else "off"
                elif event == "GUILD_CREATE":
                    self._set_voice_states(str(data.get("id")),
                                           data.get("voice_states") or [])
                elif event == "VOICE_STATE_UPDATE":
                    self._apply_voice_state(data)
        for key in ("audio", "audience"):
            frame = self._frames.get(key)
            if frame is not None and frame.loaded:
                frame._render()
        self._gateway_after = self.after(500, self._poll_gateway)

    def _set_voice_states(self, guild_id: str, states: list[dict]) -> None:
        by_channel: dict[str, list[dict]] = {}
        for state in states:
            channel_id = str(state.get("channel_id") or "")
            if not channel_id:
                continue
            member = state.get("member") or {}
            user = member.get("user") or {}
            by_channel.setdefault(channel_id, []).append({
                "id": str(state.get("user_id") or ""),
                "name": user.get("global_name") or user.get("username") or "Miembro",
                "mute": bool(state.get("mute")),
                "deaf": bool(state.get("deaf")),
                "suppress": bool(state.get("suppress")),
            })
        self.voice_states[guild_id] = by_channel

    def _apply_voice_state(self, state: dict) -> None:
        user_id = str(state.get("user_id") or "")
        guild_id = str(state.get("guild_id") or self.app.guild.id)
        if not user_id:
            return
        by_channel = self.voice_states.setdefault(guild_id, {})
        for users in by_channel.values():
            users[:] = [user for user in users if user.get("id") != user_id]
        channel_id = str(state.get("channel_id") or "")
        if not channel_id:
            return
        member = state.get("member") or {}
        user = member.get("user") or {}
        by_channel.setdefault(channel_id, []).append({
            "id": user_id,
            "name": user.get("global_name") or user.get("username") or "Miembro",
            "mute": bool(state.get("mute")),
            "deaf": bool(state.get("deaf")),
            "suppress": bool(state.get("suppress")),
        })


# --------------------------------------------------------------------------- #
# Sanciones
# --------------------------------------------------------------------------- #

class BansTab(tk.Frame):
    def __init__(self, master: tk.Misc, app: Any, page: ModerationPage):
        super().__init__(master, bg=C.CONTENT)
        self.app = app
        self.page = page
        self.loaded = False
        self._bans: list[Ban] = []
        can_ban = app.can("BAN_MEMBERS")

        toolbar = tk.Frame(self, bg=C.CONTENT)
        toolbar.pack(fill="x", pady=(0, 8))
        self.search = SearchEntry(toolbar, placeholder="Filtrar por usuario, ID o motivo…",
                                  on_change=lambda _t: self._render(), width=34,
                                  bg=C.CONTENT, theme=app.theme)
        self.search.pack(side="left")
        self.count_label = tk.Label(toolbar, text="", bg=C.CONTENT, fg=C.MUTED,
                                    font=app.theme.font(9))
        self.count_label.pack(side="left", padx=(12, 0))
        self.unban_button = ttk.Button(toolbar, text="Quitar baneo", style="SmallDanger.TButton",
                                       command=self._unban)
        self.unban_button.pack(side="right")
        self.ban_button = ttk.Button(toolbar, text="Banear usuario", style="Accent.TButton",
                                     command=self._ban)
        self.ban_button.pack(side="right", padx=(0, 8))
        if not can_ban:
            self.ban_button.configure(state="disabled")
            self.unban_button.configure(state="disabled")
            tk.Label(self, text="Solo lectura: falta el permiso «Banear miembros».",
                     bg=C.YELLOW_SOFT, fg="#ffd98a", font=app.theme.font(8),
                     anchor="w", padx=10, pady=5).pack(fill="x", pady=(0, 8))

        columns = [TableColumn("user", "Usuario", 220, stretch=True),
                   TableColumn("id", "ID", 190),
                   TableColumn("reason", "Motivo", 340, stretch=True)]
        self.table = Table(self, columns, height=16, theme=app.theme,
                           empty_text="No hay usuarios baneados.")
        self.table.pack(fill="both", expand=True)

    def load(self) -> None:
        self.loaded = True
        client = self.app.client
        guild_id = self.app.guild.id
        self.page.run(lambda: client.list_bans(guild_id, limit=1000), self._done,
                      self._failed)

    def _done(self, bans: list[Ban]) -> None:
        self._bans = bans
        self._render()

    def _failed(self, error: BaseException) -> None:
        self.loaded = False
        self.page.error(error)

    def _render(self) -> None:
        needle = self.search.value().lower()
        bans = [ban for ban in self._bans
                if not needle
                or needle in ban.user.display_name.lower()
                or needle in ban.user.username.lower()
                or needle in ban.user.id
                or needle in (ban.reason or "").lower()]
        rows = [{
            "_id": ban.user.id,
            "user": ban.user.display_name + (" (bot)" if ban.user.bot else ""),
            "id": ban.user.id,
            "reason": ban.reason or "—",
            "_raw": {"user": ban.user.display_name, "reason": ban.reason or ""},
        } for ban in bans]
        self.table.set_rows(rows)
        self.count_label.configure(text=f"{len(bans)} sanciones")

    def _ban(self) -> None:
        BanModal(self, self.app, on_done=self.load).show()

    def _unban(self) -> None:
        rows = self.table.selected_rows()
        if not rows:
            self.page.toast_warn("Selecciona un baneo de la tabla.")
            return
        names = ", ".join(str(row["user"]) for row in rows[:3])
        dialog = ConfirmDialog(self, "Quitar baneo",
                               f"Se permitirá volver a entrar a: {names}.",
                               confirm_text="Quitar baneo", theme=self.app.theme)
        if not dialog.show():
            return
        client = self.app.client
        guild_id = self.app.guild.id

        def work() -> int:
            for row in rows:
                client.unban_member(guild_id, str(row["_id"]))
            return len(rows)

        def done(count: int) -> None:
            self.app.toasts.show(f"{count} baneos retirados.", "success")
            self.load()

        self.page.run(work, done)


# --------------------------------------------------------------------------- #
# Registro de auditoría
# --------------------------------------------------------------------------- #

class AuditTab(tk.Frame):
    def __init__(self, master: tk.Misc, app: Any, page: ModerationPage):
        super().__init__(master, bg=C.CONTENT)
        self.app = app
        self.page = page
        self.loaded = False
        self._entries: list[AuditEntry] = []
        self._has_more = False

        toolbar = tk.Frame(self, bg=C.CONTENT)
        toolbar.pack(fill="x", pady=(0, 8))
        self.category_var = tk.StringVar(value="Todas")
        category = ttk.Combobox(toolbar, values=AUDIT_CATEGORIES, state="readonly",
                                width=16, textvariable=self.category_var)
        category.pack(side="left")
        category.bind("<<ComboboxSelected>>", lambda _e: self._render())
        tk.Label(toolbar, text="Moderador (ID):", bg=C.CONTENT, fg=C.FAINT,
                 font=app.theme.font(8)).pack(side="left", padx=(12, 4))
        self.user_var = tk.StringVar()
        user_entry = ttk.Entry(toolbar, textvariable=self.user_var, width=18)
        user_entry.pack(side="left")
        user_entry.bind("<Return>", lambda _e: self.load())
        self.count_label = tk.Label(toolbar, text="", bg=C.CONTENT, fg=C.MUTED,
                                    font=app.theme.font(9))
        self.count_label.pack(side="left", padx=(12, 0))
        self.more_button = ttk.Button(toolbar, text="Cargar más", style="Small.TButton",
                                      command=self._more)
        self.more_button.pack(side="right")
        self.more_button.configure(state="disabled")

        columns = [TableColumn("date", "Fecha", 140),
                   TableColumn("action", "Acción", 220, stretch=True),
                   TableColumn("actor", "Moderador", 150),
                   TableColumn("target", "Objetivo", 170),
                   TableColumn("reason", "Motivo", 240, stretch=True)]
        self.table = Table(self, columns, height=16, theme=app.theme,
                           on_double=self._details, multi=False,
                           empty_text="No hay acciones registradas.")
        self.table.pack(fill="both", expand=True)

    def load(self) -> None:
        self.loaded = True
        self._entries = []
        self._fetch(before=None)

    def _fetch(self, before: str | None) -> None:
        client = self.app.client
        guild_id = self.app.guild.id
        action_user = self.user_var.get().strip() or None

        def work() -> list[AuditEntry]:
            return client.list_audit_logs(guild_id, limit=50, before=before,
                                          user_id=action_user)

        def done(entries: list[AuditEntry]) -> None:
            if before is None:
                self._entries = entries
            else:
                known = {entry.id for entry in self._entries}
                self._entries.extend(e for e in entries if e.id not in known)
            self._has_more = len(entries) == 50
            self.more_button.configure(state="normal" if self._has_more else "disabled")
            self._render()

        def failed(error: BaseException) -> None:
            self.loaded = False
            self.page.error(error)

        self.page.run(work, done, failed)

    def _more(self) -> None:
        if not self._entries:
            return
        self._fetch(before=self._entries[-1].id)

    def _render(self) -> None:
        category = self.category_var.get()
        entries = [entry for entry in self._entries
                   if category == "Todas" or audit_action_category(entry.action_type) == category]
        rows = []
        for entry in entries:
            actor = entry.actor.display_name if entry.actor else "Sistema"
            target = ""
            if entry.target:
                target = entry.target.display_name
            elif entry.target_id:
                target = str(entry.target_id)
            rows.append({
                "_id": entry.id,
                "date": fmt_datetime(entry.created_at),
                "action": entry.action_label,
                "actor": actor,
                "target": target or "—",
                "reason": entry.reason or "—",
                "_raw": {"date": entry.created_at, "action": entry.action_label},
                "_entry": entry,
            })
        self.table.set_rows(rows)
        total = len(self._entries)
        self.count_label.configure(text=f"{len(entries)} de {total} acciones")

    def _details(self, row: dict) -> None:
        entry: AuditEntry = row["_entry"]
        modal = Modal(self, "Detalle de la acción", width=560, theme=self.app.theme,
                      subtitle=entry.action_label)
        meta = tk.Frame(modal.body, bg=C.CARD)
        meta.pack(fill="x")
        for key, value in (("ID", entry.id),
                           ("Fecha", fmt_datetime(entry.created_at)),
                           ("Moderador", entry.actor.display_name if entry.actor else "Sistema"),
                           ("Objetivo", str(entry.target_id or "—")),
                           ("Motivo", entry.reason or "—")):
            tk.Label(meta, text=f"{key}: {value}", bg=C.CARD, fg=C.DIM,
                     font=self.app.theme.font(9), anchor="w").pack(fill="x")
        if entry.changes or entry.options:
            text = tk.Text(modal.body, height=10, bg=C.INPUT, fg=C.TEXT, bd=0,
                           highlightthickness=1, highlightbackground=C.BORDER,
                           font=(self.app.theme.mono_family, 8), wrap="none",
                           padx=8, pady=6)
            text.pack(fill="both", expand=True, pady=(10, 0))
            payload = {"changes": entry.changes, "options": entry.options}
            text.insert("1.0", json.dumps(payload, indent=2, ensure_ascii=False, default=str))
            text.configure(state="disabled")
        modal.add_button("Cerrar", modal.close)
        modal.show()


# --------------------------------------------------------------------------- #
# Mensajes
# --------------------------------------------------------------------------- #

class MessagesTab(tk.Frame):
    def __init__(self, master: tk.Misc, app: Any, page: ModerationPage):
        super().__init__(master, bg=C.CONTENT)
        self.app = app
        self.page = page
        self.loaded = False
        self._messages: list[Message] = []
        self._channel_id = ""
        self._forced_channel: Any = None
        self.can_manage = app.can("MANAGE_MESSAGES")
        self.can_send = app.can("SEND_MESSAGES")

        toolbar = tk.Frame(self, bg=C.CONTENT)
        toolbar.pack(fill="x", pady=(0, 8))
        self.channel_var = tk.StringVar()
        self.channel_combo = ttk.Combobox(toolbar, values=self._channel_values(),
                                          state="readonly", width=24,
                                          textvariable=self.channel_var)
        self.channel_combo.pack(side="left")
        self.channel_combo.bind("<<ComboboxSelected>>", lambda _e: self.load())
        self.count_label = tk.Label(toolbar, text="", bg=C.CONTENT, fg=C.MUTED,
                                    font=app.theme.font(9))
        self.count_label.pack(side="left", padx=(12, 0))
        ttk.Button(toolbar, text="Actualizar", style="Small.TButton",
                   command=self.load).pack(side="right")
        self.delete_button = ttk.Button(toolbar, text="Eliminar seleccionados",
                                        style="SmallDanger.TButton", command=self._purge)
        self.delete_button.pack(side="right", padx=(0, 6))
        self.pin_button = ttk.Button(toolbar, text="Fijar", style="Small.TButton",
                                     command=self._toggle_pin)
        self.pin_button.pack(side="right", padx=(0, 6))
        if not self.can_manage:
            self.pin_button.configure(state="disabled")
        if not self.can_manage:
            self.delete_button.configure(state="disabled")

        columns = [TableColumn("author", "Autor", 140),
                   TableColumn("content", "Mensaje", 380, stretch=True),
                   TableColumn("attachments", "Adjuntos", 240, stretch=True),
                   TableColumn("date", "Enviado", 130),
                   TableColumn("pinned", "Fijado", 60, anchor="center")]
        self.table = Table(self, columns, height=15, theme=app.theme, multi=True,
                           empty_text="Carga los mensajes de un canal para verlos aquí.")
        self.table.pack(fill="both", expand=True)
        self.table.tree.bind("<<TreeviewSelect>>",
                             lambda _e: self._update_pin_button())

        tk.Label(self, text="Los mensajes se envían como el bot, no como tu cuenta.",
                 bg=C.CARD, fg=C.FAINT, font=self.app.theme.font(8),
                 anchor="w").pack(fill="x", pady=(6, 0))
        composer = tk.Frame(self, bg=C.CARD, highlightbackground=C.BORDER_SOFT,
                            highlightthickness=1)
        composer.pack(fill="x", pady=(10, 0))
        self.composer_var = tk.StringVar()
        self.composer = ttk.Entry(composer, textvariable=self.composer_var)
        self.composer.pack(side="left", fill="x", expand=True, padx=10, pady=8)
        self.composer.bind("<Return>", lambda _e: self._send())
        self.send_button = ttk.Button(composer, text="Enviar mensaje", style="SmallAccent.TButton",
                                      command=self._send)
        self.send_button.pack(side="right", padx=8)
        self.emoji_button = ttk.Button(composer, text="Emoji", style="Small.TButton",
                                       command=self._open_emoji_picker)
        self.emoji_button.pack(side="right", padx=(0, 6))
        if not self.can_send:
            self.composer.configure(state="readonly")
            self.send_button.configure(state="disabled")

    def _open_emoji_picker(self) -> None:
        EmojiPicker(self, self.app, self.emoji_button, self._insert_emoji)

    def _insert_emoji(self, text: str) -> None:
        try:
            self.composer.insert("insert", text)
            self.composer.icursor("end")
        except tk.TclError:
            pass

    def _channel_values(self) -> list[str]:
        values = []
        for channel in self.app.channels:
            if channel.is_text:
                values.append(f"#{channel.display_name}")
        return values

    def _channels(self) -> list[Any]:
        return [c for c in self.app.channels if c.is_text]

    def load(self) -> None:
        self.loaded = True
        if self._forced_channel is not None:
            channel = self._forced_channel
            self.channel_var.set(f"#{channel.display_name}")
            self._channel_id = channel.id
            client = self.app.client

            def done_forced(messages: list[Message]) -> None:
                self._messages = messages
                self._render()

            self.page.run(lambda: client.list_messages(channel.id, limit=50),
                          done_forced, lambda error: self.page.error(error))
            return
        channels = self._channels()
        if not channels:
            self.table.set_rows([])
            return
        label = self.channel_var.get()
        channel = next((c for c in channels if f"#{c.display_name}" == label), channels[0])
        self.channel_var.set(f"#{channel.display_name}")
        self._channel_id = channel.id
        client = self.app.client

        def done(messages: list[Message]) -> None:
            self._messages = messages
            self._render()

        self.page.run(lambda: client.list_messages(channel.id, limit=50), done,
                      lambda error: self.page.error(error))

    def show_channel(self, channel: Any) -> None:
        self._forced_channel = channel
        self.load()

    def _update_pin_button(self) -> None:
        rows = self.table.selected_rows()
        pinned = bool(rows) and all(
            bool((row.get("_message") and row["_message"].pinned)) for row in rows)
        if hasattr(self, "pin_button"):
            self.pin_button.configure(text="Desfijar" if pinned else "Fijar")

    def _toggle_pin(self) -> None:
        rows = self.table.selected_rows()
        if not rows:
            self.page.toast_warn("Selecciona un mensaje.")
            return
        pinned = not all(
            bool((row.get("_message") and row["_message"].pinned)) for row in rows)
        self._pin(pinned)

    def _render(self) -> None:
        rows = []
        for message in self._messages:
            rows.append({
                "_id": message.id,
                "author": message.author.display_name,
                "content": message.preview,
                "attachments": ", ".join(a.filename for a in message.attachments) or "—",
                "date": fmt_datetime(message.timestamp),
                "pinned": "sí" if message.pinned else "",
                "_tags": ("warning",) if message.pinned else (),
                "_raw": {"date": message.timestamp, "author": message.author.display_name},
                "_message": message,
            })
        self.table.set_rows(rows)
        self.count_label.configure(text=f"{len(rows)} mensajes recientes")
        self._update_pin_button()

    def _purge(self) -> None:
        ids = self.table.selected_ids()
        if not ids:
            self.page.toast_warn("Selecciona los mensajes que quieres eliminar.")
            return
        dialog = ConfirmDialog(self, "Eliminar mensajes",
                               f"Se eliminarán {len(ids)} mensajes del canal. "
                               "Los mensajes de más de 14 días se borran uno a uno.",
                               confirm_text="Eliminar mensajes", danger=True,
                               theme=self.app.theme)
        if not dialog.show():
            return
        client = self.app.client
        channel_id = self._channel_id

        def done(result: tuple[int, int]) -> None:
            deleted, failed = result
            message = f"{deleted} mensajes eliminados."
            if failed:
                message += f" {failed} no se pudieron borrar."
            self.app.toasts.show(message, "success" if not failed else "warning")
            self.load()

        self.page.run(lambda: client.purge_messages(channel_id, ids), done)

    def _pin(self, pinned: bool) -> None:
        if not self.page.require("MANAGE_MESSAGES", "fijar mensajes"):
            return
        ids = self.table.selected_ids()
        if not ids:
            self.page.toast_warn("Selecciona un mensaje.")
            return
        client = self.app.client
        channel_id = self._channel_id

        def work() -> int:
            for message_id in ids:
                if pinned:
                    client.pin_message(channel_id, message_id)
                else:
                    client.unpin_message(channel_id, message_id)
            return len(ids)

        def done(count: int) -> None:
            self.app.toasts.show(f"{count} mensajes {'fijados' if pinned else 'desfijados'}.",
                                 "success")
            self.load()

        self.page.run(work, done)

    def _send(self) -> None:
        content = self.composer_var.get().strip()
        if not content:
            return
        if not self.can_send:
            self.page.toast_warn("Falta el permiso «Enviar mensajes».")
            return
        client = self.app.client
        channel_id = self._channel_id

        def done(_message: Message) -> None:
            self.composer_var.set("")
            self.load()

        self.page.run(lambda: client.send_message(channel_id, content), done)
