"""Ventana principal de Discord Server Studio (Python + Tkinter)."""
from __future__ import annotations

import os
import time
import traceback
import webbrowser
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

from ..api import DiscordClient
from ..constants import APP_NAME, LIVE_SYNC_SECONDS, PERMISSION_BY_KEY
from ..demo import DemoClient
from ..errors import DiscordError
from ..models import (Channel, Guild, GuildSummary, Member, User,
                      channel_permissions, effective_permissions)
from ..oauth import (DEFAULT_CLIENT_ID, DEFAULT_REDIRECT_URI, OAuthError, OAuthFlow,
                     OAuthResult, OAuthTokens, fetch_identity, refresh_tokens)
from ..store import Settings, TokenStore
from ..tasks import TaskRunner
from ..util import plural
from .images import ImageCache
from .login import LoginView
from .pages import PAGE_BY_KEY
from .picker import GuildPickerView
from .shell import ShellView
from .theme import C, Theme, enable_dark_titlebar, enable_dpi_awareness
from .widgets import ConfirmDialog, Modal, ToastManager, copy_to_clipboard


class App(tk.Tk):
    def __init__(self) -> None:
        enable_dpi_awareness()
        super().__init__()
        self.settings = Settings()
        self.tokens = TokenStore()
        self.bot_tokens = TokenStore.for_bot()

        self.title(APP_NAME)
        self.configure(bg=C.CONTENT)
        self.minsize(1024, 640)
        self._apply_geometry()

        self.theme = Theme(self)
        self.theme.apply()
        enable_dark_titlebar(self)
        self._apply_icon()

        self.tasks = TaskRunner(self)
        self.toasts = ToastManager(self)
        self.images = ImageCache(self)

        self.client_id = str(self.settings.get("oauth_client_id") or DEFAULT_CLIENT_ID)
        self.redirect_uri = str(
            self.settings.get("oauth_redirect_uri") or DEFAULT_REDIRECT_URI)
        self.oauth_tokens: OAuthTokens | None = None
        self.bot_token = ""
        self.pending_bot_token = self._load_fixed_bot_token()
        self.bot_user: User | None = None
        self.bot_guild_ids: set[str] = set()
        self.bot_guild_ids_known = False
        self._oauth_flow: OAuthFlow | None = None
        self._oauth_after: str | None = None
        self._pending_bot: tuple[DiscordClient, User, list[GuildSummary]] | None = None
        self._pending_remember = True

        self.client: Any = None
        self.user: Any = None
        self.guilds: list[GuildSummary] = []
        self.hidden_guilds: int = 0
        self.guild: Guild | None = None
        self.channels: list[Channel] = []
        self.my_member: Member | None = None
        self.permissions: int = 0
        self.session_kind: str = ""
        self.demo: bool = False
        self.restore_note: str | None = None
        self.shell: ShellView | None = None

        self._view: tk.Widget | None = None
        self._busy_frame: tk.Frame | None = None
        self._refreshing = False
        self._refresh_pending = False
        self._refreshing_guilds = False
        self.live_status = "live" if self.settings.get("live_sync", True) else "off"
        self._live_after: str | None = None
        self._live_cycle = 0

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._bind_shortcuts()
        self.show_login()
        if os.environ.get("DSS_DEMO") == "1":
            self.after(250, self.start_demo)
        else:
            self.after(150, self._try_restore)
        self.after(1200, self._schedule_live)

    # ------------------------------------------------------------------ #
    @property
    def root(self) -> "App":
        return self

    def _apply_icon(self) -> None:
        assets = Path(__file__).resolve().parent / "assets"
        png = assets / "app.png"
        ico = assets / "app.ico"
        try:
            if png.exists():
                self._icon_image = tk.PhotoImage(file=str(png))
                self.iconphoto(True, self._icon_image)
        except tk.TclError:
            pass
        try:
            if ico.exists() and self.tk.call("tk", "windowingsystem") == "win32":
                self.iconbitmap(default=str(ico))
        except tk.TclError:
            pass

    def _apply_geometry(self) -> None:
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        saved = str(self.settings.get("window_geometry") or "")
        if saved:
            try:
                size = saved.split("+")[0]
                width, height = (int(part) for part in size.split("x"))
                if width <= screen_w and height <= screen_h:
                    self.geometry(saved)
                    return
            except (ValueError, tk.TclError):
                pass
        width = min(1400, max(980, screen_w - 80))
        height = min(900, max(620, screen_h - 110))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _bind_shortcuts(self) -> None:
        self.bind_all("<Control-q>", lambda _e: self.on_close())
        self.bind_all("<F5>", lambda _e: self._shortcut_refresh())
        self.bind_all("<Control-Shift-KeyPress-S>", lambda _e: self.show_picker())
        shortcuts = ["dashboard", "channels", "roles", "members", "moderation",
                     "automod", "invites", "emojis", "webhooks"]
        for index, key in enumerate(shortcuts, start=1):
            self.bind_all(f"<Control-Key-{index}>",
                          lambda _e, k=key: self.shell and self.shell.switch_page(k))

    def _shortcut_refresh(self) -> None:
        if self.shell:
            self.refresh_guild(silent=False)
        elif isinstance(self._view, GuildPickerView):
            self.refresh_guilds()

    # ------------------------------------------------------------------ #
    def _load_fixed_bot_token(self) -> str:
        saved = self.bot_tokens.load()
        return saved[0] if saved else ""

    def _save_fixed_bot_token(self) -> None:
        if self.bot_token:
            self.bot_tokens.save(self.bot_token, "bot")

    def _set_view(self, view: tk.Widget) -> None:
        if self._view is not None:
            try:
                self._view.destroy()
            except tk.TclError:
                pass
        self._view = view
        view.pack(fill="both", expand=True)

    def _reset_session(self) -> None:
        self.client = None
        self.user = None
        self.guilds = []
        self.hidden_guilds = 0
        self.guild = None
        self.channels = []
        self.my_member = None
        self.permissions = 0
        self.session_kind = ""
        self.demo = False
        self.shell = None
        self.images.enabled = True
        self.live_status = "off"
        self.oauth_tokens = None
        self.bot_token = ""
        self.bot_user = None
        self.bot_guild_ids = set()
        self.bot_guild_ids_known = False
        self._pending_bot = None
        self._refreshing_guilds = False
        if self._oauth_after is not None:
            try:
                self.after_cancel(self._oauth_after)
            except tk.TclError:
                pass
            self._oauth_after = None
        if self._oauth_flow is not None:
            try:
                self._oauth_flow.cancel()
            except Exception:  # noqa: BLE001
                pass
            self._oauth_flow = None

    # ------------------------------------------------------------------ #
    def show_login(self, note: str | None = None) -> None:
        self.restore_note = note
        self._reset_session()
        if not self.pending_bot_token:
            self.pending_bot_token = self._load_fixed_bot_token()
        self._set_view(LoginView(self, self))

    def show_picker(self) -> None:
        self.shell = None
        self._set_view(GuildPickerView(self, self))

    # ------------------------------------------------------------------ #
    # Sesión OAuth2 + bot
    # ------------------------------------------------------------------ #
    def begin_oauth(self, client_id: str, redirect_uri: str, bot_token: str,
                    remember: bool) -> None:
        self.client_id = client_id.strip()
        self.redirect_uri = redirect_uri.strip()
        self.bot_token = (bot_token.strip() or self.pending_bot_token.strip())
        self._pending_remember = remember
        view = self._view
        if not self.bot_token:
            if isinstance(view, LoginView):
                view.set_busy(False)
                view.show_error("No hay token del bot configurado.")
            return
        if isinstance(view, LoginView):
            view.set_busy(True, "Validando el token del bot…")
        bot_client = DiscordClient(self.bot_token, "bot")

        def work() -> tuple[DiscordClient, User, list[GuildSummary]]:
            bot_user = bot_client.login()
            if not bot_user.bot:
                raise DiscordError("El token no pertenece a un bot.")
            bot_guilds = bot_client.list_guilds()
            return bot_client, bot_user, bot_guilds

        def done(result: tuple[DiscordClient, User, list[GuildSummary]]) -> None:
            self._pending_bot = result
            self._save_fixed_bot_token()
            self.pending_bot_token = self.bot_token
            self._start_oauth_flow()

        def failed(error: BaseException) -> None:
            if isinstance(view, LoginView):
                view.set_busy(False)
                view.show_error(f"No se pudo conectar el bot: {error}")
            else:
                self.report_error(error)

        self.run_task(work, done, failed, quiet=True)

    def _start_oauth_flow(self) -> None:
        view = self._view
        if not isinstance(view, LoginView):
            return
        view.set_busy(True, "Esperando autorización en el navegador…")
        self._oauth_flow = OAuthFlow(self.client_id, self.redirect_uri)
        try:
            url = self._oauth_flow.start()
        except OAuthError as error:
            self._oauth_flow = None
            self._pending_bot = None
            view.set_busy(False)
            view.show_error(str(error))
            return
        webbrowser.open(url)
        self._poll_oauth()

    def _poll_oauth(self) -> None:
        self._oauth_after = None
        flow = self._oauth_flow
        if flow is None:
            return
        try:
            result = flow.poll()
        except OAuthError as error:
            self._oauth_flow = None
            self._pending_bot = None
            view = self._view
            if isinstance(view, LoginView):
                view.set_busy(False)
                view.show_error(str(error))
            return
        if result is None:
            try:
                self._oauth_after = self.after(300, self._poll_oauth)
            except tk.TclError:
                pass
            return
        self._oauth_flow = None
        self._oauth_ok(result)

    def cancel_oauth(self) -> None:
        if self._oauth_after is not None:
            try:
                self.after_cancel(self._oauth_after)
            except tk.TclError:
                pass
            self._oauth_after = None
        if self._oauth_flow is not None:
            try:
                self._oauth_flow.cancel()
            except Exception:  # noqa: BLE001
                pass
            self._oauth_flow = None
        self._pending_bot = None

    @staticmethod
    def _managed_guilds(guilds: list[GuildSummary]) -> list[GuildSummary]:
        """Solo servidores propios o con permisos administrativos (Admin/Gestionar servidor)."""
        visible = [guild for guild in guilds if guild.can_manage]
        visible.sort(key=lambda guild: (
            0 if guild.owner else
            (1 if (guild.permissions == -1 or guild.permissions & (1 << 3)) else 2),
            guild.name.lower(),
        ))
        return visible

    def _oauth_ok(self, result: OAuthResult) -> None:
        if self._pending_bot is None:
            return
        bot_client, bot_user, bot_guilds = self._pending_bot
        self._pending_bot = None
        self.pending_bot_token = ""
        self.oauth_tokens = result.tokens
        self.client = bot_client
        self.bot_user = bot_user
        self.bot_guild_ids = {guild.id for guild in bot_guilds}
        self.bot_guild_ids_known = True
        self.user = result.user
        visible = self._managed_guilds(result.guilds)
        self.hidden_guilds = len(result.guilds) - len(visible)
        self.guilds = visible
        self.session_kind = "oauth"
        self.demo = False
        self.images.enabled = True
        self.settings.set("remember_token", self._pending_remember)
        self.settings.set("token_kind", "oauth")
        self.settings.save()
        if self._pending_remember:
            self._save_session()
        else:
            self.tokens.clear()
        self.show_picker()
        self.set_live_status("live" if self.settings.get("live_sync", True) else "off")
        noun = "servidor administrado" if len(visible) == 1 else "servidores administrados"
        hidden = (f" · {self.hidden_guilds} "
                  f"{'oculto' if self.hidden_guilds == 1 else 'ocultos'} sin permisos"
                  if self.hidden_guilds else "")
        self.toasts.show(f"Conectado como {result.user.display_name} · "
                         f"bot {self.bot_user.username if self.bot_user else 'listo'} · "
                         f"{len(visible)} {noun}{hidden}.", "success")
        if self._live_after is not None:
            try:
                self.after_cancel(self._live_after)
            except tk.TclError:
                pass
            self._live_after = None
        self._schedule_live()

    def _save_session(self) -> None:
        if self.oauth_tokens is None or not self.bot_token:
            return
        payload = {
            "oauth": self.oauth_tokens.to_dict(),
            "bot_token": self.bot_token,
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
        }
        if not self.tokens.save_session(payload):
            self.toasts.show("No se pudo guardar la sesión cifrada en este equipo.",
                             "warning")

    def start_demo(self) -> None:
        self._reset_session()
        client = DemoClient()
        self.client = client
        self.user = client.login()
        all_guilds = client.list_guilds()
        visible = self._managed_guilds(all_guilds)
        self.hidden_guilds = len(all_guilds) - len(visible)
        self.guilds = visible
        self.session_kind = "demo"
        self.demo = True
        self.images.enabled = False
        self.pending_bot_token = self._load_fixed_bot_token()
        self.show_picker()
        self.set_live_status("live" if self.settings.get("live_sync", True) else "off")

    def _try_restore(self) -> None:
        if os.environ.get("DSS_DEMO") == "1":
            return
        payload = self.tokens.load_session()
        if not payload or not isinstance(payload.get("oauth"), dict):
            return
        bot_token = str(payload.get("bot_token") or "")
        if not bot_token:
            return
        self.client_id = str(payload.get("client_id") or self.client_id)
        self.redirect_uri = str(payload.get("redirect_uri") or self.redirect_uri)
        self.bot_token = bot_token
        self._pending_remember = True
        tokens = OAuthTokens.from_dict(payload["oauth"])
        self.oauth_tokens = tokens
        if tokens.expired:
            self.pending_bot_token = bot_token
            self.show_login(note="La sesión OAuth caducó. Vuelve a entrar con Discord; "
                                 "el token del bot ya está rellenado.")
            return
        view = self._view
        if isinstance(view, LoginView):
            view.set_busy(True, "Restaurando sesión…")

        def work() -> tuple[OAuthTokens, User, list[GuildSummary],
                            DiscordClient, User, list[GuildSummary]]:
            user, guilds = fetch_identity(tokens.access_token)
            bot_client = DiscordClient(bot_token, "bot")
            bot_user = bot_client.login()
            bot_guilds = bot_client.list_guilds()
            return tokens, user, guilds, bot_client, bot_user, bot_guilds

        def done(result: tuple[OAuthTokens, User, list[GuildSummary],
                               DiscordClient, User, list[GuildSummary]]) -> None:
            session, user, guilds, bot_client, bot_user, bot_guilds = result
            self.oauth_tokens = session
            self._pending_bot = (bot_client, bot_user, bot_guilds)
            self._oauth_ok(OAuthResult(session, user, guilds))

        def failed(error: BaseException) -> None:
            self.pending_bot_token = bot_token
            view2 = self._view
            if isinstance(view2, LoginView):
                view2.set_busy(False)
            note = ("La sesión OAuth caducó. Vuelve a entrar con Discord; el token del bot "
                    "ya está rellenado." if tokens.expired else
                    f"No se pudo restaurar la sesión: {error}")
            self.show_login(note=note)

        self.run_task(work, done, failed, quiet=True)

    # ------------------------------------------------------------------ #
    def open_guild(self, summary: GuildSummary) -> None:
        if self.client is None:
            return
        if not any(guild.id == summary.id for guild in self.guilds):
            self.toasts.show(
                "Ese servidor no está disponible: solo se muestran servidores donde eres "
                "propietario o tienes permisos administrativos.", "warning", timeout=7000)
            return
        if self.guild is not None and self.guild.id == summary.id and self.shell is not None:
            self.shell.switch_page(str(self.settings.get("last_page") or "dashboard"))
            return
        self.set_busy(True, f"Abriendo {summary.name}…")
        client = self.client

        def work() -> tuple[Guild, list[Channel], Member | None]:
            guild = client.get_guild(summary.id)
            channels = client.list_channels(summary.id)
            member: Member | None = None
            if self.user is not None:
                try:
                    member = client.get_member(summary.id, self.user.id)
                except DiscordError:
                    member = None
            return guild, channels, member

        def done(result: tuple[Guild, list[Channel], Member | None]) -> None:
            self._guild_ready(summary, *result)

        def failed(error: BaseException) -> None:
            self.set_busy(False)
            if isinstance(error, DiscordError) and error.status in (403, 404, 50001):
                if (self.bot_guild_ids_known
                        and (summary.id not in self.bot_guild_ids or error.status == 404)):
                    self._show_bot_missing(summary)
                else:
                    self.toasts.show(
                        f"{error}\nEl bot está en el servidor, pero le faltan permisos.",
                        "error", timeout=9000)
            else:
                self.report_error(error)

        self.run_task(work, done, failed, quiet=True)

    def _show_bot_missing(self, summary: GuildSummary) -> None:
        if self.client is None:
            return
        url = self.client.invite_url_for_guild(summary.id)
        modal = Modal(self, "Falta el bot en este servidor", width=580, theme=self.theme,
                      subtitle=f"«{summary.name}»")
        tk.Label(modal.body,
                 text="OAuth inicia sesión con tu cuenta, pero las acciones las ejecuta el "
                      "bot. Para administrar este servidor, invítalo con el enlace de abajo "
                      "(permisos recomendados) y vuelve a pulsar «Actualizar».",
                 bg=C.CARD, fg=C.DIM, font=self.theme.font(9), wraplength=520,
                 justify="left", anchor="w").pack(fill="x")
        if url:
            tk.Label(modal.body, text=url, bg=C.INPUT, fg=C.MUTED,
                     font=(self.theme.mono_family, 8), wraplength=520, justify="left",
                     anchor="w", padx=8, pady=8).pack(fill="x", pady=(10, 0))
            modal.add_button("Copiar enlace",
                             lambda: copy_to_clipboard(modal, url))
            modal.add_button("Abrir invitación", lambda: webbrowser.open(url),
                             style="Accent.TButton")
        else:
            tk.Label(modal.body, text="El bot no tiene una URL de invitación disponible.",
                     bg=C.CARD, fg=C.YELLOW, font=self.theme.font(9)).pack(
                fill="x", pady=(10, 0))
        modal.add_button("Cerrar", modal.close)
        modal.show()

    def _guild_ready(self, summary: GuildSummary, guild: Guild,
                     channels: list[Channel], member: Member | None) -> None:
        self.guild = guild
        self.channels = channels
        self.my_member = member
        self.permissions = self._compute_permissions(summary)
        self.settings.set("last_guild_id", guild.id)
        self.shell = ShellView(self, self)
        self._set_view(self.shell)
        self.shell.update_badges()
        self.set_live_status("live" if self.settings.get("live_sync", True) else "off")
        self.set_busy(False)
        self.toasts.show(f"Servidor «{guild.name}» cargado.", "success")

    def _compute_permissions(self, summary: GuildSummary) -> int:
        if self.guild is None:
            return summary.permissions
        if summary.owner or summary.permissions == -1:
            return -1
        if summary.permissions & (1 << 3):
            return -1
        user_id = getattr(self.user, "id", "")
        permissions = effective_permissions(self.guild, self.my_member, user_id)
        return permissions | summary.permissions

    # ------------------------------------------------------------------ #
    # Sincronización automática
    # ------------------------------------------------------------------ #
    def _schedule_live(self) -> None:
        if self._live_after is not None:
            return
        if not self.settings.get("live_sync", True):
            self.set_live_status("off")
            return
        try:
            self._live_after = self.after(int(LIVE_SYNC_SECONDS * 1000), self._live_tick)
        except tk.TclError:
            self._live_after = None

    def _live_tick(self) -> None:
        self._live_after = None
        if not self.settings.get("live_sync", True):
            self.set_live_status("off")
            return
        if (self.state() == "iconic" or self.grab_current() is not None
                or self._busy_frame is not None):
            self.set_live_status("paused")
            self._schedule_live()
            return
        if isinstance(self._view, GuildPickerView):
            if self.client is None and self.oauth_tokens is None:
                self._schedule_live()
                return
            if not self._refreshing_guilds:
                self._live_cycle += 1
                self.refresh_guilds(silent=True, live=True)
            self._schedule_live()
            return
        if self.client is None or self.shell is None or self.guild is None:
            self._schedule_live()
            return
        if self._refreshing:
            self._schedule_live()
            return
        self._live_cycle += 1
        if self._live_cycle % 5 == 0:
            self.refresh_guilds(silent=True)
        self.refresh_guild(silent=True, live=True)
        self._schedule_live()

    def set_live_status(self, state: str) -> None:
        self.live_status = state
        if isinstance(self._view, GuildPickerView):
            try:
                self._view.set_live_status(state)
            except tk.TclError:
                pass
        if self.shell is not None:
            try:
                self.shell.set_live_status(state)
            except tk.TclError:
                pass

    def toggle_live(self) -> None:
        enabled = not bool(self.settings.get("live_sync", True))
        self.settings.set("live_sync", enabled)
        self.settings.save()
        if enabled:
            self.set_live_status("live")
            self._schedule_live()
            self.toasts.show("Sincronización automática activada.", "info")
        else:
            if self._live_after is not None:
                try:
                    self.after_cancel(self._live_after)
                except tk.TclError:
                    pass
                self._live_after = None
            self.set_live_status("off")
            self.toasts.show("Sincronización automática desactivada. Usa F5 o «Actualizar».",
                             "info")

    # ------------------------------------------------------------------ #
    def refresh_guild(self, silent: bool = True, live: bool = False) -> None:
        if self.guild is None or self.client is None or self.shell is None:
            return
        if self._refreshing:
            self._refresh_pending = True
            return
        self._refreshing = True
        guild_id = self.guild.id
        summary = next((g for g in self.guilds if g.id == guild_id), None)
        client = self.client

        def work() -> tuple[Guild, list[Channel], Member | None]:
            guild = client.get_guild(guild_id)
            channels = client.list_channels(guild_id)
            member: Member | None = None
            if self.user is not None:
                try:
                    member = client.get_member(guild_id, self.user.id)
                except DiscordError:
                    member = None
            return guild, channels, member

        def done(result: tuple[Guild, list[Channel], Member | None]) -> None:
            self._refreshing = False
            self.guild, self.channels, self.my_member = result
            if summary is not None:
                self.permissions = self._compute_permissions(summary)
            if self.shell is not None:
                if live:
                    self.shell.on_guild_refreshed()
                    outcome = self.shell.live_update()
                    if outcome == "editing":
                        self.set_live_status("editing")
                    elif outcome == "error":
                        self.set_live_status("error")
                    else:
                        self.set_live_status("live")
                else:
                    self.shell.on_guild_refreshed()
                    if not silent:
                        self.shell.refresh_current()
                        self.set_live_status(
                            "live" if self.settings.get("live_sync", True) else "off")
            if not silent:
                self.toasts.show("Datos del servidor actualizados.", "success")
            if self._refresh_pending:
                self._refresh_pending = False
                self.refresh_guild(silent=True, live=live)

        def failed(error: BaseException) -> None:
            self._refreshing = False
            if live:
                self.set_live_status("error")
            else:
                self.report_error(error)

        self.run_task(work, done, failed, quiet=True)

    def refresh_guilds(self, silent: bool = False, live: bool = False) -> None:
        if self._refreshing_guilds:
            return
        if self.oauth_tokens is None:
            if self.client is None:
                return
            self._refreshing_guilds = True

            def demo_done(guilds: list[GuildSummary]) -> None:
                self._refreshing_guilds = False
                self._apply_guild_list(guilds, None, silent, live)

            def demo_failed(error: BaseException) -> None:
                self._refreshing_guilds = False
                if live:
                    self.set_live_status("error")
                else:
                    self.report_error(error)

            self.run_task(lambda: self.client.list_guilds(), demo_done, demo_failed,
                          quiet=True)
            return
        self._refreshing_guilds = True

        def work() -> tuple[OAuthTokens, User, list[GuildSummary],
                            list[GuildSummary] | None]:
            session = self.oauth_tokens
            if session.expired and session.refresh_token:
                session = refresh_tokens(self.client_id, session.refresh_token)
            user, guilds = fetch_identity(session.access_token)
            bot_guilds = self.client.list_guilds() if self.client is not None else None
            return session, user, guilds, bot_guilds

        def done(result: tuple[OAuthTokens, User, list[GuildSummary],
                               list[GuildSummary] | None]) -> None:
            self._refreshing_guilds = False
            session, user, guilds, bot_guilds = result
            self.oauth_tokens = session
            self.user = user
            if isinstance(self._view, GuildPickerView):
                self._view.update_user(user)
            self._apply_guild_list(guilds, bot_guilds, silent, live)
            if live:
                self.set_live_status("live")

        def failed(error: BaseException) -> None:
            self._refreshing_guilds = False
            if live:
                self.set_live_status("error")
            else:
                self.report_error(error)

        self.run_task(work, done, failed, quiet=True)

    def _apply_guild_list(self, guilds: list[GuildSummary],
                          bot_guilds: list[GuildSummary] | None, silent: bool,
                          live: bool = False) -> None:
        previous_bot = set(self.bot_guild_ids)
        bot_changed = False
        if bot_guilds is not None:
            fresh_bot = {guild.id for guild in bot_guilds}
            bot_changed = not self.bot_guild_ids_known or fresh_bot != self.bot_guild_ids
            self.bot_guild_ids = fresh_bot
            self.bot_guild_ids_known = True
        visible = self._managed_guilds(guilds)
        hidden = len(guilds) - len(visible)
        previous = [(guild.id, guild.name, guild.icon, guild.owner,
                     guild.permissions, guild.member_count) for guild in self.guilds]
        current = [(guild.id, guild.name, guild.icon, guild.owner,
                    guild.permissions, guild.member_count) for guild in visible]
        self.hidden_guilds = hidden
        self.guilds = visible
        if previous != current or bot_changed:
            if isinstance(self._view, GuildPickerView):
                self._view.reload()
            if self.shell is not None:
                self.shell.refresh_rail()
        if not silent and not live:
            hidden_text = (f" · {hidden} "
                           f"{'oculto' if hidden == 1 else 'ocultos'} sin permisos"
                           if hidden else "")
            self.toasts.show(f"Lista actualizada: {len(visible)} servidores{hidden_text}.",
                             "info")

    # ------------------------------------------------------------------ #
    def logout(self) -> None:
        dialog = ConfirmDialog(
            self, "Cerrar sesión",
            "Se cerrará la sesión de Discord y se borrará el token OAuth guardado. El token "
            "fijo del bot se conserva para la próxima vez.",
            confirm_text="Cerrar sesión", danger=True, theme=self.theme)
        if not dialog.show():
            return
        self.tokens.clear()
        self.settings.set("remember_token", False)
        self.settings.save()
        self.pending_bot_token = self._load_fixed_bot_token()
        self.show_login(note="Sesión cerrada. Vuelve a entrar con Discord.")

    # ------------------------------------------------------------------ #
    def set_busy(self, busy: bool, text: str = "") -> None:
        if self._busy_frame is not None:
            try:
                self._busy_frame.destroy()
            except tk.TclError:
                pass
            self._busy_frame = None
        if not busy:
            return
        frame = tk.Frame(self, bg=C.CONTENT)
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        card = tk.Frame(frame, bg=C.CARD, highlightbackground=C.BORDER,
                        highlightthickness=1)
        card.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(card, text=text or "Cargando…", bg=C.CARD, fg=C.TEXT,
                 font=self.theme.font(10, "bold")).pack(padx=48, pady=(22, 10))
        bar = ttk.Progressbar(card, mode="indeterminate", length=260,
                              style="Horizontal.TProgressbar")
        bar.pack(padx=48, pady=(0, 22))
        bar.start(12)
        frame.lift()
        self._busy_frame = frame

    def run_task(self, func: Any, on_done: Any = None, on_error: Any = None,
                 quiet: bool = False) -> None:
        def done(result: Any) -> None:
            if on_done is not None:
                on_done(result)

        def failed(error: BaseException) -> None:
            if on_error is not None:
                on_error(error)
            elif not quiet:
                self.report_error(error)
            else:
                traceback.print_exception(type(error), error, error.__traceback__)

        self.tasks.run(func, done, failed)

    def report_error(self, error: BaseException) -> None:
        if isinstance(error, DiscordError):
            self.toasts.show(str(error), "error", timeout=8000)
        else:
            traceback.print_exception(type(error), error, error.__traceback__)
            self.toasts.show(f"Error inesperado: {type(error).__name__}: {error}",
                             "error", timeout=8000)

    # ------------------------------------------------------------------ #
    def can(self, permission_key: str) -> bool:
        entry = PERMISSION_BY_KEY.get(permission_key)
        if entry is None:
            return True
        return self.permissions == -1 or bool(self.permissions & (1 << entry[1]))

    def can_channel(self, channel: Channel, permission_key: str) -> bool:
        entry = PERMISSION_BY_KEY.get(permission_key)
        if entry is None or self.guild is None:
            return True
        permissions = channel_permissions(self.guild, channel, self.my_member, self.permissions)
        return permissions == -1 or bool(permissions & (1 << entry[1]))

    # ------------------------------------------------------------------ #
    def report_callback_exception(self, exc: type[BaseException], value: BaseException,
                                  tb: Any) -> None:
        """Cualquier error no controlado en un callback se muestra, no se pierde."""
        traceback.print_exception(exc, value, tb)
        try:
            self.report_error(value)
        except Exception:  # noqa: BLE001 - nunca fallar dentro del manejador
            pass

    def on_close(self) -> None:
        if self._oauth_after is not None:
            try:
                self.after_cancel(self._oauth_after)
            except tk.TclError:
                pass
            self._oauth_after = None
        self.cancel_oauth()
        if self._live_after is not None:
            try:
                self.after_cancel(self._live_after)
            except tk.TclError:
                pass
            self._live_after = None
        try:
            self.settings.set("window_geometry", self.geometry())
            self.settings.save()
        except tk.TclError:
            pass
        try:
            self.toasts.shutdown()
        except Exception:  # noqa: BLE001
            pass
        try:
            moderation = getattr(self.shell, "_pages", {}).get("moderation")
            if moderation is not None:
                moderation.voice_process.stop()
                if moderation.gateway is not None:
                    moderation.gateway.stop()
        except Exception:  # noqa: BLE001
            pass
        self.tasks.close()
        self.destroy()


def main() -> None:
    app = App()
    app.mainloop()
