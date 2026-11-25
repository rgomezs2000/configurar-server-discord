"""Marco principal: barra de servidores, navegación lateral y cambio de páginas."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from ..constants import APP_NAME
from ..models import GuildSummary
from .pages import NAV_GROUPS, PAGE_BY_KEY
from .theme import C
from .widgets import Avatar, FlatButton, GuildTile, Modal, NavButton, Tooltip, copy_to_clipboard


class ShellView(tk.Frame):
    def __init__(self, master: tk.Misc, app: Any):
        super().__init__(master, bg=C.CONTENT)
        self.app = app
        self._pages: dict[str, Any] = {}
        self._nav: dict[str, NavButton] = {}
        self._active = ""
        self._rail_tiles: dict[str, GuildTile] = {}
        self._build()
        last = str(app.settings.get("last_page") or "dashboard")
        if last not in PAGE_BY_KEY:
            last = "dashboard"
        self.switch_page(last)

    # ------------------------------------------------------------------ #
    # Construcción
    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        self._build_rail()
        self._build_sidebar()
        self.host = tk.Frame(self, bg=C.CONTENT)
        self.host.pack(side="left", fill="both", expand=True)

    def _build_rail(self) -> None:
        app = self.app
        rail = tk.Frame(self, bg=C.RAIL, width=74)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)

        home = self._glyph_tile(rail, "⊞", "Todos los servidores", app.show_picker)
        home.pack(pady=(12, 6))
        tk.Frame(rail, bg=C.BORDER_SOFT, height=1, width=36).pack(pady=(0, 6))

        holder = tk.Frame(rail, bg=C.RAIL)
        holder.pack(fill="both", expand=True)
        self._rail_canvas = tk.Canvas(holder, bg=C.RAIL, highlightthickness=0, bd=0,
                                      width=74)
        self._rail_canvas.pack(fill="both", expand=True)
        self._rail_inner = tk.Frame(self._rail_canvas, bg=C.RAIL)
        self._rail_window = self._rail_canvas.create_window((0, 0), window=self._rail_inner,
                                                            anchor="nw", width=74)
        self._rail_inner.bind("<Configure>", self._rail_configure)
        self._rail_canvas.bind("<Enter>", self._rail_wheel_on)
        self._rail_canvas.bind("<Leave>", self._rail_wheel_off)
        self._populate_rail()

        tk.Frame(rail, bg=C.BORDER_SOFT, height=1, width=36).pack(pady=6)
        add = self._glyph_tile(rail, "＋", "Invitar la aplicación a otro servidor",
                               self._show_invite_info)
        add.pack(pady=(0, 8))
        avatar = Avatar(rail, app.user.display_name if app.user else "?", 34, bg=C.RAIL,
                        theme=app.theme)
        avatar.pack(pady=(0, 12))
        avatar.configure(cursor="hand2")
        avatar.bind("<Button-1>", lambda _e: app.logout())
        Tooltip(avatar, "Cerrar sesión")
        self.rail_avatar = avatar
        if app.user is not None:
            app.images.apply(avatar, app.user.avatar_url, 34)

    def _rail_configure(self, _event: Any = None) -> None:
        self._rail_canvas.configure(scrollregion=self._rail_canvas.bbox("all"))

    def _rail_wheel_on(self, _event: Any = None) -> None:
        self._rail_canvas.bind_all("<MouseWheel>", self._rail_wheel, add="+")

    def _rail_wheel_off(self, _event: Any = None) -> None:
        self._rail_canvas.unbind_all("<MouseWheel>")

    def _rail_wheel(self, event: Any) -> None:
        self._rail_canvas.yview_scroll(int(-event.delta / 120) * 2, "units")

    def _glyph_tile(self, parent: tk.Misc, glyph: str, tooltip: str, command: Any) -> tk.Canvas:
        canvas = tk.Canvas(parent, width=48, height=48, bg=C.RAIL, highlightthickness=0,
                           bd=0, cursor="hand2")
        canvas.create_oval(4, 4, 44, 44, fill=C.CARD_ALT, outline="")
        canvas.create_text(24, 24, text=glyph, fill=C.GREEN, font=(self.app.theme.family, 16, "bold"))
        canvas.bind("<Button-1>", lambda _e: command())
        canvas.bind("<Enter>", lambda _e: canvas.configure(bg=C.RAIL) or canvas.itemconfigure(
            1, fill=C.ACCENT))
        canvas.bind("<Leave>", lambda _e: canvas.itemconfigure(1, fill=C.CARD_ALT))
        Tooltip(canvas, tooltip)
        return canvas

    def _populate_rail(self) -> None:
        for child in self._rail_inner.winfo_children():
            child.destroy()
        self._rail_tiles.clear()
        for summary in self.app.guilds or []:
            tile = GuildTile(self._rail_inner, summary.name, 48, bg=C.RAIL,
                             command=lambda s=summary: self.app.open_guild(s))
            tile.pack(pady=4)
            tile.set_selected(bool(self.app.guild and summary.id == self.app.guild.id))
            self.app.images.apply(tile, summary.icon_url, 54)
            Tooltip(tile, f"{summary.name}\nAbrir servidor")
            self._rail_tiles[summary.id] = tile

    def _build_sidebar(self) -> None:
        app = self.app
        sidebar = tk.Frame(self, bg=C.SIDEBAR, width=256)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        header = tk.Frame(sidebar, bg=C.SIDEBAR, height=108)
        header.pack(fill="x")
        header.pack_propagate(False)
        self.guild_tile = GuildTile(header, app.guild.name, 42, bg=C.SIDEBAR,
                                    command=app.show_picker)
        self.guild_tile.pack(side="left", padx=(16, 10), pady=16)
        self._load_guild_icon()
        info = tk.Frame(header, bg=C.SIDEBAR)
        info.pack(side="left", fill="x", expand=True, pady=(16, 0))
        self.guild_name = tk.Label(info, text=app.guild.name, bg=C.SIDEBAR, fg=C.TEXT,
                                   font=app.theme.font(11, "bold"), anchor="w",
                                   justify="left", wraplength=150)
        self.guild_name.pack(fill="x")
        self.switch_link = tk.Label(info, text="Cambiar de servidor", bg=C.SIDEBAR,
                                    fg=C.LINK, font=app.theme.font(8), anchor="w",
                                    cursor="hand2")
        self.switch_link.pack(fill="x", pady=(2, 0))
        self.switch_link.bind("<Button-1>", lambda _e: app.show_picker())
        actions = tk.Frame(info, bg=C.SIDEBAR)
        actions.pack(fill="x", pady=(4, 0))
        FlatButton(actions, "Actualizar", self.manual_refresh, bg=C.SIDEBAR,
                   fg=C.LINK, hover_bg=C.CARD_ALT, hover_fg=C.TEXT,
                   font=app.theme.font(8), pady=2).pack(side="left")
        FlatButton(actions, "Ver registro", self.open_audit, bg=C.SIDEBAR,
                   fg=C.LINK, hover_bg=C.CARD_ALT, hover_fg=C.TEXT,
                   font=app.theme.font(8), pady=2).pack(side="left", padx=(6, 0))
        if app.demo:
            tk.Label(info, text="MODO DEMO", bg=C.ACCENT_SOFT, fg="#c7cdff",
                     font=app.theme.font(7, "bold"), padx=5, pady=1).pack(
                anchor="w", pady=(4, 0))

        tk.Frame(sidebar, bg=C.BORDER_SOFT, height=1).pack(fill="x", padx=12)

        nav = tk.Frame(sidebar, bg=C.SIDEBAR)
        nav.pack(fill="both", expand=True, pady=(8, 0))
        for group, keys in NAV_GROUPS:
            available = [key for key in keys if key in PAGE_BY_KEY]
            if not available:
                continue
            tk.Label(nav, text=group.upper(), bg=C.SIDEBAR, fg=C.FAINT,
                     font=app.theme.font(7, "bold"), anchor="w").pack(
                fill="x", padx=18, pady=(10, 2))
            for key in available:
                page_class = PAGE_BY_KEY[key]
                button = NavButton(nav, page_class.label, lambda k=key: self.switch_page(k),
                                   glyph=page_class.glyph, bg=C.SIDEBAR, theme=app.theme)
                button.pack(fill="x", padx=8)
                self._nav[key] = button

        footer = tk.Frame(sidebar, bg=C.SIDEBAR)
        footer.pack(fill="x", side="bottom", pady=(6, 16))
        tk.Frame(footer, bg=C.BORDER_SOFT, height=1).pack(fill="x", padx=12, pady=(0, 10))
        user_row = tk.Frame(footer, bg=C.SIDEBAR)
        user_row.pack(fill="x", padx=14)
        user_avatar = Avatar(user_row, app.user.display_name if app.user else "?", 30,
                             bg=C.SIDEBAR, theme=app.theme)
        user_avatar.pack(side="left")
        self.user_avatar = user_avatar
        text = tk.Frame(user_row, bg=C.SIDEBAR)
        text.pack(side="left", fill="x", expand=True, padx=(8, 0))
        tk.Label(text, text=app.user.display_name if app.user else "—", bg=C.SIDEBAR,
                 fg=C.TEXT, font=app.theme.font(9, "bold"), anchor="w").pack(fill="x")
        kind_label = {"bot": "Aplicación (bot)", "user": "Cuenta de usuario",
                      "oauth": "Cuenta (OAuth)", "demo": "Demostración"}.get(
            app.session_kind, "")
        tk.Label(text, text=kind_label, bg=C.SIDEBAR, fg=C.MUTED,
                 font=app.theme.font(8), anchor="w").pack(fill="x")
        if getattr(app.user, "has_nitro", False):
            tk.Label(text, text="NITRO", bg=C.ACCENT, fg=C.WHITE,
                     font=app.theme.font(6, "bold"), padx=5, pady=1).pack(
                anchor="w", pady=(2, 0))
        FlatButton(footer, "Cerrar sesión", app.logout, bg=C.SIDEBAR, fg=C.MUTED,
                   hover_bg=C.CARD_ALT, hover_fg=C.TEXT, font=app.theme.font(8),
                   pady=5).pack(fill="x", padx=10, pady=(8, 2))
        self.live_pill = tk.Label(footer, text="○ Manual · F5", bg=C.SIDEBAR, fg=C.FAINT,
                                  font=app.theme.font(8, "bold"), anchor="w")
        self.live_pill.pack(fill="x", padx=14, pady=(4, 0))
        Tooltip(self.live_pill,
                "Actualización manual: usa «Actualizar» o F5. El sondeo automático está "
                "desactivado.")
        self.set_live_status(getattr(app, "live_status", "off"))
        self._load_user_avatars()

    def _load_user_avatars(self) -> None:
        if self.app.user is None:
            return
        url = self.app.user.avatar_url
        self.app.images.apply(self.rail_avatar, url, 34)
        self.app.images.apply(self.user_avatar, url, 30)

    def _load_guild_icon(self) -> None:
        guild = self.app.guild
        if guild is None:
            return
        if guild.icon_url:
            self.app.images.apply(self.guild_tile, guild.icon_url, 54)
        else:
            self.guild_tile.set_photo(None)

    # ------------------------------------------------------------------ #
    # Acciones globales
    # ------------------------------------------------------------------ #
    def manual_refresh(self) -> None:
        self.app.refresh_guilds(silent=True)
        self.app.refresh_guild(silent=False)

    def open_audit(self) -> None:
        self.switch_page("moderation")
        page = self._pages.get("moderation")
        if page is not None:
            page.tabbar.select("audit")

    # ------------------------------------------------------------------ #
    # Navegación
    # ------------------------------------------------------------------ #
    def switch_page(self, key: str, **kwargs: Any) -> None:
        page_class = PAGE_BY_KEY.get(key)
        if page_class is None:
            return
        page = self._pages.get(key)
        if page is None:
            page = page_class(self.host, self.app)
            self._pages[key] = page
        for other in self._pages.values():
            other.pack_forget()
        page.pack(fill="both", expand=True)
        self._active = key
        for nav_key, button in self._nav.items():
            button.set_active(nav_key == key)
        self.app.settings.set("last_page", key)
        try:
            page.on_show(**kwargs)
        except TypeError:
            page.on_show()

    def refresh_current(self) -> None:
        page = self._pages.get(self._active)
        if page is not None and not page.is_dirty():
            page.refresh()

    def live_update(self) -> str:
        """Refresca la página visible; respeta los cambios sin guardar."""
        page = self._pages.get(self._active)
        if page is None:
            return "idle"
        if page.is_dirty():
            return "editing"
        try:
            page.live_refresh()
            return "ok"
        except Exception as error:  # noqa: BLE001
            print(f"[dss] error en actualización en vivo: {error}")
            return "error"

    def set_live_status(self, state: str) -> None:
        palette = {
            "live": ("● Automático", C.GREEN),
            "syncing": ("● Sincronizando…", C.YELLOW),
            "editing": ("● En pausa · editando", C.YELLOW),
            "paused": ("● En pausa", C.MUTED),
            "off": ("○ Manual · F5", C.FAINT),
            "error": ("● Sin conexión", C.RED),
        }
        text, color = palette.get(state, palette["live"])
        try:
            self.live_pill.configure(text=text, fg=color)
        except tk.TclError:
            pass

    def silent_refresh(self) -> None:
        """Actualiza cabecera, contadores e iconos sin recargar la página visible."""
        guild = self.app.guild
        if guild is None:
            return
        self.guild_name.configure(text=guild.name)
        self.guild_tile.set_name(guild.name)
        self._load_guild_icon()
        for summary in self.app.guilds:
            tile = self._rail_tiles.get(summary.id)
            if tile is not None:
                tile.set_name(summary.name)
                self.app.images.apply(tile, summary.icon_url, 54)
        self.update_badges()
        for key, page in self._pages.items():
            if key != self._active:
                page.invalidate()

    def on_guild_refreshed(self) -> None:
        guild = self.app.guild
        self.guild_name.configure(text=guild.name)
        self.guild_tile.set_name(guild.name)
        self._load_guild_icon()
        self._load_user_avatars()
        for summary in self.app.guilds:
            tile = self._rail_tiles.get(summary.id)
            if tile is not None:
                tile.set_name(summary.name)
                self.app.images.apply(tile, summary.icon_url, 54)
        for guild_id, tile in self._rail_tiles.items():
            tile.set_selected(guild_id == guild.id)
        self.update_badges()
        for key, page in self._pages.items():
            try:
                page.on_guild_refreshed()
            except Exception as error:  # noqa: BLE001 - una página rota no debe tumbar el panel
                print(f"[dss] error refrescando {page.__class__.__name__}: {error}")
            if key != self._active:
                page.invalidate()

    def update_badges(self) -> None:
        channels = [c for c in (self.app.channels or []) if not c.is_category]
        if "channels" in self._nav:
            self._nav["channels"].set_badge(str(len(channels)) if channels else "")
        if "roles" in self._nav and self.app.guild:
            self._nav["roles"].set_badge(str(len(self.app.guild.roles)))
        if "members" in self._nav and self.app.guild and self.app.guild.member_count:
            self._nav["members"].set_badge(
                f"{self.app.guild.member_count // 1000}k"
                if self.app.guild.member_count >= 1000
                else str(self.app.guild.member_count))

    # ------------------------------------------------------------------ #
    def refresh_rail(self) -> None:
        self._populate_rail()

    def _show_invite_info(self) -> None:
        app = self.app
        url = getattr(app.client, "bot_invite_url", None)
        modal = Modal(self, "Añadir la aplicación a otro servidor", width=560,
                      theme=app.theme,
                      subtitle="La app solo puede administrar servidores donde esté presente.")
        text = (
            "Abre el portal de desarrolladores, entra en tu aplicación y usa "
            "«OAuth2 → URL Generator» con el alcance bot y los permisos que necesites."
            if url else
            "Con un token de cuenta no hace falta invitar nada: aparecerán todos los "
            "servidores de tu cuenta. Con un token de bot, invita la aplicación a cada "
            "servidor que quieras administrar."
        )
        tk.Label(modal.body, text=text, bg=C.CARD, fg=C.DIM, font=app.theme.font(9),
                 wraplength=500, justify="left", anchor="w").pack(fill="x")
        if url:
            tk.Label(modal.body, text=url, bg=C.INPUT, fg=C.MUTED,
                     font=(app.theme.mono_family, 8), wraplength=500, justify="left",
                     anchor="w", padx=8, pady=8).pack(fill="x", pady=(10, 0))
            modal.add_button("Copiar URL", lambda: self._copy_invite(modal, url),
                             style="Accent.TButton")
        modal.add_button("Cerrar", modal.close)
        modal.show()

    def _copy_invite(self, modal: Modal, url: str) -> None:
        copy_to_clipboard(modal, url)
        self.app.toasts.show("URL copiada al portapapeles.", "success")
