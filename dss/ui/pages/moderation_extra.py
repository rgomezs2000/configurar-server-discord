"""Pestañas de audios, audiencia y foros para Moderación."""
from __future__ import annotations

import queue
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any

from ...gateway import DiscordGateway
from ...models import Channel, Message, fmt_datetime
from ..theme import C
from ..voice_process import voice_dependencies_available, voice_missing_dependencies
from ..widgets import ConfirmDialog, Table, TableColumn


class AudioTab(tk.Frame):
    def __init__(self, master: tk.Misc, app: Any, page: Any, stage: bool = False):
        super().__init__(master, bg=C.CONTENT)
        self.app = app
        self.page = page
        self.stage = stage
        self.loaded = False
        self.joined = False
        self.recording = False
        self.last_recording: str | None = None
        self._can_move = app.can("MOVE_MEMBERS")
        self._can_mute = app.can("MUTE_MEMBERS")
        self._can_deafen = app.can("DEAFEN_MEMBERS")
        toolbar = tk.Frame(self, bg=C.CONTENT)
        toolbar.pack(fill="x", pady=(0, 8))
        self.status = tk.Label(toolbar, text="", bg=C.CONTENT, fg=C.MUTED,
                               font=app.theme.font(8), anchor="w")
        self.status.pack(side="left")
        ttk.Button(toolbar, text="Actualizar", style="Small.TButton",
                   command=self.load).pack(side="right")
        for text, command in (("Detener", self._record_stop),
                              ("Grabar", self._record_start),
                              ("Salir", self._leave),
                              ("Entrar", self._join)):
            button = ttk.Button(toolbar, text=text, style="Small.TButton",
                                command=command)
            button.pack(side="right", padx=(0, 6))
            setattr(self, "_btn_" + text.lower(), button)
        self._btn_guardar = ttk.Button(toolbar, text="Guardar grabación…",
                                       style="Small.TButton",
                                       command=self._save_recording)
        self._btn_guardar.pack(side="right", padx=(0, 6))
        self.record_label = tk.Label(toolbar, text="", bg=C.CONTENT, fg=C.RED,
                                     font=app.theme.font(8, "bold"))
        self.record_label.pack(side="right", padx=(0, 10))
        columns = [TableColumn("channel", "Canal", 260, stretch=True),
                   TableColumn("type", "Tipo", 110),
                   TableColumn("call", "Llamada", 140),
                   TableColumn("users", "Usuarios conectados", 420, stretch=True)]
        self.table = Table(self, columns, height=8, theme=app.theme,
                           on_select=lambda _rows: self._channel_changed(),
                           empty_text="Sin canales de este tipo.")
        self.table.pack(fill="x")
        self.table.tree.bind("<Double-1>", lambda _e: self._open_messages())
        tk.Label(self, text="MIEMBROS EN LA SALA", bg=C.CONTENT, fg=C.MUTED,
                 font=app.theme.font(8, "bold"), anchor="w").pack(
            fill="x", pady=(8, 2))
        member_columns = [TableColumn("user", "Miembro", 300, stretch=True),
                          TableColumn("id", "ID", 220)]
        self.member_table = Table(self, member_columns, height=7, theme=app.theme,
                                  multi=True,
                                  empty_text="Selecciona una sala con miembros.")
        self.member_table.pack(fill="both", expand=True)
        self.member_table.tree.bind("<<TreeviewSelect>>",
                                    lambda _e: self._set_controls())
        self._member_anchor: str | None = None
        self.member_table.tree.bind("<ButtonPress-1>", self._member_press)
        self.member_table.tree.bind("<Shift-Up>", lambda _e: self._member_extend(-1))
        self.member_table.tree.bind("<Shift-Down>", lambda _e: self._member_extend(1))
        self.member_table.tree.bind("<Shift-Prior>", lambda _e: self._member_extend(-7))
        self.member_table.tree.bind("<Shift-Next>", lambda _e: self._member_extend(7))
        self.member_table.tree.unbind("<Button-3>")
        self.member_table.tree.bind("<Button-3>", self._member_context)
        self._member_menu = tk.Menu(self, tearoff=0, bg=C.CARD, fg=C.TEXT,
                                    activebackground=C.ACCENT_SOFT,
                                    activeforeground=C.TEXT)
        self._member_menu.add_command(label="Mover al destino",
                                      command=self._move_members)
        self._member_menu.add_command(label="Desconectar",
                                      command=self._disconnect_members)
        self._member_menu.add_separator()
        self._member_menu.add_command(label="Silenciar", command=self._toggle_mute)
        self._member_menu.add_command(label="Ensordecer", command=self._toggle_deaf)
        if stage:
            self._member_menu.add_separator()
            self._member_menu.add_command(label="Permitir hablar",
                                          command=lambda: self._stage(False))
            self._member_menu.add_command(label="Subir/Bajar escenario",
                                          command=self._toggle_stage)
        actions = tk.Frame(self, bg=C.CONTENT)
        actions.pack(fill="x", pady=(6, 0))
        self.move_var = tk.StringVar()
        self.move_combo = ttk.Combobox(actions, textvariable=self.move_var,
                                       state="readonly", width=22)
        self.move_combo.pack(side="left")
        for text, command, permission in (
                ("Mover", self._move_members, self._can_move),
                ("Desconectar", self._disconnect_members, self._can_move),
                ("Silenciar", self._toggle_mute, self._can_mute),
                ("Ensordecer", self._toggle_deaf, self._can_deafen)):
            button = ttk.Button(actions, text=text, style="Small.TButton",
                                command=command)
            button.pack(side="left", padx=(6, 0))
            setattr(self, "_act_" + text.split()[0].lower(), button)
            if not permission:
                button.configure(state="disabled")
        self._stage_buttons = []
        self._act_permitir = None
        self._act_escenario = None
        if stage:
            self._act_permitir = ttk.Button(
                actions, text="Permitir hablar", style="Small.TButton",
                command=lambda: self._stage(False))
            self._act_permitir.pack(side="left", padx=(6, 0))
            self._act_escenario = ttk.Button(
                actions, text="Subir escenario", style="Small.TButton",
                command=self._toggle_stage)
            self._act_escenario.pack(side="left", padx=(6, 0))
            self._stage_buttons = [self._act_permitir, self._act_escenario]
            if not self._can_mute:
                for button in self._stage_buttons:
                    button.configure(state="disabled")
        tk.Label(self,
                 text="Solo se muestra presencia (quién está en cada sala). "
                      "No se graba audio ni se entra de forma oculta.",
                 bg=C.CARD, fg=C.FAINT, font=app.theme.font(8),
                 anchor="w", justify="left").pack(fill="x", pady=(6, 0))

    def load(self) -> None:
        self.loaded = True
        self.page.ensure_gateway()
        self.page.start_voice_poll()
        self.move_combo.configure(values=[
            f"#{c.display_name}" for c in self.app.channels
            if c.type == 2 and c.id != (self._selected_channel().id
                                        if self._selected_channel() else "")])
        self._render()

    def _channel_changed(self) -> None:
        self._render_members()
        self._set_controls()

    def _member_press(self, event: tk.Event) -> str | None:
        row_id = self.member_table.tree.identify_row(event.y)
        if not row_id:
            return None
        ctrl = bool(event.state & 0x0004)
        shift = bool(event.state & 0x0001)
        if ctrl:
            selected = set(self.member_table.tree.selection())
            selected.discard(row_id) if row_id in selected else selected.add(row_id)
            self.member_table.tree.selection_set(*selected) if selected else \
                self.member_table.tree.selection_remove(*self.member_table.tree.selection())
            self.member_table.tree.focus(row_id)
            return "break"
        if shift:
            selected = set(self.member_table.tree.selection())
            if row_id in selected:
                selected.discard(row_id)
                self.member_table.tree.selection_set(*selected) if selected else \
                    self.member_table.tree.selection_remove(
                        *self.member_table.tree.selection())
                return "break"
            rows = list(self.member_table.tree.get_children())
            anchor = self._member_anchor if self._member_anchor in rows else row_id
            low, high = sorted((rows.index(anchor), rows.index(row_id)))
            self.member_table.tree.selection_set(*rows[low:high + 1])
            self.member_table.tree.focus(row_id)
            return "break"
        self._member_anchor = row_id
        return None

    def _member_extend(self, delta: int) -> str:
        rows = list(self.member_table.tree.get_children())
        if not rows:
            return "break"
        focus = self.member_table.tree.focus()
        if focus not in rows:
            focus = self._member_anchor if self._member_anchor in rows else rows[0]
        anchor = self._member_anchor if self._member_anchor in rows else focus
        target = max(0, min(rows.index(focus) + delta, len(rows) - 1))
        low, high = sorted((rows.index(anchor), target))
        self.member_table.tree.selection_set(*rows[low:high + 1])
        self.member_table.tree.focus(rows[target])
        self.member_table.tree.see(rows[target])
        return "break"

    def _member_context(self, event: tk.Event) -> None:
        row_id = self.member_table.tree.identify_row(event.y)
        if not row_id:
            return
        if row_id not in self.member_table.tree.selection():
            self.member_table.tree.selection_set(row_id)
        self.member_table.tree.focus(row_id)
        rows = self.member_table.selected_rows()
        muted = bool(rows) and all(row.get("_mute") for row in rows)
        deaf = bool(rows) and all(row.get("_deaf") for row in rows)
        self._member_menu.entryconfigure(
            3, label="Permitir hablar" if muted else "Silenciar")
        self._member_menu.entryconfigure(
            4, label="Escuchar" if deaf else "Ensordecer")
        try:
            self._member_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._member_menu.grab_release()
            except tk.TclError:
                pass

    def _open_messages(self) -> None:
        channel = self._selected_channel()
        if channel is None:
            return
        from .moderation import MessagesTab
        window = tk.Toplevel(self)
        window.title(f"Mensajes de {channel.display_name}")
        window.geometry("900x620")
        window.transient(self.winfo_toplevel())
        tab = MessagesTab(window, self.app, self.page)
        tab.pack(fill="both", expand=True, padx=10, pady=10)
        tab.show_channel(channel)

    def _render_members(self) -> None:
        channel = self._selected_channel()
        if channel is None:
            self.member_table.set_rows([])
            return
        users = self.page.voice_states.get(
            self.app.guild.id, {}).get(channel.id, [])
        self.member_table.set_rows([{
            "_id": user.get("id", ""),
            "user": user.get("name") or "Miembro",
            "id": user.get("id", ""),
            "_mute": bool(user.get("mute")),
            "_deaf": bool(user.get("deaf")),
            "_suppress": bool(user.get("suppress")),
        } for user in users])

    def _set_controls(self) -> None:
        selected = self._selected_channel() is not None
        members = bool(self.member_table.selected_ids())
        joined = bool(self.page.voice_joined_channel)
        recording = bool(self.page.voice_recording)
        self._btn_entrar.configure(
            state="normal" if selected else "disabled")
        self._btn_salir.configure(state="normal" if joined else "disabled")
        self._btn_grabar.configure(
            state="normal" if joined and not recording else "disabled")
        self._btn_detener.configure(
            state="normal" if recording else "disabled")
        self._btn_guardar.configure(
            state="normal" if self.page.voice_last_recording else "disabled")
        for name, allowed in (("_act_mover", self._can_move),
                              ("_act_desconectar", self._can_move)):
            button = getattr(self, name, None)
            if button is not None:
                button.configure(
                    state="normal" if allowed and members else "disabled")
        for name, allowed in (("_act_silenciar", self._can_mute),
                              ("_act_ensordecer", self._can_deafen)):
            button = getattr(self, name, None)
            if button is not None:
                button.configure(
                    state="normal" if allowed and members else "disabled")
        selected = self.member_table.selected_rows()
        all_muted = bool(selected) and all(row.get("_mute") for row in selected)
        all_deaf = bool(selected) and all(row.get("_deaf") for row in selected)
        self._act_silenciar.configure(
            text="Permitir hablar" if all_muted else "Silenciar")
        self._act_ensordecer.configure(
            text="Escuchar" if all_deaf else "Ensordecer")
        stage_state = ("normal" if self.stage and self._can_mute and members
                       else "disabled")
        for button in self._stage_buttons:
            if button is not None:
                button.configure(state=stage_state)
        if self._act_escenario is not None:
            all_suppressed = bool(selected) and all(
                row.get("_suppress") for row in selected)
            self._act_escenario.configure(
                text="Subir escenario" if all_suppressed else "Bajar escenario")

    def _selected_members(self) -> list[str]:
        return [str(row.get("_id")) for row in self.member_table.selected_rows()
                if row.get("_id")]

    def _move_members(self) -> None:
        ids = self._selected_members()
        label = self.move_var.get()
        target = next((c for c in self.app.channels
                       if c.type == 2 and f"#{c.display_name}" == label), None)
        if not ids or target is None:
            return
        self._voice_action(lambda user_id: self.app.client.update_member(
            self.app.guild.id, user_id, {"channel_id": target.id}))

    def _disconnect_members(self) -> None:
        ids = self._selected_members()
        if not ids:
            return
        self._voice_action(lambda user_id: self.app.client.update_member(
            self.app.guild.id, user_id, {"channel_id": None}))

    def _toggle_mute(self) -> None:
        rows = self.member_table.selected_rows()
        if not rows:
            return
        value = not all(row.get("_mute") for row in rows)
        self._member_flag("mute", value)

    def _toggle_deaf(self) -> None:
        rows = self.member_table.selected_rows()
        if not rows:
            return
        value = not all(row.get("_deaf") for row in rows)
        self._member_flag("deaf", value)

    def _member_flag(self, flag: str, value: bool) -> None:
        ids = self._selected_members()
        if not ids:
            return
        users = self.page.voice_states.get(
            self.app.guild.id, {}).get(
            self._selected_channel().id if self._selected_channel() else "", [])
        for user in users:
            if user.get("id") in ids:
                user[flag] = value
        self._render_members()
        existing = [user_id for user_id in ids
                    if user_id in self.member_table.tree.get_children()]
        if existing:
            self.member_table.tree.selection_set(*existing)
        self._set_controls()
        self._voice_action(lambda user_id: self.app.client.update_member(
            self.app.guild.id, user_id, {flag: value}))

    def _toggle_stage(self) -> None:
        rows = self.member_table.selected_rows()
        if not rows:
            return
        suppress = not all(row.get("_suppress") for row in rows)
        self._stage(suppress)

    def _stage(self, suppress: bool) -> None:
        ids = self._selected_members()
        if not ids:
            return
        self._voice_action(lambda user_id: self.app.client.modify_voice_state(
            self.app.guild.id, user_id, suppress=suppress))

    def _voice_action(self, action: Any) -> None:
        ids = self._selected_members()
        if not ids:
            self.page.toast_warn("Selecciona al menos un miembro.")
            return

        def work() -> int:
            for user_id in ids:
                action(user_id)
            return len(ids)

        def done(count: int) -> None:
            self.page.toast_ok(f"{count} miembros actualizados.")
            self._render()

        def failed(error: BaseException) -> None:
            if getattr(error, "status", None) == 404:
                self.status.configure(
                    text="Ese miembro ya no está en la sala o el canal cambió. "
                         "Actualiza la lista e inténtalo de nuevo.", fg=C.RED)
                self.load()
            else:
                self.page.error(error)

        self.page.run(work, done, failed)

    def _save_recording(self) -> None:
        if not self.page.voice_last_recording:
            return
        source = Path(self.page.voice_last_recording)
        target = filedialog.asksaveasfilename(
            parent=self, title="Guardar grabación",
            initialfile=source.name,
            defaultextension=source.suffix,
            filetypes=[("Audio", "*.ogg *.wav"), ("Todos", "*.*")])
        if not target:
            return
        try:
            shutil.copy2(source, target)
            self.status.configure(text=f"Grabación guardada en {target}", fg=C.GREEN)
        except OSError as error:
            self.status.configure(text=f"No se pudo guardar: {error}", fg=C.RED)

    def _selected_channel(self) -> Channel | None:
        ids = self.table.selected_ids()
        if not ids:
            return None
        return next((c for c in self._channels() if c.id == ids[0]), None)

    def _join(self) -> None:
        channel = self._selected_channel()
        if channel is None:
            self.page.toast_warn("Selecciona una sala de la tabla.")
            return
        if not voice_dependencies_available():
            missing = ", ".join(voice_missing_dependencies())
            self.status.configure(
                text=f"Faltan dependencias de voz: {missing}. "
                     "Instala: pip install \"discord.py[voice]\" "
                     "discord-ext-voice-recv PyNaCl", fg=C.RED)
            return
        token = getattr(self.app, "bot_token", "")
        if not token:
            self.status.configure(text="Falta el token del bot.", fg=C.RED)
            return
        process = self.page.voice_process
        process.start(token)
        process.send({"cmd": "join", "guild_id": self.app.guild.id,
                      "channel_id": channel.id})
        self.status.configure(text=f"Solicitando entrada visible a {channel.display_name}…",
                              fg=C.YELLOW)

    def _leave(self) -> None:
        self.page.voice_process.send({"cmd": "leave"})
        self.status.configure(text="Saliendo de la sala…", fg=C.YELLOW)

    def _record_start(self) -> None:
        if not self.page.voice_joined_channel:
            self.status.configure(text="Primero entra a una sala.", fg=C.RED)
            return
        if self.page.voice_recording:
            return
        dialog = ConfirmDialog(
            self, "Grabar llamada",
            "La grabación será visible para el servidor mediante el aviso del bot. "
            "Solo debes grabarla si todos los participantes están de acuerdo. "
            "¿Comenzar la grabación?",
            confirm_text="Comenzar grabación", danger=True, theme=self.app.theme)
        if not dialog.show():
            return
        self.page.voice_process.send({"cmd": "record_start"})

    def _record_stop(self) -> None:
        self.page.voice_process.send({"cmd": "record_stop"})

    def handle_voice_event(self, event: dict) -> None:
        name = event.get("event")
        if name == "joined":
            self.status.configure(text=f"Conectado a {event.get('channel', '')}",
                                  fg=C.GREEN)
        elif name == "left":
            self.status.configure(text="Fuera de la sala.", fg=C.MUTED)
        elif name == "recording":
            self.record_label.configure(text="● GRABANDO")
            self.status.configure(text=f"Grabando en {event.get('file')}", fg=C.RED)
        elif name == "recorded":
            self.record_label.configure(text="")
            self.status.configure(text=f"Grabación guardada: {event.get('file')}",
                                  fg=C.GREEN)
        elif name == "error":
            self.status.configure(text=str(event.get("message")), fg=C.RED)
        elif name == "exit":
            self.record_label.configure(text="")
        self._set_controls()

    def _channels(self) -> list[Channel]:
        if self.stage:
            return [c for c in self.app.channels if c.type == 13]
        return [c for c in self.app.channels if c.type == 2]

    def _render(self) -> None:
        states = self.page.voice_states.get(self.app.guild.id, {})
        rows = []
        for channel in self._channels():
            users = states.get(channel.id, [])
            rows.append({
                "_id": channel.id,
                "channel": channel.display_name,
                "type": "Escenario" if channel.type == 13 else "Voz",
                "call": "Abierta" if users else "Sin conexión",
                "users": ", ".join(user.get("name") or user.get("id", "")
                                   for user in users) or "—",
            })
        self.table.set_rows(rows)
        self.status.configure(
            text=f"{len(rows)} canales · Gateway: {self.page.gateway_status}",
            fg=C.GREEN if self.page.gateway_status in ("ready", "connected") else C.MUTED)
        self._render_members()
        self._set_controls()


