"""Tema visual de la aplicación: paleta, tipografías y estilos ttk.

Estética de escritorio oscura inspirada en Discord, pero con widgets nativos
de Tk (sin navegador, sin dependencias externas).
"""
from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk


class C:
    """Paleta de colores centralizada."""

    RAIL = "#16171a"
    SIDEBAR = "#1e1f22"
    CONTENT = "#2b2d31"
    CARD = "#313338"
    CARD_ALT = "#383a40"
    INPUT = "#1e1f22"
    INPUT_ALT = "#232428"
    BORDER = "#3f4147"
    BORDER_SOFT = "#2f3136"
    TEXT = "#f2f3f5"
    DIM = "#b5bac1"
    MUTED = "#949ba4"
    FAINT = "#6d6f78"
    ACCENT = "#5865f2"
    ACCENT_HOVER = "#4752c4"
    ACCENT_SOFT = "#3c4270"
    GREEN = "#23a55a"
    GREEN_SOFT = "#1f3d2c"
    YELLOW = "#f0b232"
    YELLOW_SOFT = "#3f3117"
    RED = "#da373c"
    RED_HOVER = "#a12828"
    RED_SOFT = "#40252a"
    LINK = "#00a8fc"
    WHITE = "#ffffff"
    BLACK = "#000000"

    # Colores para iconos de servidor (se eligen por hash del nombre).
    GUILD_COLORS = ["#5865f2", "#3ba55d", "#faa61a", "#ed4245", "#eb459e",
                    "#00a8fc", "#9b59b6", "#e67e22", "#1abc9c", "#7289da"]


FONT_CANDIDATES = [
    "Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Helvetica Neue",
    "Inter", "Ubuntu", "Cantarell", "Noto Sans", "DejaVu Sans", "Arial",
]
MONO_CANDIDATES = [
    "Cascadia Mono", "Cascadia Code", "Consolas", "SF Mono", "JetBrains Mono",
    "Ubuntu Mono", "DejaVu Sans Mono", "Courier New",
]


def _pick_family(root: tk.Misc, candidates: list[str], fallback: str) -> str:
    try:
        available = {name.lower(): name for name in tkfont.families(root)}
    except tk.TclError:
        return fallback
    for candidate in candidates:
        if candidate.lower() in available:
            return available[candidate.lower()]
    return fallback


def enable_dark_titlebar(window: tk.Toplevel | tk.Tk) -> None:
    """Título oscuro en Windows 10/11 (silencioso si no está disponible)."""
    if sys.platform != "win32":
        return
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()
        enabled = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(enabled),
                                                   ctypes.sizeof(enabled))
        caption = ctypes.c_int(0x002B2D31)  # COLORREF 0x00BBGGRR
        text = ctypes.c_int(0x00F5F3F2)
        border = ctypes.c_int(0x0047413F)
        for attribute, value in ((35, caption), (36, text), (34, border)):
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute,
                                                           ctypes.byref(value),
                                                           ctypes.sizeof(value))
            except Exception:  # noqa: BLE001 - solo Windows 11
                pass
    except Exception:  # noqa: BLE001 - sin DWM disponible
        return


def enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass


class Theme:
    """Fuentes y estilos ttk de toda la aplicación."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.family = _pick_family(root, FONT_CANDIDATES, "TkDefaultFont")
        self.mono_family = _pick_family(root, MONO_CANDIDATES, "Courier")
        self._fonts: dict[tuple, tuple] = {}

    # -- tipografías -------------------------------------------------------- #
    def font(self, size: int = 10, weight: str = "normal", mono: bool = False,
             slant: str = "roman", underline: bool = False) -> tuple:
        key = (size, weight, mono, slant, underline)
        cached = self._fonts.get(key)
        if cached is None:
            cached = (self.mono_family if mono else self.family, size, weight, slant,
                      "underline" if underline else "normal")
            self._fonts[key] = cached
        return cached

    # -- estilos ------------------------------------------------------------ #
    def apply(self) -> None:
        root = self.root
        root.configure(bg=C.CONTENT)
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        base = self.font(10)
        bold = self.font(10, "bold")
        small = self.font(9)
        small_bold = self.font(9, "bold")
        heading = self.font(20, "bold")
        h2 = self.font(13, "bold")
        h3 = self.font(11, "bold")
        mono = self.font(9, mono=True)

        root.option_add("*tearOff", False)
        root.option_add("*Font", base)
        root.option_add("*TCombobox*Listbox.background", C.INPUT)
        root.option_add("*TCombobox*Listbox.foreground", C.TEXT)
        root.option_add("*TCombobox*Listbox.selectBackground", C.ACCENT)
        root.option_add("*TCombobox*Listbox.selectForeground", C.WHITE)
        root.option_add("*TCombobox*Listbox.font", base)
        root.option_add("*Menu.background", C.SIDEBAR)
        root.option_add("*Menu.foreground", C.TEXT)
        root.option_add("*Menu.activeBackground", C.ACCENT)
        root.option_add("*Menu.activeForeground", C.WHITE)

        # Contenedores
        style.configure("TFrame", background=C.CONTENT)
        style.configure("Card.TFrame", background=C.CARD)
        style.configure("Sidebar.TFrame", background=C.SIDEBAR)
        style.configure("Rail.TFrame", background=C.RAIL)
        style.configure("Input.TFrame", background=C.CARD)

        # Texto
        style.configure("TLabel", background=C.CONTENT, foreground=C.TEXT, font=base)
        style.configure("Title.TLabel", background=C.CONTENT, foreground=C.TEXT, font=heading)
        style.configure("H2.TLabel", background=C.CONTENT, foreground=C.TEXT, font=h2)
        style.configure("H3.TLabel", background=C.CONTENT, foreground=C.TEXT, font=h3)
        style.configure("Body.TLabel", background=C.CONTENT, foreground=C.TEXT, font=base)
        style.configure("Dim.TLabel", background=C.CONTENT, foreground=C.DIM, font=base)
        style.configure("Muted.TLabel", background=C.CONTENT, foreground=C.MUTED, font=small)
        style.configure("Field.TLabel", background=C.CONTENT, foreground=C.DIM, font=small_bold)
        style.configure("Mono.TLabel", background=C.CONTENT, foreground=C.MUTED, font=mono)
        style.configure("Error.TLabel", background=C.CONTENT, foreground=C.RED, font=small)
        style.configure("Success.TLabel", background=C.CONTENT, foreground=C.GREEN, font=small)
        style.configure("Link.TLabel", background=C.CONTENT, foreground=C.LINK, font=base)

        # Botones
        style.configure("TButton", background=C.CARD_ALT, foreground=C.TEXT, font=bold,
                        borderwidth=1, bordercolor=C.BORDER, relief="flat",
                        padding=(12, 6), focuscolor=C.CARD_ALT)
        style.map("TButton",
                  background=[("disabled", C.CARD), ("pressed", C.BORDER), ("active", "#4e5058")],
                  foreground=[("disabled", C.FAINT)],
                  bordercolor=[("disabled", C.BORDER_SOFT)])

        style.configure("Accent.TButton", background=C.ACCENT, foreground=C.WHITE,
                        bordercolor=C.ACCENT, font=bold, padding=(14, 7))
        style.map("Accent.TButton",
                  background=[("disabled", C.ACCENT_SOFT), ("pressed", C.ACCENT_HOVER),
                              ("active", C.ACCENT_HOVER)],
                  foreground=[("disabled", C.MUTED)],
                  bordercolor=[("disabled", C.ACCENT_SOFT)])

        style.configure("Danger.TButton", background=C.RED, foreground=C.WHITE,
                        bordercolor=C.RED, font=bold, padding=(12, 6))
        style.map("Danger.TButton",
                  background=[("disabled", C.RED_SOFT), ("pressed", C.RED_HOVER),
                              ("active", C.RED_HOVER)],
                  foreground=[("disabled", C.MUTED)])

        style.configure("Ghost.TButton", background=C.CONTENT, foreground=C.DIM,
                        bordercolor=C.BORDER, font=base, padding=(10, 5))
        style.map("Ghost.TButton",
                  background=[("active", C.CARD_ALT)], foreground=[("active", C.TEXT)],
                  bordercolor=[("active", C.BORDER)])

        style.configure("Small.TButton", background=C.CARD_ALT, foreground=C.TEXT,
                        font=small_bold, borderwidth=1, bordercolor=C.BORDER,
                        padding=(8, 3))
        style.map("Small.TButton",
                  background=[("disabled", C.CARD), ("active", "#4e5058")],
                  foreground=[("disabled", C.FAINT)])

        style.configure("SmallAccent.TButton", background=C.ACCENT, foreground=C.WHITE,
                        font=small_bold, borderwidth=0, padding=(9, 4))
        style.map("SmallAccent.TButton",
                  background=[("disabled", C.ACCENT_SOFT), ("active", C.ACCENT_HOVER)],
                  foreground=[("disabled", C.MUTED)])

        style.configure("SmallDanger.TButton", background=C.RED_SOFT, foreground="#ff8f92",
                        font=small_bold, borderwidth=0, padding=(9, 4))
        style.map("SmallDanger.TButton",
                  background=[("active", C.RED)], foreground=[("active", C.WHITE)])

        # Entradas
        for style_name in ("TEntry", "TSpinbox"):
            style.configure(style_name, fieldbackground=C.INPUT, background=C.INPUT,
                            foreground=C.TEXT, insertcolor=C.TEXT, bordercolor=C.BORDER,
                            lightcolor=C.BORDER, darkcolor=C.BORDER, borderwidth=1,
                            relief="flat", padding=(8, 6), arrowcolor=C.DIM)
            style.map(style_name,
                      bordercolor=[("focus", C.ACCENT)],
                      lightcolor=[("focus", C.ACCENT)],
                      darkcolor=[("focus", C.ACCENT)],
                      fieldbackground=[("disabled", C.CARD), ("readonly", C.INPUT_ALT)],
                      foreground=[("disabled", C.FAINT)],
                      selectbackground=[("!disabled", C.ACCENT)],
                      selectforeground=[("!disabled", C.WHITE)])

        style.configure("TCombobox", fieldbackground=C.INPUT, background=C.CARD_ALT,
                        foreground=C.TEXT, arrowcolor=C.DIM, bordercolor=C.BORDER,
                        lightcolor=C.BORDER, darkcolor=C.BORDER, borderwidth=1,
                        relief="flat", padding=(8, 5))
        style.map("TCombobox",
                  fieldbackground=[("readonly", C.INPUT), ("disabled", C.CARD)],
                  foreground=[("readonly", C.TEXT), ("disabled", C.FAINT)],
                  selectbackground=[("readonly", C.INPUT)],
                  selectforeground=[("readonly", C.TEXT)],
                  arrowcolor=[("active", C.TEXT)],
                  bordercolor=[("focus", C.ACCENT)])
        root.option_add("*TCombobox*Listbox.borderWidth", 0)

        # Tablas
        style.configure("Treeview", background=C.CARD, fieldbackground=C.CARD,
                        foreground=C.TEXT, font=base, rowheight=30, borderwidth=0,
                        relief="flat", lightcolor=C.CARD, darkcolor=C.CARD)
        style.map("Treeview",
                  background=[("selected", C.ACCENT)],
                  foreground=[("selected", C.WHITE)])
        style.configure("Treeview.Heading", background=C.SIDEBAR, foreground=C.DIM,
                        font=small_bold, relief="flat", borderwidth=0,
                        padding=(8, 7), lightcolor=C.SIDEBAR, darkcolor=C.SIDEBAR)
        style.map("Treeview.Heading",
                  background=[("active", C.CARD_ALT), ("pressed", C.CARD_ALT)],
                  foreground=[("active", C.TEXT)])
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

        # Barras de desplazamiento
        for orientation in ("Vertical", "Horizontal"):
            style.configure(f"{orientation}.TScrollbar", background="#4e5058",
                            troughcolor=C.CONTENT, bordercolor=C.CONTENT,
                            arrowcolor=C.MUTED, width=11, arrowsize=11,
                            relief="flat", borderwidth=0)
            style.map(f"{orientation}.TScrollbar",
                      background=[("active", "#6d6f78"), ("pressed", C.MUTED)])

        style.configure("Horizontal.TProgressbar", troughcolor=C.INPUT,
                        background=C.ACCENT, borderwidth=0, thickness=4,
                        bordercolor=C.INPUT, lightcolor=C.ACCENT, darkcolor=C.ACCENT)

        # Notebook (por si se usa en algún sitio)
        style.configure("TNotebook", background=C.CONTENT, borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure("TNotebook.Tab", background=C.SIDEBAR, foreground=C.DIM,
                        font=bold, padding=(16, 8), borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", C.CARD), ("active", C.CARD_ALT)],
                  foreground=[("selected", C.TEXT)])

        style.configure("TCheckbutton", background=C.CONTENT, foreground=C.TEXT,
                        font=base, focuscolor=C.CONTENT)
        style.map("TCheckbutton", background=[("active", C.CONTENT)],
                  indicatorcolor=[("selected", C.ACCENT), ("!selected", C.INPUT)])

        style.configure("TPanedwindow", background=C.CONTENT)
        style.configure("TSeparator", background=C.BORDER_SOFT)

    # -- menús -------------------------------------------------------------- #
    def style_menu(self, menu: tk.Menu) -> None:
        menu.configure(bg=C.SIDEBAR, fg=C.TEXT, activebackground=C.ACCENT,
                       activeforeground=C.WHITE, bd=0, relief="flat",
                       font=self.font(10))
