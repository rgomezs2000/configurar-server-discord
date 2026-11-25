"""Página de resumen del servidor."""
from __future__ import annotations

import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any

from ...constants import (CONTENT_FILTER_LEVELS, GUILD_FEATURES, PREMIUM_TIERS,
                          VERIFICATION_LEVELS)
from ...models import (AuditEntry, AutoModRule, Emoji, Invite, fmt_date, fmt_datetime,
                       fmt_relative, snowflake_time)
from ...report import build_server_report
from ...util import plural
from ..theme import C
from ..widgets import (Card, FlatButton, KeyValue, PageHeader, ScrollFrame,
                       StatCard, copy_to_clipboard)
from .base import Page


class DashboardPage(Page):
    key = "dashboard"
    label = "Resumen"
    glyph = "▦"

    def build(self) -> None:
        app = self.app
        self.header = PageHeader(self, app, "Resumen", "")
        self.header.pack(fill="x", padx=28, pady=(22, 0))
        self.header.button("Actualizar", self.reload, style="TButton")
        self.header.button("Copiar informe", self.copy_report)
        self.header.button("Exportar TXT…", self.export_report)
        self.header.button("Ver registro", lambda: app.shell.switch_page("moderation"),
                           style="Accent.TButton")

        self.scroll = ScrollFrame(self, bg=C.CONTENT)
        self.scroll.pack(fill="both", expand=True, padx=16, pady=(10, 6))
        self.content = self.scroll.inner
        self.content.grid_columnconfigure(0, weight=3, uniform="dash")
        self.content.grid_columnconfigure(1, weight=2, uniform="dash")

        self._rules: list[AutoModRule] = []
        self._invites: list[Invite] = []
        self._audit: list[AuditEntry] = []
        self._emojis: list[Emoji] = []
        self._extras_loaded = False
        self._extras_error = False
        self._extras_at = 0.0
        self._dirty = True

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        self.header.subtitle.configure(text=self._subtitle())
        self._render()
        if self._dirty or not self._extras_loaded:
            self._load_extras()

    def on_guild_refreshed(self) -> None:
        self._dirty = True
        self.header.subtitle.configure(text=self._subtitle())
        self._render()

    def reload(self) -> None:
        self._extras_at = 0.0
        self._extras_loaded = False
        self.app.refresh_guild()

    def _report_text(self) -> str:
        return build_server_report(
            self.app.guild, self.app.channels,
            emojis=self._emojis or None, invites=self._invites or None)

    def copy_report(self) -> None:
        copy_to_clipboard(self, self._report_text())
        self.app.toasts.show("Informe del servidor copiado.", "success")

    def export_report(self) -> None:
        safe_name = "".join(ch for ch in self.app.guild.name
                            if ch.isalnum() or ch in " -_")[:50] or "servidor"
        path = filedialog.asksaveasfilename(
            parent=self, title="Exportar informe del servidor",
            defaultextension=".txt", initialfile=f"{safe_name}.txt",
            filetypes=[("Texto", "*.txt"), ("Todos", "*.*")])
        if not path:
            return
        try:
            Path(path).write_text(self._report_text(), "utf-8")
            self.app.toasts.show("Informe exportado.", "success")
        except OSError as error:
            self.app.toasts.show(f"No se pudo exportar: {error}", "error")

    def _subtitle(self) -> str:
        guild = self.app.guild
        parts = [guild.name]
        if guild.member_count:
            parts.append(plural(guild.member_count, "miembro", "miembros"))
        if guild.presence_count:
            parts.append(f"{guild.presence_count} en línea")
        return "  ·  ".join(parts)

    def _load_extras(self) -> None:
        now = time.monotonic()
        if self._extras_loaded and now - self._extras_at < 12:
            self._dirty = False
            return
        self._extras_at = now
        app = self.app
        client = app.client
        guild_id = app.guild.id

        def work() -> tuple[list[AuditEntry], list[AutoModRule], list[Invite], list[Emoji]]:
            return (client.list_audit_logs(guild_id, limit=6),
                    client.list_automod_rules(guild_id),
                    client.list_guild_invites(guild_id),
                    client.list_emojis(guild_id))

        def done(result: tuple[list[AuditEntry], list[AutoModRule], list[Invite],
                               list[Emoji]]) -> None:
            self._audit, self._rules, self._invites, self._emojis = result
            self._extras_loaded = True
            self._extras_error = False
            self._dirty = False
            self._render()

        def failed(_error: BaseException) -> None:
            self._extras_error = True
            self._extras_loaded = True
            self._render()

        self.run(work, done, failed)

    # ------------------------------------------------------------------ #
    def _render(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()
        guild = self.app.guild
        channels = [c for c in self.app.channels if not c.is_category]

        stats = tk.Frame(self.content, bg=C.CONTENT)
        stats.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(6, 4))
        for index in range(4):
            stats.grid_columnconfigure(index, weight=1, uniform="stats")
        cards = [
            ("Miembros", str(guild.member_count or "—"), "total aproximado", C.ACCENT),
            ("En línea", str(guild.presence_count or "—"), "ahora mismo", C.GREEN),
            ("Canales", str(len(channels)), "sin contar categorías", C.YELLOW),
            ("Roles", str(len(guild.roles)), "incluido @everyone", "#eb459e"),
        ]
        for index, (label, value, hint, accent) in enumerate(cards):
            card = StatCard(stats, label, value, hint, accent=accent, theme=self.app.theme)
            card.grid(row=0, column=index, sticky="nsew", padx=6)

        self._security_card().grid(row=1, column=0, sticky="nsew", padx=8, pady=6)
        self._actions_card().grid(row=1, column=1, sticky="nsew", padx=8, pady=6)
        self._info_card().grid(row=2, column=0, sticky="nsew", padx=8, pady=6)
        self._activity_card().grid(row=2, column=1, sticky="nsew", padx=8, pady=6)
        self._benefits_card().grid(row=3, column=0, columnspan=2, sticky="nsew",
                                   padx=8, pady=6)
        self.scroll.refresh_scroll()

    # ------------------------------------------------------------------ #
    def _section(self, title: str, subtitle: str = "") -> tuple[Card, tk.Frame]:
        card = Card(self.content, padding=16)
        head = tk.Frame(card.body, bg=C.CARD)
        head.pack(fill="x", pady=(0, 10))
        tk.Label(head, text=title, bg=C.CARD, fg=C.TEXT,
                 font=self.app.theme.font(11, "bold"), anchor="w").pack(fill="x")
        if subtitle:
            tk.Label(head, text=subtitle, bg=C.CARD, fg=C.MUTED,
                     font=self.app.theme.font(8), anchor="w").pack(fill="x")
        body = tk.Frame(card.body, bg=C.CARD)
        body.pack(fill="both", expand=True)
        return card, body

    def _security_card(self) -> tk.Frame:
        guild = self.app.guild
        card, body = self._section("Estado de seguridad",
                                   "Recomendaciones para mantener el servidor a salvo")
        admin_roles = [r for r in guild.roles if r.permissions & (1 << 3) and not r.managed]
        permanent = [i for i in self._invites if i.max_age == 0]
        checks = [
            ("Verificación de miembros", "Nivel medio o superior",
             guild.verification_level >= 2, "settings"),
            ("Filtro de contenido", "Activo para todos los miembros",
             guild.explicit_content_filter >= 2, "settings"),
            ("2FA para moderación", "Obligatoria para acciones sensibles",
             guild.mfa_level == 1, "settings"),
            ("Automod", "Al menos una regla activa",
             bool([r for r in self._rules if r.enabled]), "automod"),
            ("Roles con Administrador", f"{len(admin_roles)} roles con permiso total",
             len(admin_roles) <= 1, "roles"),
            ("Invitaciones permanentes", f"{len(permanent)} sin caducidad",
             not permanent, "invites"),
        ]
        for title, description, ok, page_key in checks:
            row = tk.Frame(body, bg=C.CARD)
            row.pack(fill="x", pady=3)
            color = C.GREEN if ok else C.YELLOW
            dot = tk.Canvas(row, width=14, height=14, bg=C.CARD, highlightthickness=0)
            dot.pack(side="left", pady=3)
            dot.create_oval(2, 2, 12, 12, fill=color, outline="")
            text = tk.Frame(row, bg=C.CARD)
            text.pack(side="left", fill="x", expand=True, padx=(8, 0))
            tk.Label(text, text=title, bg=C.CARD, fg=C.TEXT,
                     font=self.app.theme.font(9, "bold"), anchor="w").pack(fill="x")
            tk.Label(text, text=description, bg=C.CARD, fg=C.MUTED,
                     font=self.app.theme.font(8), anchor="w").pack(fill="x")
            tk.Label(row, text="OK" if ok else "Revisar", bg=C.CARD,
                     fg=C.GREEN if ok else C.YELLOW,
                     font=self.app.theme.font(8, "bold")).pack(side="right", padx=(6, 0))
        if self._extras_error:
            tk.Label(body, text="No se pudieron cargar automod e invitaciones.",
                     bg=C.CARD, fg=C.FAINT, font=self.app.theme.font(8),
                     anchor="w").pack(fill="x", pady=(6, 0))
        return card

    def _actions_card(self) -> tk.Frame:
        card, body = self._section("Acciones rápidas",
                                   "Cada acción se ejecuta solo cuando la confirmas")
        actions = [
            ("Crear un canal", "Canales de texto, voz o foro", "channels"),
            ("Gestionar roles", "Permisos, colores y jerarquía", "roles"),
            ("Revisar miembros", "Buscar, aislar o expulsar", "members"),
            ("Sanciones y auditoría", "Baneos y registro de cambios", "moderation"),
            ("Ajustes del servidor", "Verificación, filtros y canales del sistema", "settings"),
        ]
        for title, description, page_key in actions:
            row = tk.Frame(body, bg=C.CARD, cursor="hand2")
            row.pack(fill="x", pady=2)
            inner = tk.Frame(row, bg=C.CARD)
            inner.pack(fill="x", padx=8, pady=7)
            tk.Label(inner, text=title, bg=C.CARD, fg=C.TEXT,
                     font=self.app.theme.font(9, "bold"), anchor="w").pack(fill="x")
            tk.Label(inner, text=description, bg=C.CARD, fg=C.MUTED,
                     font=self.app.theme.font(8), anchor="w").pack(fill="x")
            tk.Label(inner, text="→", bg=C.CARD, fg=C.FAINT,
                     font=self.app.theme.font(10, "bold")).pack(side="right")
            self._bind_hover(row, inner, lambda _e, key=page_key: self.app.shell.switch_page(key))
        return card

    @staticmethod
    def _bind_hover(row: tk.Frame, inner: tk.Frame, command: Any) -> None:
        def enter(_event: Any = None) -> None:
            for widget in (row, inner):
                widget.configure(bg=C.CARD_ALT)
            for widget in inner.winfo_children():
                widget.configure(bg=C.CARD_ALT)

        def leave(_event: Any = None) -> None:
            for widget in (row, inner):
                widget.configure(bg=C.CARD)
            for widget in inner.winfo_children():
                widget.configure(bg=C.CARD)

        for widget in [row, inner, *inner.winfo_children()]:
            widget.bind("<Enter>", enter)
            widget.bind("<Leave>", leave)
            widget.bind("<Button-1>", command)

    def _benefits_card(self) -> tk.Frame:
        guild = self.app.guild
        card, body = self._section(
            "Comunidad, mejoras y límites",
            "Lo que Discord habilita según tu cuenta y el estado del servidor")
        columns = tk.Frame(body, bg=C.CARD)
        columns.pack(fill="x")
        for index in range(3):
            columns.grid_columnconfigure(index, weight=1, uniform="benefits")

        # 1) Comunidad
        community = tk.Frame(columns, bg=C.CARD)
        community.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        self._benefit_title(community, "COMUNIDAD")
        active = guild.is_community
        row = tk.Frame(community, bg=C.CARD)
        row.pack(fill="x", pady=(4, 4))
        dot = tk.Canvas(row, width=12, height=12, bg=C.CARD, highlightthickness=0)
        dot.pack(side="left")
        dot.create_oval(2, 2, 10, 10, fill=C.GREEN if active else C.FAINT, outline="")
        tk.Label(row, text="Activa" if active else "No activada", bg=C.CARD, fg=C.TEXT,
                 font=self.app.theme.font(9, "bold")).pack(side="left", padx=(6, 0))
        if active:
            self._benefit_line(community, "Canal de reglas",
                               self._channel_name(guild.rules_channel_id))
            self._benefit_line(community, "Canal de anuncios",
                               self._channel_name(guild.public_updates_channel_id))
            self._benefit_line(community, "Descubrimiento",
                               "Sí" if "DISCOVERABLE" in guild.features else "No")
        else:
            tk.Label(community,
                     text="Sin comunidad no hay canal de reglas, anuncios, foro, media, "
                          "escenario ni descubrimiento. Actívala desde Discord.",
                     bg=C.CARD, fg=C.MUTED, font=self.app.theme.font(8),
                     wraplength=300, justify="left", anchor="w").pack(fill="x")

        # 2) Mejoras
        boosts = tk.Frame(columns, bg=C.CARD)
        boosts.grid(row=0, column=1, sticky="nsew", padx=(0, 18))
        self._benefit_title(boosts, "MEJORAS DEL SERVIDOR")
        tk.Label(boosts, text=PREMIUM_TIERS.get(guild.boost_level, "Sin mejoras"),
                 bg=C.CARD, fg=C.TEXT, font=self.app.theme.font(13, "bold"),
                 anchor="w").pack(fill="x", pady=(2, 0))
        count = guild.premium_subscription_count
        tk.Label(boosts, text=f"{count} boosts · {guild.boosts_to_next_level} para el "
                              f"siguiente nivel" if guild.boost_level < 3
                 else f"{count} boosts · nivel máximo",
                 bg=C.CARD, fg=C.MUTED, font=self.app.theme.font(8),
                 anchor="w").pack(fill="x")
        if guild.boost_level < 3:
            from ...constants import BOOST_REQUIREMENTS
            required = BOOST_REQUIREMENTS[guild.boost_level + 1]
            bar = ttk.Progressbar(boosts, maximum=required, value=min(count, required),
                                  length=170, style="Horizontal.TProgressbar")
            bar.pack(fill="x", pady=(6, 6))
        chips = tk.Frame(boosts, bg=C.CARD)
        chips.pack(fill="x", pady=(2, 0))
        for label, unlocked in (("Icono animado", guild.can_use_animated_icon),
                                ("Banner", guild.can_use_banner),
                                ("URL personalizada", guild.can_use_vanity_url)):
            tk.Label(chips, text=("✓ " if unlocked else "✕ ") + label,
                     bg=C.GREEN_SOFT if unlocked else C.CARD_ALT,
                     fg="#8ef0b4" if unlocked else C.FAINT,
                     font=self.app.theme.font(7, "bold"), padx=6, pady=2).pack(
                side="left", padx=(0, 4), pady=(0, 2))

        # 3) Cuenta y límites
        limits = tk.Frame(columns, bg=C.CARD)
        limits.grid(row=0, column=2, sticky="nsew")
        self._benefit_title(limits, "TU CUENTA Y LÍMITES")
        user = self.app.user
        nitro = bool(getattr(user, "has_nitro", False))
        row = tk.Frame(limits, bg=C.CARD)
        row.pack(fill="x", pady=(4, 2))
        tk.Label(row, text="Nitro", bg=C.CARD, fg=C.TEXT,
                 font=self.app.theme.font(9, "bold")).pack(side="left")
        tk.Label(row, text="ACTIVO" if nitro else "SIN NITRO",
                 bg=C.ACCENT if nitro else C.CARD_ALT,
                 fg=C.WHITE if nitro else C.MUTED,
                 font=self.app.theme.font(7, "bold"), padx=6, pady=1).pack(
            side="left", padx=(6, 0))
        tk.Label(limits,
                 text=("Puedes usar emojis animados en cualquier servidor y aportas 2 "
                       "boosts a los servidores que quieras." if nitro
                       else "Los emojis animados solo se muestran dentro del servidor "
                            "donde están; Nitro permite usarlos en todas partes."),
                 bg=C.CARD, fg=C.MUTED, font=self.app.theme.font(8),
                 wraplength=300, justify="left", anchor="w").pack(fill="x")
        emojis = len(self._emojis) if self._extras_loaded else guild.emoji_count
        self._benefit_line(limits, "Emojis", f"{emojis}/{guild.max_emoji_slots}")
        self._benefit_line(limits, "Stickers", f"{guild.sticker_count}/{guild.max_sticker_slots}")
        self._benefit_line(limits, "Calidad de voz", f"{guild.max_voice_bitrate // 1000} kbps")
        self._benefit_line(limits, "Subida de archivos", f"{guild.max_upload_mb} MB")
        return card

    def _benefit_title(self, parent: tk.Misc, text: str) -> None:
        tk.Label(parent, text=text, bg=C.CARD, fg=C.MUTED,
                 font=self.app.theme.font(8, "bold"), anchor="w").pack(fill="x")

    def _benefit_line(self, parent: tk.Misc, label: str, value: str) -> None:
        row = tk.Frame(parent, bg=C.CARD)
        row.pack(fill="x", pady=1)
        tk.Label(row, text=label, bg=C.CARD, fg=C.MUTED,
                 font=self.app.theme.font(8), anchor="w", width=18).pack(side="left")
        tk.Label(row, text=value, bg=C.CARD, fg=C.TEXT,
                 font=self.app.theme.font(8), anchor="w").pack(side="left")

    def _channel_name(self, channel_id: str | None) -> str:
        if not channel_id:
            return "—"
        channel = next((c for c in self.app.channels if c.id == channel_id), None)
        return f"#{channel.display_name}" if channel else "—"

    def _info_card(self) -> tk.Frame:
        guild = self.app.guild
        card, body = self._section("Información del servidor")
        created = snowflake_time(guild.id)
        from ...constants import LOCALES
        locale = dict(LOCALES).get(guild.preferred_locale, guild.preferred_locale)
        verification = next((label for value, label, _d in VERIFICATION_LEVELS
                             if value == guild.verification_level), "—")
        content_filter = next((label for value, label, _d in CONTENT_FILTER_LEVELS
                               if value == guild.explicit_content_filter), "—")
        rows = [
            ("ID", guild.id, True),
            ("Propietario", f"<@{guild.owner_id}>", False),
            ("Creado", fmt_datetime(created) if created else "—", False),
            ("Idioma", locale, False),
            ("Verificación", verification, False),
            ("Filtro explícito", content_filter, False),
            ("Mejoras", PREMIUM_TIERS.get(guild.premium_tier, "—"), False),
            ("Emojis", str(guild.emoji_count), False),
        ]
        for key, value, mono in rows:
            row = tk.Frame(body, bg=C.CARD)
            row.pack(fill="x", pady=1)
            KeyValue(row, key, value, mono=mono, theme=self.app.theme).pack(fill="x")
            if key == "ID":
                copy = tk.Label(row, text="copiar", bg=C.CARD, fg=C.LINK,
                                font=self.app.theme.font(8), cursor="hand2")
                copy.pack(side="right", padx=(6, 0))
                copy.bind("<Button-1>", lambda _e: self._copy(guild.id))
        features = [GUILD_FEATURES.get(feature, feature) for feature in guild.features]
        if features:
            chips = tk.Frame(body, bg=C.CARD)
            chips.pack(fill="x", pady=(10, 0))
            for feature in features[:8]:
                tk.Label(chips, text=feature, bg=C.CARD_ALT, fg=C.DIM,
                         font=self.app.theme.font(8), padx=7, pady=2).pack(
                    side="left", padx=(0, 5), pady=2)
        return card

    def _copy(self, value: str) -> None:
        copy_to_clipboard(self, value)
        self.toast_ok("ID copiado al portapapeles.")

    def _activity_card(self) -> tk.Frame:
        card, body = self._section("Actividad reciente",
                                   "Últimas acciones del registro de auditoría")
        if not self._extras_loaded:
            tk.Label(body, text="Cargando actividad…", bg=C.CARD, fg=C.MUTED,
                     font=self.app.theme.font(9), anchor="w").pack(fill="x", pady=8)
            return card
        if not self._audit:
            tk.Label(body, text="No hay acciones registradas todavía.", bg=C.CARD,
                     fg=C.MUTED, font=self.app.theme.font(9), anchor="w").pack(
                fill="x", pady=8)
            return card
        for entry in self._audit[:6]:
            row = tk.Frame(body, bg=C.CARD)
            row.pack(fill="x", pady=4)
            actor = entry.actor.display_name if entry.actor else "Sistema"
            tk.Label(row, text=entry.action_label, bg=C.CARD, fg=C.TEXT,
                     font=self.app.theme.font(9, "bold"), anchor="w").pack(fill="x")
            detail = f"{actor}  ·  {fmt_relative(entry.created_at)}"
            if entry.reason:
                detail += f"  ·  {entry.reason}"
            tk.Label(row, text=detail, bg=C.CARD, fg=C.MUTED, font=self.app.theme.font(8),
                     anchor="w", justify="left", wraplength=380).pack(fill="x")
        view_all = FlatButton(body, "Ver todo el registro  →", lambda: self.app.shell.switch_page("moderation"),
                              bg=C.CARD, fg=C.LINK, hover_bg=C.CARD_ALT,
                              hover_fg=C.LINK, font=self.app.theme.font(8, "bold"),
                              pady=4)
        view_all.pack(fill="x", pady=(8, 0))
        return card