class ForumsTab(tk.Frame):
    def __init__(self, master: tk.Misc, app: Any, page: Any):
        super().__init__(master, bg=C.CONTENT)
        self.app = app
        self.page = page
        self.loaded = False
        self._threads: list[Channel] = []
        self._messages: list[Message] = []
        self.can_manage = app.can("MANAGE_MESSAGES")
        self.can_send = app.can("SEND_MESSAGES")
        toolbar = tk.Frame(self, bg=C.CONTENT)
        toolbar.pack(fill="x", pady=(0, 8))
        self.forum_var = tk.StringVar()
        self.forum_combo = ttk.Combobox(toolbar, textvariable=self.forum_var,
                                        state="readonly", width=28)
        self.forum_combo.pack(side="left")
        self.forum_combo.bind("<<ComboboxSelected>>", lambda _e: self._load_threads())
        self.thread_var = tk.StringVar()
        self.thread_combo = ttk.Combobox(toolbar, textvariable=self.thread_var,
                                         state="readonly", width=34)
        self.thread_combo.pack(side="left", padx=(8, 0))
        self.thread_combo.bind("<<ComboboxSelected>>", lambda _e: self._load_messages())
        ttk.Button(toolbar, text="Actualizar", style="Small.TButton",
                   command=self.load).pack(side="right")
        self.count = tk.Label(toolbar, text="", bg=C.CONTENT, fg=C.MUTED,
                              font=app.theme.font(8))
        self.count.pack(side="right", padx=(0, 8))

        columns = [TableColumn("author", "Autor", 130),
                   TableColumn("content", "Mensaje", 430, stretch=True),
                   TableColumn("attachments", "Adjuntos", 260, stretch=True),
                   TableColumn("date", "Enviado", 130)]
        self.table = Table(self, columns, height=13, theme=app.theme, multi=True,
                           empty_text="Selecciona un foro y un hilo.")
        self.table.pack(fill="both", expand=True)
        actions = tk.Frame(self, bg=C.CONTENT)
        actions.pack(fill="x", pady=(6, 0))
        for text, command in (("Fijar", lambda: self._pin(True)),
                              ("Desfijar", lambda: self._pin(False)),
                              ("Eliminar", self._delete)):
            button = ttk.Button(actions, text=text, style="Small.TButton",
                                command=command)
            button.pack(side="left", padx=(0, 6))
            if not self.can_manage:
                button.configure(state="disabled")

        composer = tk.Frame(self, bg=C.CARD, highlightbackground=C.BORDER_SOFT,
                            highlightthickness=1)
        composer.pack(fill="x", pady=(8, 0))
        self.composer_var = tk.StringVar()
        self.composer = ttk.Entry(composer, textvariable=self.composer_var)
        self.composer.pack(side="left", fill="x", expand=True, padx=10, pady=8)
        self.composer.bind("<Return>", lambda _e: self._send())
        ttk.Button(composer, text="Enviar mensaje", style="SmallAccent.TButton",
                   command=self._send).pack(side="right", padx=8)
        self.empty = tk.Label(self, text="", bg=C.CONTENT, fg=C.MUTED,
                              font=app.theme.font(9), anchor="w")
        self.empty.pack(fill="x")

    def load(self) -> None:
        self.loaded = True
        forums = [c for c in self.app.channels if c.type == 15]
        self.forum_combo.configure(values=[f"#{c.display_name}" for c in forums])
        if not forums:
            self.empty.configure(text="Este servidor no tiene canales de foro.")
            self.table.set_rows([])
            return
        self.empty.configure(text="")
        if self.forum_var.get() not in [f"#{c.display_name}" for c in forums]:
            self.forum_var.set(f"#{forums[0].display_name}")
        self._load_threads()

    def _forum(self) -> Channel | None:
        label = self.forum_var.get()
        return next((c for c in self.app.channels
                     if c.type == 15 and f"#{c.display_name}" == label), None)

    def _load_threads(self) -> None:
        forum = self._forum()
        if forum is None:
            return
        self.thread_var.set("")
        self.thread_combo.configure(values=[])
        self.page.run(lambda: self.app.client.list_active_threads(forum.id),
                      self._threads_done, self.page.error)

    def _threads_done(self, threads: list[Channel]) -> None:
        self._threads = threads
        self.thread_combo.configure(values=[t.display_name for t in threads])
        if threads:
            self.thread_var.set(threads[0].display_name)
            self._load_messages()
        else:
            self.table.set_rows([])
            self.empty.configure(text="Este foro no tiene hilos activos.")
            self.count.configure(text="0 mensajes")

    def _thread(self) -> Channel | None:
        label = self.thread_var.get()
        return next((t for t in self._threads if t.display_name == label), None)

    def _load_messages(self) -> None:
        thread = self._thread()
        if thread is None:
            return
        self.page.run(lambda: self.app.client.list_messages(thread.id, limit=50),
                      self._messages_done, self.page.error)

    def _messages_done(self, messages: list[Message]) -> None:
        self._messages = messages
        self.table.set_rows([{
            "_id": message.id,
            "author": message.author.display_name,
            "content": message.preview,
            "attachments": ", ".join(a.filename for a in message.attachments) or "—",
            "date": fmt_datetime(message.timestamp),
            "_raw": message,
        } for message in messages])
        self.count.configure(text=f"{len(messages)} mensajes")

    def _selected(self) -> list[str]:
        return self.table.selected_ids()

    def _pin(self, pinned: bool) -> None:
        thread = self._thread()
        ids = self._selected()
        if thread is None or not ids:
            return
        client = self.app.client
        self.page.run(lambda: [client.pin_message(thread.id, i) if pinned
                               else client.unpin_message(thread.id, i) for i in ids],
                      lambda _r: self._load_messages(), self.page.error)

    def _delete(self) -> None:
        thread = self._thread()
        ids = self._selected()
        if thread is None or not ids:
            return
        client = self.app.client
        self.page.run(lambda: [client.delete_message(thread.id, i) for i in ids],
                      lambda _r: self._load_messages(), self.page.error)

    def _send(self) -> None:
        thread = self._thread()
        content = self.composer_var.get().strip()
        if thread is None or not content:
            return
        self.composer_var.set("")
        self.page.run(lambda: self.app.client.send_message(thread.id, content),
                      lambda _r: self._load_messages(), self.page.error)
