"""Genera capturas de la aplicación en modo demostración (herramienta de desarrollo).

Usa PrintWindow para capturar la ventana aunque esté tapada por otras.
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DSS_HOME", str(ROOT / "_testdata"))

from PIL import Image, ImageGrab  # noqa: E402

from dss.store import TokenStore  # noqa: E402
from dss.ui.app import App  # noqa: E402

OUT = ROOT / "capturas"
OUT.mkdir(exist_ok=True)

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def pump(app: tk.Misc, seconds: float = 0.6) -> None:
    end = time.time() + seconds
    while time.time() < end:
        try:
            app.update()
        except tk.TclError:
            return
        time.sleep(0.02)


def hwnd_of(widget: tk.Misc) -> int:
    return user32.GetParent(widget.winfo_id()) or widget.winfo_id()


def capture_window(hwnd: int) -> Image.Image:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    window_dc = user32.GetWindowDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    gdi32.SelectObject(memory_dc, bitmap)
    user32.PrintWindow(hwnd, memory_dc, 2)
    header = BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    header.biWidth = width
    header.biHeight = -height
    header.biPlanes = 1
    header.biBitCount = 32
    header.biCompression = 0
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(memory_dc, bitmap, 0, height, buffer, ctypes.byref(header), 0)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory_dc)
    user32.ReleaseDC(hwnd, window_dc)
    return Image.frombuffer("RGBA", (width, height), buffer, "raw", "BGRA", 0, 1)


def capture(app: tk.Misc, name: str, window: tk.Misc | None = None) -> None:
    target = window or app.winfo_toplevel()
    root = app.winfo_toplevel()
    root.attributes("-topmost", True)
    if window is not None:
        target.attributes("-topmost", True)
    hwnd = hwnd_of(target)
    user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0040)
    user32.SetForegroundWindow(hwnd)
    pump(root, 0.25)
    try:
        image = capture_window(hwnd)
        if image.getextrema()[3][1] == 0:
            raise ValueError("captura vacía")
    except Exception:
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        image = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))
    image.convert("RGB").save(OUT / f"{name}.png")
    print(f"captura {name} -> {image.size}")


def capture_modal(app: tk.Misc, modal: tk.Toplevel, name: str) -> None:
    def snap() -> None:
        try:
            capture(app, name, window=modal)
        finally:
            modal.close()

    modal.after(700, snap)
    modal.show()


def main() -> None:
    # La captura muestra el estado real: token del bot fijo cargado (valor de ejemplo).
    TokenStore.for_bot().save("token-fijo-de-demostracion", "bot")
    app = App()
    app.geometry("1400x900+60+60")
    pump(app, 0.9)
    capture(app, "01-inicio-sesion")

    view = app._view
    if hasattr(view, "_toggle_bot_help"):
        view._toggle_bot_help()
        pump(app, 0.6)
        capture(app, "21-ayuda-bot")
        view._toggle_bot_help()
        pump(app, 0.3)

    app.start_demo()
    pump(app, 0.7)
    capture(app, "02-selector-servidor")

    summary = next(g for g in app.guilds if g.name == "Estudio Lunar")
    app.open_guild(summary)
    pump(app, 1.2)
    capture(app, "03-resumen")

    for key, name in (
        ("channels", "04-canales"),
        ("roles", "05-roles"),
        ("members", "06-miembros"),
        ("moderation", "07-moderacion-sanciones"),
        ("automod", "10-automod"),
        ("invites", "11-invitaciones"),
        ("emojis", "12-emojis"),
        ("webhooks", "13-webhooks"),
        ("settings", "14-ajustes"),
    ):
        app.shell.switch_page(key)
        pump(app, 0.9)
        capture(app, name)
        if key == "roles":
            page = app.shell._pages["roles"]
            page.tabs.select("bulk")
            sample = {
                "guild_id": app.guild.id,
                "roles": {
                    "create": [{
                        "name": "VIP", "position": 10, "color": "#F1C40F",
                        "hoist": True, "mentionable": True,
                        "permissions": ["SendMessages", "AttachFiles", "UseExternalEmojis"],
                    }],
                    "modify": [{"target_name": "Miembro", "name": "Miembro Verificado",
                                "position": 8, "color": "#2ECC71"}],
                    "delete": [{"target_name": "Silenciado", "reason": "Limpieza de roles"}],
                },
                "role_members": [{
                    "target_name": "Administrador",
                    "add_users": [app.user.id],
                    "remove_users": [],
                }],
            }
            page.bulk.load_text(json.dumps(sample), format_json=True)
            pump(app, 0.8)
            capture(app, "27-roles-masivos")
            page.bulk.clear()
            page.tabs.select("roles")
        if key == "moderation":
            page = app.shell._pages["moderation"]
            page.tabbar.select("audit")
            pump(app, 0.9)
            capture(app, "08-moderacion-registro")
            page.tabbar.select("messages")
            pump(app, 0.9)
            capture(app, "09-moderacion-mensajes")

    from dss.ui.pages.automod import AutomodRuleModal
    from dss.ui.pages.channels import OverwritesModal
    from dss.ui.pages.members import MemberModal
    from dss.ui.pages.modals import BanModal

    # Beneficios por comunidad y mejoras
    app.shell.switch_page("dashboard")
    pump(app, 0.7)
    dashboard = app.shell._pages["dashboard"]
    dashboard.scroll._canvas.yview_moveto(1.0)
    pump(app, 0.6)
    capture(app, "24-beneficios-servidor")

    app.shell.switch_page("settings")
    pump(app, 0.7)
    settings_page = app.shell._pages["settings"]
    settings_page.scroll._canvas.yview_moveto(0.40)
    pump(app, 0.6)
    capture(app, "25-ajustes-comunidad")

    # Selector de emojis (estándar y del servidor)
    moderation_page = app.shell._pages["moderation"]
    app.shell.switch_page("moderation")
    pump(app, 0.4)
    moderation_page.tabbar.select("messages")
    pump(app, 0.9)
    messages_tab = moderation_page._frames["messages"]
    messages_tab.channel_var.set("#general")
    messages_tab.load()
    pump(app, 0.8)
    messages_tab._open_emoji_picker()
    pump(app, 0.6)
    picker = getattr(app, "_emoji_picker", None)
    if picker is not None:
        picker._can_close = False
        capture(app, "22-selector-emojis", window=picker)
        picker._on_tab("guild")
        pump(app, 0.7)
        capture(app, "23-selector-emojis-servidor", window=picker)
        picker.close()
        pump(app, 0.2)

    channels_page = app.shell._pages["channels"]
    channel = next(c for c in app.channels if c.is_text and c.name == "general")
    app.shell.switch_page("channels")
    pump(app, 0.5)
    capture_modal(app, OverwritesModal(channels_page, app, channel), "15-permisos-canal")

    automod_page = app.shell._pages["automod"]
    app.shell.switch_page("automod")
    pump(app, 0.5)
    capture_modal(app, AutomodRuleModal(automod_page, app, automod_page._rules[0],
                                       lambda: None), "16-editor-automod")

    members_page = app.shell._pages["members"]
    app.shell.switch_page("members")
    pump(app, 0.8)
    capture_modal(app, MemberModal(members_page, app, members_page, members_page._members[3]),
                  "17-ficha-miembro")
    capture_modal(app, BanModal(members_page, app), "18-banear")

    # Servidor sin comunidad ni mejoras
    pruebas = next(g for g in app.guilds if g.name == "Servidor de Pruebas")
    app.open_guild(pruebas)
    pump(app, 1.2)
    app.shell.switch_page("settings")
    pump(app, 0.8)
    plain_settings = app.shell._pages["settings"]
    plain_settings.scroll._canvas.yview_moveto(0.40)
    pump(app, 0.6)
    capture(app, "26-ajustes-sin-comunidad")

    app.open_guild(summary)
    pump(app, 1.2)
    app.geometry("1120x700+80+80")
    app.shell.switch_page("roles")
    pump(app, 0.9)
    capture(app, "28-roles-ventana-pequena")
    app.shell.switch_page("dashboard")
    pump(app, 0.9)
    capture(app, "20-ventana-pequena")

    app.on_close()


if __name__ == "__main__":
    main()
