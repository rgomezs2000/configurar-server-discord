"""Ajustes del servidor: identidad, seguridad, canales del sistema y salida."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any

from ...constants import (AFK_TIMEOUTS, CONTENT_FILTER_LEVELS,
                          DEFAULT_NOTIFICATION_LEVELS, LOCALES, MFA_LEVELS,
                          NSFW_LEVELS, VERIFICATION_LEVELS)
from ...util import MAX_ICON_BYTES, image_to_data_uri
from ..theme import C
from ..widgets import (Card, ConfirmDialog, Field, PageHeader, ScrollFrame,
                       labeled_combo, round_rect)
from .base import Page


class SettingsPage(Page):
    key = "settings"
    label = "Ajustes"
    glyph = "▣"

    def build(self) -> None:
        app = self.app
        self.header = PageHeader(self, app, "Ajustes del servidor",
                                 "Identidad, seguridad y canales del sistema.")
        self.header.pack(fill="x", padx=28, pady=(22, 0))
        self._manage = app.can("MANAGE_GUILD")
        self.save_button = self.header.button("Guardar cambios", self._save,
                                              style="Accent.TButton")
        self.header.button("Recargar", self.refresh)
        if not self._manage:
            self.save_button.configure(state="disabled")

        self.scroll = ScrollFrame(self, bg=C.CONTENT)
        self.scroll.pack(fill="both", expand=True, padx=22, pady=(12, 10))
        self.content = self.scroll.inner

        self._icon_data: str | None = None
        self._banner_data: str | None = None
        self._icon_changed = False
        self._banner_changed = False
        self._icon_photo: tk.PhotoImage | None = None
        self._banner_photo: tk.PhotoImage | None = None
        self._server_icon_photo: tk.PhotoImage | None = None
        self._server_banner_photo: tk.PhotoImage | None = None

        self._build_identity()
        self._build_security()
        self._build_community()
        self._build_system()
        if self.app.session_kind == "user":
            self._build_danger()

    # ------------------------------------------------------------------ #
    def _card(self, title: str, subtitle: str = "") -> tk.Frame:
        card = Card(self.content, padding=18)
        card.pack(fill="x", padx=6, pady=8)
        head = tk.Frame(card.body, bg=C.CARD)
        head.pack(fill="x", pady=(0, 12))
        tk.Label(head, text=title, bg=C.CARD, fg=C.TEXT,
                 font=self.app.theme.font(12, "bold"), anchor="w").pack(fill="x")
        if subtitle:
            tk.Label(head, text=subtitle, bg=C.CARD, fg=C.MUTED,
                     font=self.app.theme.font(8), anchor="w").pack(fill="x", pady=(2, 0))
        return card.body

    # ------------------------------------------------------------------ #
    def _build_identity(self) -> None:
        app = self.app
        body = self._card("Identidad", "Nombre, descripción e imágenes del servidor.")
        columns = tk.Frame(body, bg=C.CARD)
        columns.pack(fill="x")

        left = tk.Frame(columns, bg=C.CARD)
        left.pack(side="left", fill="x", expand=True, padx=(0, 20), anchor="n")
        self.name_var = tk.StringVar()
        name_field = Field(left, "Nombre del servidor", bg=C.CARD)
        name_field.pack(fill="x", pady=(0, 12))
        self.name_entry = ttk.Entry(name_field.slot, textvariable=self.name_var)
        name_field.add(self.name_entry)

        desc_field = Field(left, "Descripción", "Aparece en la vista previa del servidor.",
                           bg=C.CARD)
        desc_field.pack(fill="x")
        self.desc_text = tk.Text(desc_field.slot, height=3, bg=C.INPUT, fg=C.TEXT,
                                 insertbackground=C.TEXT, relief="flat", bd=0,
                                 highlightthickness=1, highlightbackground=C.BORDER,
                                 highlightcolor=C.ACCENT, font=app.theme.font(9),
                                 wrap="word", padx=8, pady=6)
        desc_field.add(self.desc_text)

        right = tk.Frame(columns, bg=C.CARD)
        right.pack(side="right", anchor="n")
        tk.Label(right, text="ICONO", bg=C.CARD, fg=C.MUTED,
                 font=app.theme.font(8, "bold"), anchor="w").pack(fill="x")
        self.icon_canvas = tk.Canvas(right, width=96, height=96, bg=C.CARD,
                                     highlightthickness=0, bd=0)
        self.icon_canvas.pack(pady=(4, 6))
        icon_actions = tk.Frame(right, bg=C.CARD)
        icon_actions.pack()
        ttk.Button(icon_actions, text="Cambiar…", style="Small.TButton",
                   command=lambda: self._pick_image("icon")).pack(side="left")
        ttk.Button(icon_actions, text="Quitar", style="Small.TButton",
                   command=lambda: self._clear_image("icon")).pack(side="left", padx=(4, 0))

        tk.Label(right, text="BANNER", bg=C.CARD, fg=C.MUTED,
                 font=app.theme.font(8, "bold"), anchor="w").pack(fill="x", pady=(12, 0))
        self.banner_canvas = tk.Canvas(right, width=220, height=70, bg=C.CARD,
                                       highlightthickness=0, bd=0)
        self.banner_canvas.pack(pady=(4, 6))
        banner_actions = tk.Frame(right, bg=C.CARD)
        banner_actions.pack()
        self.banner_change_button = ttk.Button(
            banner_actions, text="Cambiar…", style="Small.TButton",
            command=lambda: self._pick_image("banner"))
        self.banner_change_button.pack(side="left")
        self.banner_clear_button = ttk.Button(
            banner_actions, text="Quitar", style="Small.TButton",
            command=lambda: self._clear_image("banner"))
        self.banner_clear_button.pack(side="left", padx=(4, 0))
        self.banner_hint = tk.Label(right, text="", bg=C.CARD, fg=C.FAINT,
                                    font=app.theme.font(7), wraplength=220,
                                    justify="left", anchor="w")
        self.banner_hint.pack(fill="x", pady=(4, 0))

    def _build_security(self) -> None:
        body = self._card("Seguridad",
                          "Nivel de verificación y filtro de contenido explícito.")
        row = tk.Frame(body, bg=C.CARD)
        row.pack(fill="x")
        self.verification_var = tk.StringVar()
        verification_field, self.verification_combo = labeled_combo(
            row, self.app, "Nivel de verificación",
            "Quién puede entrar al servidor.",
            [label for _v, label, _d in VERIFICATION_LEVELS],
            variable=self.verification_var)
        verification_field.pack(side="left", fill="x", expand=True, padx=(0, 14))
        self.filter_var = tk.StringVar()
        filter_field, self.filter_combo = labeled_combo(
            row, self.app, "Filtro de contenido explícito",
            "Qué mensajes se escanean.", [label for _v, label, _d in CONTENT_FILTER_LEVELS],
            variable=self.filter_var)
        filter_field.pack(side="left", fill="x", expand=True)

        info = tk.Frame(body, bg=C.CARD)
        info.pack(fill="x", pady=(12, 0))
        self.mfa_label = tk.Label(info, text="", bg=C.CARD, fg=C.MUTED,
                                  font=self.app.theme.font(8), anchor="w")
        self.mfa_label.pack(fill="x")
        self.nsfw_label = tk.Label(info, text="", bg=C.CARD, fg=C.MUTED,
                                   font=self.app.theme.font(8), anchor="w")
        self.nsfw_label.pack(fill="x")

    def _build_community(self) -> None:
        guild = self.app.guild
        self._community = guild.is_community
        body = self._card(
            "Comunidad",
            "Canales y funciones que Discord solo habilita con la comunidad activa.")
        if guild.is_community:
            row = tk.Frame(body, bg=C.CARD)
            row.pack(fill="x")
            self.rules_channel_var = tk.StringVar()
            rules_field, _c1 = labeled_combo(
                row, self.app, "Canal de reglas", "Obligatorio para la comunidad.",
                ["Ninguno"] + self._text_channels(), variable=self.rules_channel_var)
            rules_field.pack(side="left", fill="x", expand=True, padx=(0, 14))
            self.public_updates_channel_var = tk.StringVar()
            updates_field, _c2 = labeled_combo(
                row, self.app, "Canal de anuncios", "Actualizaciones de Discord.",
                ["Ninguno"] + self._text_channels(),
                variable=self.public_updates_channel_var)
            updates_field.pack(side="left", fill="x", expand=True)
            tk.Label(body,
                     text="Comunidad activa: también se habilitan foro, media, escenario, "
                          "descubrimiento y pantalla de bienvenida.",
                     bg=C.CARD, fg=C.GREEN, font=self.app.theme.font(8), anchor="w",
                     justify="left", wraplength=760).pack(fill="x", pady=(10, 0))
        else:
            banner = tk.Frame(body, bg=C.YELLOW_SOFT, highlightbackground=C.YELLOW,
                              highlightthickness=1)
            banner.pack(fill="x")
            tk.Label(banner, text="Comunidad no activada", bg=C.YELLOW_SOFT,
                     fg="#ffd98a", font=self.app.theme.font(9, "bold"),
                     anchor="w").pack(fill="x", padx=12, pady=(8, 2))
            tk.Label(banner,
                     text="Actívala en Discord (Configuración del servidor → Comunidad) para "
                          "habilitar canal de reglas, canal de anuncios, foro, media, "
                          "escenario, descubrimiento y pantalla de bienvenida.",
                     bg=C.YELLOW_SOFT, fg="#e8c98f", font=self.app.theme.font(8),
                     justify="left", wraplength=740, anchor="w").pack(
                fill="x", padx=12, pady=(0, 8))
            self.rules_channel_var = None
            self.public_updates_channel_var = None

    def _build_system(self) -> None:
        body = self._card("Canales y notificaciones",
                          "Dónde van los mensajes del sistema y el estado de voz.")
        row = tk.Frame(body, bg=C.CARD)
        row.pack(fill="x")
        self.notifications_var = tk.StringVar()
        notifications_field, _combo = labeled_combo(
            row, self.app, "Notificaciones por defecto", "",
            [label for _v, label, _d in DEFAULT_NOTIFICATION_LEVELS],
            variable=self.notifications_var)
        notifications_field.pack(side="left", fill="x", expand=True, padx=(0, 14))
        self.locale_var = tk.StringVar()
        locale_field, _combo2 = labeled_combo(
            row, self.app, "Idioma del servidor", "",
            [label for _v, label in LOCALES], variable=self.locale_var)
        locale_field.pack(side="left", fill="x", expand=True)

        row2 = tk.Frame(body, bg=C.CARD)
        row2.pack(fill="x", pady=(12, 0))
        self.system_channel_var = tk.StringVar()
        system_field, _c3 = labeled_combo(row2, self.app, "Canal del sistema",
                                          "Mensajes de bienvenida y avisos.",
                                          ["Ninguno"] + self._text_channels(),
                                          variable=self.system_channel_var)
        system_field.pack(side="left", fill="x", expand=True, padx=(0, 14))
        self.afk_channel_var = tk.StringVar()
        afk_field, _c5 = labeled_combo(row2, self.app, "Canal de inactividad", "",
                                       ["Ninguno"] + self._voice_channels(),
                                       variable=self.afk_channel_var)
        afk_field.pack(side="left", fill="x", expand=True)

        row3 = tk.Frame(body, bg=C.CARD)
        row3.pack(fill="x", pady=(12, 0))
        self.afk_timeout_var = tk.StringVar()
        timeout_field, _c6 = labeled_combo(row3, self.app, "Tiempo de inactividad", "",
                                           [label for _v, label in AFK_TIMEOUTS],
                                           variable=self.afk_timeout_var)
        timeout_field.pack(side="left", fill="x", expand=True)

    def _build_danger(self) -> None:
        body = self._card("Zona sensible", "Acciones que no se pueden deshacer.")
        row = tk.Frame(body, bg=C.CARD)
        row.pack(fill="x")
        tk.Label(row, text="Quitar el bot de este servidor. Dejarás de administrarlo desde "
                           "la app hasta que lo vuelvas a invitar; tu cuenta sigue en el "
                           "servidor.", bg=C.CARD, fg=C.DIM, font=self.app.theme.font(9),
                 anchor="w", justify="left").pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Quitar el bot", style="SmallDanger.TButton",
                   command=self._leave).pack(side="right")

    # ------------------------------------------------------------------ #
    def _text_channels(self) -> list[str]:
        return [f"#{c.display_name}" for c in self.app.channels if c.is_text]

    def _voice_channels(self) -> list[str]:
        return [f"#{c.display_name}" for c in self.app.channels if c.is_voice]

    def _channel_id(self, label: str) -> str | None:
        if not label or label == "Ninguno":
            return None
        name = label.lstrip("#")
        channel = next((c for c in self.app.channels if c.display_name == name), None)
        return channel.id if channel else None

    def _channel_label(self, channel_id: str | None) -> str:
        if not channel_id:
            return "Ninguno"
        channel = next((c for c in self.app.channels if c.id == channel_id), None)
        return f"#{channel.display_name}" if channel else "Ninguno"

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        guild = self.app.guild
        app = self.app
        self.name_var.set(guild.name)
        self.desc_text.delete("1.0", "end")
        if guild.description:
            self.desc_text.insert("1.0", guild.description)
        self.verification_var.set(next((label for value, label, _d in VERIFICATION_LEVELS
                                        if value == guild.verification_level), "Ninguno"))
        self.filter_var.set(next((label for value, label, _d in CONTENT_FILTER_LEVELS
                                  if value == guild.explicit_content_filter), "Desactivado"))
        self.notifications_var.set(next((label for value, label, _d in DEFAULT_NOTIFICATION_LEVELS
                                         if value == guild.default_message_notifications),
                                        "Solo menciones"))
        self.locale_var.set(next((label for value, label in LOCALES
                                  if value == guild.preferred_locale), "Español (España)"))
        self.system_channel_var.set(self._channel_label(guild.system_channel_id))
        if self._community and self.rules_channel_var is not None:
            self.rules_channel_var.set(self._channel_label(guild.rules_channel_id))
            if self.public_updates_channel_var is not None:
                self.public_updates_channel_var.set(
                    self._channel_label(guild.public_updates_channel_id))
        self.afk_channel_var.set(self._channel_label(guild.afk_channel_id))
        self.afk_timeout_var.set(next((label for value, label in AFK_TIMEOUTS
                                       if value == guild.afk_timeout), "5 minutos"))
        self.mfa_label.configure(
            text=f"Autenticación en dos pasos: {MFA_LEVELS.get(guild.mfa_level, '—')}")
        self.nsfw_label.configure(text=f"Clasificación NSFW: "
                                       f"{NSFW_LEVELS.get(guild.nsfw_level, '—')}")
        self._icon_data = None
        self._banner_data = None
        self._icon_changed = False
        self._banner_changed = False
        self._icon_photo = None
        self._banner_photo = None
        self._server_icon_photo = None
        self._server_banner_photo = None
        self._render_icon_preview()
        self._render_banner_preview()
        self._load_remote_previews()
        banner_allowed = guild.can_use_banner and self._manage
        for button in (self.banner_change_button, self.banner_clear_button):
            button.configure(state="normal" if banner_allowed else "disabled")
        self.banner_hint.configure(
            text="" if guild.can_use_banner else
            f"Requiere Nivel 2 de mejoras (actual: Nivel {guild.boost_level}).")
        if not self._manage:
            for widget in (self.name_entry, self.desc_text, self.verification_combo,
                           self.filter_combo):
                try:
                    widget.configure(state="disabled")
                except tk.TclError:
                    pass
        self._snapshot_value = self._snapshot()

    def _snapshot(self) -> tuple:
        return (
            self.name_var.get().strip(),
            self.desc_text.get("1.0", "end").strip(),
            self.verification_var.get(),
            self.filter_var.get(),
            self.notifications_var.get(),
            self.locale_var.get(),
            self.system_channel_var.get(),
            self.rules_channel_var.get() if self.rules_channel_var is not None else "",
            (self.public_updates_channel_var.get()
             if self.public_updates_channel_var is not None else ""),
            self.afk_channel_var.get(),
            self.afk_timeout_var.get(),
            self._icon_changed,
            self._banner_changed,
        )

    def is_dirty(self) -> bool:
        snapshot = getattr(self, "_snapshot_value", None)
        return snapshot is not None and self._snapshot() != snapshot

    def on_guild_refreshed(self) -> None:
        if not self.is_dirty():
            self.refresh()

    # ------------------------------------------------------------------ #
    @staticmethod
    def _fit(photo: tk.PhotoImage, max_width: int, max_height: int) -> tk.PhotoImage:
        factor = max(1, (photo.width() + max_width - 1) // max_width,
                     (photo.height() + max_height - 1) // max_height)
        return photo.subsample(factor) if factor > 1 else photo

    def _load_remote_previews(self) -> None:
        guild = self.app.guild
        if guild is None or not self.app.images.enabled:
            return
        if guild.icon_url:
            photo = self.app.images.get(guild.icon_url, 92, self._set_server_icon)
            if photo is not None:
                self._set_server_icon(photo)
        if guild.banner_url:
            photo = self.app.images.get(guild.banner_url, 216, self._set_server_banner)
            if photo is not None:
                self._set_server_banner(photo)

    def _set_server_icon(self, photo: tk.PhotoImage | None) -> None:
        self._server_icon_photo = photo
        self._render_icon_preview()

    def _set_server_banner(self, photo: tk.PhotoImage | None) -> None:
        self._server_banner_photo = photo
        self._render_banner_preview()

    def _render_icon_preview(self) -> None:
        canvas = self.icon_canvas
        canvas.delete("all")
        if self._icon_photo is not None:
            photo = self._fit(self._icon_photo, 92, 92)
            self._icon_shown = photo
            canvas.create_image(48, 48, image=photo)
            return
        if self._server_icon_photo is not None:
            photo = self._fit(self._server_icon_photo, 92, 92)
            self._icon_shown = photo
            canvas.create_image(48, 48, image=photo)
            return
        if self._icon_data:
            round_rect(canvas, 2, 2, 94, 94, 16, fill=C.CARD_ALT, outline=C.BORDER)
            canvas.create_text(48, 48, text="Nuevo\na icono", fill=C.MUTED,
                               font=(self.app.theme.family, 8), justify="center")
            return
        guild = self.app.guild
        round_rect(canvas, 2, 2, 94, 94, 16, fill=C.ACCENT, outline="")
        canvas.create_text(48, 49, text=guild.initials, fill=C.WHITE,
                           font=(self.app.theme.family, 22, "bold"))

    def _render_banner_preview(self) -> None:
        canvas = self.banner_canvas
        canvas.delete("all")
        if self._banner_photo is not None:
            photo = self._fit(self._banner_photo, 216, 66)
            self._banner_shown = photo
            canvas.create_image(110, 35, image=photo)
            return
        if self._server_banner_photo is not None:
            photo = self._fit(self._server_banner_photo, 216, 66)
            self._banner_shown = photo
            canvas.create_image(110, 35, image=photo)
            return
        round_rect(canvas, 2, 2, 218, 68, 8, fill=C.INPUT, outline=C.BORDER)
        text = "Banner nuevo\n(se verá al guardar)" if self._banner_data else "Sin banner"
        canvas.create_text(110, 35, text=text, fill=C.MUTED if self._banner_data else C.FAINT,
                           font=(self.app.theme.family, 8), justify="center")

    def _pick_image(self, kind: str) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="Elegir imagen",
            filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.gif *.webp")])
        if not path:
            return
        try:
            data = image_to_data_uri(path, MAX_ICON_BYTES)
        except (ValueError, OSError) as error:
            self.toast_warn(str(error))
            return
        if kind == "icon" and path.lower().endswith(".gif") and not self.app.guild.can_use_animated_icon:
            self.toast_warn("El icono animado requiere Nivel 1 de mejoras del servidor.")
            return
        if kind == "banner" and not self.app.guild.can_use_banner:
            self.toast_warn("El banner del servidor requiere Nivel 2 de mejoras.")
            return
        photo = None
        try:
            photo = tk.PhotoImage(file=path)
        except tk.TclError:
            photo = None
        if kind == "icon":
            self._icon_data = data
            self._icon_changed = True
            self._icon_photo = photo
            self._render_icon_preview()
        else:
            self._banner_data = data
            self._banner_changed = True
            self._banner_photo = photo
            self._render_banner_preview()

    def _clear_image(self, kind: str) -> None:
        if kind == "icon":
            self._icon_data = None
            self._icon_changed = True
            self._icon_photo = None
            self._server_icon_photo = None
            self._render_icon_preview()
        else:
            self._banner_data = None
            self._banner_changed = True
            self._banner_photo = None
            self._server_banner_photo = None
            self._render_banner_preview()

    # ------------------------------------------------------------------ #
    def _save(self) -> None:
        if not self.require("MANAGE_GUILD", "editar los ajustes"):
            return
        name = self.name_var.get().strip()
        if not name:
            self.toast_warn("El nombre del servidor no puede quedar vacío.")
            return
        verification = next((value for value, label, _d in VERIFICATION_LEVELS
                             if label == self.verification_var.get()),
                            self.app.guild.verification_level)
        content_filter = next((value for value, label, _d in CONTENT_FILTER_LEVELS
                               if label == self.filter_var.get()),
                              self.app.guild.explicit_content_filter)
        notifications = next((value for value, label, _d in DEFAULT_NOTIFICATION_LEVELS
                              if label == self.notifications_var.get()),
                             self.app.guild.default_message_notifications)
        locale = next((value for value, label in LOCALES
                       if label == self.locale_var.get()), self.app.guild.preferred_locale)
        afk_timeout = next((value for value, label in AFK_TIMEOUTS
                            if label == self.afk_timeout_var.get()),
                           self.app.guild.afk_timeout)
        fields: dict[str, Any] = {
            "name": name,
            "description": self.desc_text.get("1.0", "end").strip() or None,
            "verification_level": verification,
            "explicit_content_filter": content_filter,
            "default_message_notifications": notifications,
            "preferred_locale": locale,
            "afk_timeout": afk_timeout,
            "system_channel_id": self._channel_id(self.system_channel_var.get()),
            "afk_channel_id": self._channel_id(self.afk_channel_var.get()),
        }
        if self._community and self.rules_channel_var is not None:
            fields["rules_channel_id"] = self._channel_id(self.rules_channel_var.get())
            if self.public_updates_channel_var is not None:
                fields["public_updates_channel_id"] = self._channel_id(
                    self.public_updates_channel_var.get())
        if self._icon_changed:
            fields["icon"] = self._icon_data
        if self._banner_changed and self.app.guild.can_use_banner:
            fields["banner"] = self._banner_data
        client = self.app.client
        guild_id = self.app.guild.id

        def done(_guild: Any) -> None:
            self._icon_changed = False
            self._banner_changed = False
            self._snapshot_value = self._snapshot()
            self.toast_ok("Ajustes guardados.")
            self.app.refresh_guild()

        self.run(lambda: client.update_guild(guild_id, fields), done)

    def _leave(self) -> None:
        guild = self.app.guild
        dialog = ConfirmDialog(self, "Quitar el bot del servidor",
                               f"El bot saldrá de «{guild.name}». Tu cuenta seguirá siendo "
                               "miembro, pero la app no podrá administrarlo hasta que lo "
                               "vuelvas a invitar.",
                               confirm_text="Quitar el bot", danger=True,
                               theme=self.app.theme, require_text=guild.name)
        if not dialog.show():
            return
        client = self.app.client

        def done(_result: Any) -> None:
            self.app.bot_guild_ids.discard(guild.id)
            self.app.toasts.show(f"Bot retirado de «{guild.name}».", "success")
            self.app.show_picker()
            self.app.refresh_guilds()

        self.run(lambda: client.leave_guild(guild.id), done)
