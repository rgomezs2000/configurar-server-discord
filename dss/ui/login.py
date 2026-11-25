"""Inicio de sesión con OAuth2 de Discord + token del bot para administrar."""
from __future__ import annotations

import textwrap
import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import Any

from ..constants import APP_NAME, APP_VERSION
from ..oauth import DEFAULT_CLIENT_ID, DEFAULT_REDIRECT_URI
from .theme import C
from .widgets import Card, Checkbox, ScrollFrame, Tooltip

DEV_PORTAL = "https://discord.com/developers/applications"


class LoginView(tk.Frame):
    """Pantalla de acceso.

    No hay cuentas internas ni contraseña: Discord autentica con OAuth2. El token
    del bot solo se usa para ejecutar las acciones de administración.
    """

    def __init__(self, master: tk.Misc, app: Any):
        super().__init__(master, bg=C.CONTENT)
        self.app = app
        self.remember = tk.BooleanVar(value=bool(app.settings.get("remember_token", False)))
        self.client_id = tk.StringVar(
            value=str(app.settings.get("oauth_client_id") or DEFAULT_CLIENT_ID))
        self.redirect_uri = tk.StringVar(
            value=str(app.settings.get("oauth_redirect_uri") or DEFAULT_REDIRECT_URI))
        self.bot_token = tk.StringVar(
            value=str(getattr(app, "pending_bot_token", "") or ""))
        self._busy = False
        self._build()
        note = getattr(self.app, "restore_note", None)
        if note:
            self.show_error(note, kind="warning")

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        app = self.app
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=500)
        self.grid_columnconfigure(1, weight=1)

        hero = tk.Frame(self, bg=C.RAIL, width=500)
        hero.grid(row=0, column=0, sticky="nsew")
        hero.pack_propagate(False)
        self._hero_canvas = tk.Canvas(hero, bg=C.RAIL, highlightthickness=0, bd=0)
        self._hero_canvas.pack(fill="both", expand=True)
        self._hero_canvas.bind("<Configure>", self._draw_hero)

        right = tk.Frame(self, bg=C.CONTENT)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        self._form = ScrollFrame(right, bg=C.CONTENT, center=True)
        self._form.grid(row=0, column=0, sticky="nsew")

        card = Card(self._form.inner, padding=26, border=C.BORDER)
        card.pack(padx=40, pady=24)
        body = card.body

        tk.Label(body, text="Entra con tu cuenta de Discord", bg=C.CARD, fg=C.TEXT,
                 font=app.theme.font(19, "bold"), anchor="w").pack(fill="x")
        tk.Label(body,
                 text="OAuth2 seguro: Discord confirma tu identidad en el navegador. "
                      "La app no pide ni guarda tu contraseña.",
                 bg=C.CARD, fg=C.MUTED, font=app.theme.font(9), anchor="w",
                 justify="left", wraplength=430).pack(fill="x", pady=(4, 14))

        self.login_button = ttk.Button(body, text="Continuar con Discord",
                                       style="Accent.TButton", command=self.submit)
        self.login_button.pack(fill="x", ipady=3)
        tk.Label(body, text="Se abrirá tu navegador para autorizar la app.",
                 bg=C.CARD, fg=C.FAINT, font=app.theme.font(8)).pack(pady=(4, 0))

        self.status_label = tk.Label(body, text="", bg=C.CARD, fg=C.YELLOW,
                                     font=app.theme.font(8), anchor="w",
                                     justify="left", wraplength=430)
        self.status_label.pack(fill="x", pady=(6, 0))
        self.progress = ttk.Progressbar(body, mode="indeterminate",
                                        style="Horizontal.TProgressbar")

        # -- Bot ----------------------------------------------------------- #
        bot_box = tk.Frame(body, bg=C.INPUT_ALT, highlightbackground=C.BORDER,
                           highlightthickness=1)
        bot_box.pack(fill="x", pady=(14, 0))
        self._bot_box = bot_box
        inner = tk.Frame(bot_box, bg=C.INPUT_ALT)
        inner.pack(fill="x", padx=12, pady=10)
        head = tk.Frame(inner, bg=C.INPUT_ALT)
        head.pack(fill="x")
        tk.Label(head, text="CONEXIÓN DEL BOT", bg=C.INPUT_ALT, fg=C.TEXT,
                 font=app.theme.font(8, "bold")).pack(side="left")
        tk.Label(head, text="para administrar", bg=C.INPUT_ALT, fg=C.MUTED,
                 font=app.theme.font(8)).pack(side="left", padx=(6, 0))
        tk.Label(inner,
                 text="Discord no permite moderar con el token de OAuth. El bot ejecuta "
                      "las acciones que tú confirmas; necesitas su token (solo una vez).",
                 bg=C.INPUT_ALT, fg=C.MUTED, font=app.theme.font(8), anchor="w",
                 justify="left", wraplength=400).pack(fill="x", pady=(2, 6))
        if self.bot_token.get().strip():
            tk.Label(inner,
                     text="Token fijo cargado desde la configuración cifrada del sistema.",
                     bg=C.INPUT_ALT, fg=C.GREEN, font=app.theme.font(8), anchor="w",
                     justify="left", wraplength=400).pack(fill="x", pady=(0, 4))

        token_row = tk.Frame(inner, bg=C.INPUT, highlightbackground=C.BORDER,
                             highlightthickness=1)
        token_row.pack(fill="x")
        self.bot_entry = tk.Entry(token_row, textvariable=self.bot_token, show="•",
                                  bg=C.INPUT, fg=C.TEXT, insertbackground=C.TEXT,
                                  relief="flat", bd=0, font=app.theme.font(9),
                                  highlightthickness=0, width=40)
        self.bot_entry.pack(side="left", fill="x", expand=True, padx=8, ipady=6)
        eye = tk.Label(token_row, text="ver", bg=C.INPUT, fg=C.MUTED,
                       font=app.theme.font(8), cursor="hand2")
        eye.pack(side="right", padx=(0, 4))
        eye.bind("<Button-1>", lambda _e: self._toggle_visibility())
        paste = tk.Label(token_row, text="pegar", bg=C.INPUT, fg=C.LINK,
                         font=app.theme.font(8), cursor="hand2")
        paste.pack(side="right", padx=6)
        paste.bind("<Button-1>", lambda _e: self._paste())
        self.bot_token.trace_add("write", lambda *_: self._update_button())

        self.bot_help_toggle = tk.Label(inner, text="¿Cómo consigo el token del bot?  ▾",
                                        bg=C.INPUT_ALT, fg=C.LINK,
                                        font=app.theme.font(8), cursor="hand2",
                                        anchor="w")
        self.bot_help_toggle.pack(fill="x", pady=(6, 0))
        self.bot_help_toggle.bind("<Button-1>", lambda _e: self._toggle_bot_help())
        self.bot_help = tk.Frame(inner, bg=C.INPUT_ALT)
        self._build_bot_help(self.bot_help)

        # -- Recordar / errores -------------------------------------------- #
        remember_row = tk.Frame(body, bg=C.CARD)
        remember_row.pack(fill="x", pady=(10, 0))
        Checkbox(remember_row, "Recordar sesión en este equipo",
                 variable=self.remember, bg=C.CARD, font=app.theme.font(9)).pack(
            side="left")
        tk.Label(remember_row, text=f"cifrado: {self.app.tokens.method_label()}",
                 bg=C.CARD, fg=C.FAINT, font=app.theme.font(8)).pack(side="right")

        self.error_label = tk.Label(body, text="", bg=C.CARD, fg=C.RED,
                                    font=app.theme.font(9), anchor="w", justify="left",
                                    wraplength=430)
        self.error_label.pack(fill="x", pady=(8, 0))

        self.cancel_button = ttk.Button(body, text="Cancelar", style="Ghost.TButton",
                                        command=self.cancel)

        demo_row = tk.Frame(body, bg=C.CARD)
        demo_row.pack(fill="x", pady=(10, 0))
        demo = tk.Label(demo_row, text="Explorar con datos de demostración →",
                        bg=C.CARD, fg=C.LINK, font=app.theme.font(9), cursor="hand2")
        demo.pack()
        demo.bind("<Button-1>", lambda _e: self.app.start_demo())
        Tooltip(demo, "Abre la app con servidores inventados, sin OAuth ni bot.")

        # -- Configuración avanzada ---------------------------------------- #
        self.config_toggle = tk.Label(body, text="Configuración de OAuth  ▾",
                                      bg=C.CARD, fg=C.MUTED,
                                      font=app.theme.font(8), cursor="hand2")
        self.config_toggle.pack(pady=(12, 0))
        self.config_toggle.bind("<Button-1>", lambda _e: self._toggle_config())
        self.config = tk.Frame(body, bg=C.CARD)
        self._build_config(self.config)

        footer = tk.Frame(body, bg=C.CARD)
        footer.pack(fill="x", pady=(12, 0))
        tk.Label(footer, text=f"{APP_NAME} {APP_VERSION} · OAuth2 + bot · "
                              "sin telemetría",
                 bg=C.CARD, fg=C.FAINT, font=app.theme.font(8)).pack()

        self._update_button()
        self.bot_entry.focus_set()

    def _build_bot_help(self, parent: tk.Misc) -> None:
        app = self.app
        steps = [
            "1. Entra en discord.com/developers/applications y abre tu aplicación.",
            "2. En «Bot» pulsa «Reset Token» y copia el token (solo se muestra una vez).",
            "3. En «Bot → Privileged Gateway Intents» activa «Server Members Intent» "
            "(necesario para listar miembros).",
            "4. Invita el bot a tus servidores: dentro de la app, al abrir un servidor "
            "sin bot, tendrás un enlace de invitación.",
            "5. Pega el token aquí. Se guarda cifrado y no es tu contraseña.",
        ]
        for step in steps:
            tk.Label(parent, text=step, bg=C.INPUT_ALT, fg=C.MUTED,
                     font=app.theme.font(8), anchor="w", justify="left",
                     wraplength=400).pack(fill="x")
        link = tk.Label(parent, text="Abrir el portal de desarrolladores ↗",
                        bg=C.INPUT_ALT, fg=C.LINK, font=app.theme.font(8),
                        cursor="hand2", anchor="w")
        link.pack(fill="x", pady=(4, 0))
        link.bind("<Button-1>", lambda _e: webbrowser.open(DEV_PORTAL))

    def _build_config(self, parent: tk.Misc) -> None:
        app = self.app
        tk.Label(parent, text="CLIENT ID", bg=C.CARD, fg=C.MUTED,
                 font=app.theme.font(8, "bold"), anchor="w").pack(fill="x", pady=(6, 2))
        ttk.Entry(parent, textvariable=self.client_id).pack(fill="x")
        tk.Label(parent, text="REDIRECT URI (debe coincidir con el portal)", bg=C.CARD,
                 fg=C.MUTED, font=app.theme.font(8, "bold"), anchor="w").pack(
            fill="x", pady=(8, 2))
        ttk.Entry(parent, textvariable=self.redirect_uri).pack(fill="x")
        tk.Label(parent,
                 text="Añade esta URL exacta en Developer Portal → OAuth2 → Redirects. "
                      "El client secret no se usa ni se guarda: el login es PKCE.",
                 bg=C.CARD, fg=C.FAINT, font=app.theme.font(7), anchor="w",
                 justify="left", wraplength=420).pack(fill="x", pady=(4, 0))
        link = tk.Label(parent, text="Abrir OAuth2 del portal ↗", bg=C.CARD,
                        fg=C.LINK, font=app.theme.font(8), cursor="hand2", anchor="w")
        link.pack(fill="x", pady=(6, 0))
        link.bind("<Button-1>", lambda _e: webbrowser.open(
            f"{DEV_PORTAL}/{self.client_id.get().strip()}/oauth2"))

    # ------------------------------------------------------------------ #
    def _draw_hero(self, event: Any = None) -> None:
        canvas = self._hero_canvas
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 10 or height < 10:
            return
        top, bottom = (0x1d, 0x1e, 0x26), (0x0e, 0x0f, 0x13)
        for y in range(0, height):
            ratio = y / max(1, height)
            color = "#%02x%02x%02x" % tuple(
                int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
            canvas.create_line(0, y, width, y, fill=color)

        app = self.app
        family = app.theme.family
        canvas.create_rectangle(44, 46, 80, 82, fill=C.ACCENT, outline="")
        canvas.create_text(62, 64, text="#", fill=C.WHITE, font=(family, 15, "bold"))
        canvas.create_text(92, 59, text="PANEL DE ADMINISTRACIÓN", anchor="w",
                           fill="#8b8f9b", font=(family, 8, "bold"))
        canvas.create_text(92, 74, text="Discord Server Studio", anchor="w",
                           fill="#6d7280", font=(family, 8))
        canvas.create_line(44, 104, width - 44, 104, fill="#262833")

        title_y = height * 0.27
        canvas.create_text(44, title_y, text="Tu cuenta,\ntus servidores.", anchor="nw",
                           fill=C.WHITE, font=(family, 31, "bold"), justify="left")
        canvas.create_text(44, title_y + 104,
                           text="Entra con OAuth2 y administra\ncon permisos reales.",
                           anchor="nw", fill="#c9ccd4", font=(family, 11), justify="left")

        bullets = [
            "OAuth2: Discord valida tu identidad, sin contraseña.",
            "Solo servidores donde eres propietario o administrador.",
            "El bot ejecuta cada cambio que tú confirmas.",
        ]
        y = max(title_y + 190, height * 0.58)
        for text in bullets:
            canvas.create_text(44, y - 1, text="▸", anchor="nw", fill=C.ACCENT,
                               font=(family, 10, "bold"))
            for line in textwrap.wrap(text, width=40):
                canvas.create_text(62, y, text=line, anchor="nw", fill="#a7abb6",
                                   font=(family, 9))
                y += 17
            y += 12
        canvas.create_text(44, height - 26, text=f"Python + Tkinter · {APP_VERSION} · "
                                                 "sin telemetría",
                           anchor="w", fill="#5f626c", font=(family, 8))

    # ------------------------------------------------------------------ #
    def _toggle_visibility(self) -> None:
        hidden = self.bot_entry.cget("show") == "•"
        self.bot_entry.configure(show="" if hidden else "•")

    def _paste(self) -> None:
        try:
            text = self.clipboard_get()
        except tk.TclError:
            return
        self.bot_token.set(text.strip())
        self.bot_entry.icursor("end")

    def _toggle_bot_help(self) -> None:
        if self.bot_help.winfo_ismapped():
            self.bot_help.pack_forget()
            self.bot_help_toggle.configure(text="¿Cómo consigo el token del bot?  ▾")
        else:
            self.bot_help.pack(fill="x", pady=(4, 0))
            self.bot_help_toggle.configure(text="¿Cómo consigo el token del bot?  ▴")

    def _toggle_config(self) -> None:
        if self.config.winfo_ismapped():
            self.config.pack_forget()
            self.config_toggle.configure(text="Configuración de OAuth  ▾")
        else:
            self.config.pack(fill="x")
            self.config_toggle.configure(text="Configuración de OAuth  ▴")

    def _update_button(self) -> None:
        self.login_button.configure(state="disabled" if self._busy else "normal")

    def set_busy(self, busy: bool, text: str = "Conectando con Discord…") -> None:
        self._busy = busy
        if busy:
            self.status_label.configure(text=text)
            self.progress.pack(fill="x", pady=(4, 0), before=self._bot_box)
            self.progress.start(12)
            self.cancel_button.pack(fill="x", pady=(6, 0), before=self.error_label)
            self.login_button.configure(text="Esperando a Discord…")
        else:
            self.progress.stop()
            self.progress.pack_forget()
            self.cancel_button.pack_forget()
            self.status_label.configure(text="")
            self.login_button.configure(text="Continuar con Discord")
        self._update_button()

    def show_error(self, message: str, kind: str = "error") -> None:
        color = C.RED if kind == "error" else C.YELLOW
        self.error_label.configure(text=message, fg=color)

    def cancel(self) -> None:
        self.app.cancel_oauth()
        self.set_busy(False)
        self.show_error("Autorización cancelada.", kind="warning")
        self._update_button()

    def submit(self) -> None:
        if self._busy:
            return
        client_id = self.client_id.get().strip()
        redirect = self.redirect_uri.get().strip()
        token = self.bot_token.get().strip().strip('"').strip("'")
        if token.lower().startswith("bot "):
            token = token[4:].strip()
        if not client_id.isdigit():
            self.show_error("El Client ID debe ser numérico. Actívalo en Configuración de OAuth.")
            return
        if not redirect.startswith("http://127.0.0.1"):
            self.show_error("El redirect URI debe empezar por http://127.0.0.1.")
            return
        if not token:
            self.show_error("Pega el token del bot para poder administrar.")
            return
        if token.count(".") < 2 and len(token) < 40:
            self.show_error("Ese token de bot no parece válido.")
            return
        self.app.settings.set("oauth_client_id", client_id)
        self.app.settings.set("oauth_redirect_uri", redirect)
        self.app.settings.save()
        self.app.begin_oauth(client_id, redirect, token, bool(self.remember.get()))
