"""Modales compartidos entre páginas (banear, enviar mensaje directo)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from ...constants import DELETE_MESSAGE_WINDOWS
from ..emoji_picker import EmojiPicker
from ..theme import C
from ..widgets import Checkbox, Field, Modal, labeled_text


class BanModal(Modal):
    def __init__(self, parent: tk.Misc, app: Any, user_id: str = "",
                 username: str = "", on_done: Callable[[], None] | None = None):
        super().__init__(parent, "Banear usuario", width=520, theme=app.theme,
                         subtitle="El usuario no podrá volver a entrar hasta que retires el baneo.")
        self.app = app
        self.on_done = on_done
        body = self.body

        id_field = Field(body, "ID de usuario", "Pega el ID numérico de la cuenta.")
        id_field.pack(fill="x", pady=(0, 12))
        self.id_var = tk.StringVar(value=user_id)
        entry = ttk.Entry(id_field.slot, textvariable=self.id_var)
        id_field.add(entry)
        if username:
            tk.Label(body, text=f"Usuario: {username}", bg=C.CARD, fg=C.MUTED,
                     font=app.theme.font(8), anchor="w").pack(fill="x", pady=(0, 8))

        reason_field = Field(body, "Motivo (opcional)", "Se guarda en el registro de auditoría.")
        reason_field.pack(fill="x", pady=(0, 12))
        self.reason_text = tk.Text(reason_field.slot, height=3, bg=C.INPUT, fg=C.TEXT,
                                   insertbackground=C.TEXT, relief="flat", bd=0,
                                   highlightthickness=1, highlightbackground=C.BORDER,
                                   highlightcolor=C.ACCENT, font=app.theme.font(9),
                                   wrap="word", padx=8, pady=6)
        reason_field.add(self.reason_text)

        delete_field = Field(body, "Borrar mensajes recientes")
        delete_field.pack(fill="x", pady=(0, 6))
        self.delete_var = tk.StringVar(value=DELETE_MESSAGE_WINDOWS[0][1])
        ttk.Combobox(delete_field.slot, state="readonly",
                     values=[label for _value, label in DELETE_MESSAGE_WINDOWS],
                     textvariable=self.delete_var).pack(fill="x")

        self.add_button("Cancelar", self.close)
        self.add_button("Banear", self._submit, style="Danger.TButton")

    def _submit(self) -> None:
        user_id = self.id_var.get().strip()
        if not user_id.isdigit() or len(user_id) < 15:
            self.show_error("El ID debe ser numérico y tener al menos 15 dígitos.")
            return
        delete_seconds = next((value for value, label in DELETE_MESSAGE_WINDOWS
                               if label == self.delete_var.get()), 0)
        reason = self.reason_text.get("1.0", "end").strip() or None
        client = self.app.client
        guild_id = self.app.guild.id
        self.set_busy(True)

        def done(_result: Any) -> None:
            self.app.toasts.show("Usuario baneado.", "success")
            if self.on_done:
                self.on_done()
            self.close()

        def failed(error: BaseException) -> None:
            self.set_busy(False)
            self.show_error(str(error))

        self.app.run_task(lambda: client.ban_member(guild_id, user_id, delete_seconds, reason),
                          done, failed)


class DirectMessageModal(Modal):
    def __init__(self, parent: tk.Misc, app: Any, user_id: str, name: str):
        super().__init__(parent, f"Mensaje directo a {name}", width=520, theme=app.theme,
                         subtitle="Se enviará como mensaje privado del bot, no de tu cuenta.")
        self.app = app
        self.user_id = user_id
        field, self.text = labeled_text(self.body, app, "Mensaje", height=5)
        field.pack(fill="x")
        emoji_row = tk.Frame(self.body, bg=C.CARD)
        emoji_row.pack(fill="x", pady=(6, 0))
        self.emoji_button = ttk.Button(emoji_row, text="Insertar emoji",
                                       style="Small.TButton", command=self._open_emoji_picker)
        self.emoji_button.pack(side="left")
        self.text.focus_set()
        self.add_button("Cancelar", self.close)
        self.add_button("Enviar mensaje", self._submit, style="Accent.TButton")

    def _open_emoji_picker(self) -> None:
        EmojiPicker(self, self.app, self.emoji_button, self._insert_emoji)

    def _insert_emoji(self, text: str) -> None:
        try:
            self.text.insert("insert", text)
        except tk.TclError:
            pass

    def _submit(self) -> None:
        content = self.text.get("1.0", "end").strip()
        if not content:
            self.show_error("Escribe un mensaje.")
            return
        client = self.app.client
        user_id = self.user_id

        def work() -> Any:
            channel_id = client.create_dm(user_id)
            return client.send_message(channel_id, content)

        def done(_result: Any) -> None:
            self.app.toasts.show("Mensaje enviado.", "success")
            self.close()

        def failed(error: BaseException) -> None:
            self.set_busy(False)
            self.show_error(str(error))

        self.set_busy(True)
        self.app.run_task(work, done, failed)
