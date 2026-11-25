"""Emojis del servidor: subir, previsualizar, editar y eliminar."""
from __future__ import annotations

import base64
import io
import tkinter as tk
import urllib.request
from tkinter import filedialog, ttk
from typing import Any

from ...models import Emoji
from ...util import MAX_EMOJI_BYTES, image_to_data_uri
from ..theme import C
from ..widgets import (Card, ConfirmDialog, Field, Modal, PageHeader, ScrollFrame,
                       TabBar, Tooltip)
from .base import Page
from .bulk_emojis import BulkEmojisTab

NAME_ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


class EmojisPage(Page):
    key = "emojis"
    label = "Emojis"
    glyph = "◕"

    def build(self) -> None:
        app = self.app
        self.header = PageHeader(self, app, "Emojis",
                                 "Sube y administra emojis personalizados del servidor.")
        self.header.pack(fill="x", padx=28, pady=(22, 0))
        self._manage = app.can("MANAGE_GUILD_EXPRESSIONS")
        self.header.button("Actualizar", self.refresh)

        self.count_label = tk.Label(self, text="", bg=C.CONTENT, fg=C.MUTED,
                                    font=app.theme.font(9), anchor="w")
        self.count_label.pack(fill="x", padx=28, pady=(10, 2))
        self.limit_hint = tk.Label(self, text="", bg=C.CONTENT, fg=C.FAINT,
                                   font=app.theme.font(8), anchor="w")
        self.limit_hint.pack(fill="x", padx=28, pady=(0, 4))

        self.tabs = TabBar(self, [("emojis", "Emojis"),
                                  ("bulk", "Gestionar emojis masivo")],
                           on_change=self._switch, theme=app.theme)
        self.tabs.pack(fill="x", padx=28, pady=(4, 0))
        self.container = tk.Frame(self, bg=C.CONTENT)
        self.container.pack(fill="both", expand=True)
        self.emojis_tab = tk.Frame(self.container, bg=C.CONTENT)
        self.bulk = BulkEmojisTab(self.container, app, self)
        self._active_tab = ""
        self._build_emojis_tab()
        self.tabs.select("emojis")

    def _build_emojis_tab(self) -> None:
        app = self.app
        toolbar = tk.Frame(self.emojis_tab, bg=C.CONTENT)
        toolbar.pack(fill="x", padx=28, pady=(10, 0))
        self.upload_button = ttk.Button(toolbar, text="Subir emoji",
                                        style="Accent.TButton", command=self._upload)
        self.upload_button.pack(side="left")
        if not self._manage:
            self.upload_button.configure(state="disabled")
            tk.Label(toolbar,
                     text="Solo lectura: falta «Gestionar emojis y stickers».",
                     bg=C.YELLOW_SOFT, fg="#ffd98a", font=app.theme.font(8),
                     anchor="w", padx=10, pady=5).pack(side="left", padx=(10, 0))
        self.scroll = ScrollFrame(self.emojis_tab, bg=C.CONTENT)
        self.scroll.pack(fill="both", expand=True, padx=22, pady=(10, 12))
        self._emojis: list[Emoji] = []
        self._photos: dict[str, tk.PhotoImage] = {}
        self._card_animations: list[tuple[tk.Label, str]] = []
        self._preview_after: str | None = None
        self._at_limit = False

    def _switch(self, key: str) -> None:
        if not hasattr(self, "emojis_tab"):
            return
        self._active_tab = key
        for frame in (self.emojis_tab, self.bulk):
            frame.pack_forget()
        if key == "emojis":
            self.emojis_tab.pack(fill="both", expand=True)
        else:
            self.bulk.pack(fill="both", expand=True)
            self.bulk.on_show()

    def refresh(self) -> None:
        client = self.app.client
        guild_id = self.app.guild.id
        self.run(lambda: client.list_emojis(guild_id), self._done)

    def _done(self, emojis: list[Emoji]) -> None:
        self._emojis = emojis
        self.bulk.set_emojis(emojis)
        guild = self.app.guild
        limit = guild.max_emoji_slots
        full = len(emojis) >= limit
        self._at_limit = full
        self.count_label.configure(
            text=f"{len(emojis)}/{limit} emojis · Nivel {guild.boost_level} de mejoras")
        self.limit_hint.configure(
            text=("Límite alcanzado: mejora el servidor para ampliar los espacios."
                  if full else
                  "Los espacios de emoji crecen con el nivel de mejoras del servidor."))
        self.upload_button.configure(
            state="disabled" if (full or not self._manage) else "normal")
        for child in self.scroll.inner.winfo_children():
            child.destroy()
        self._cancel_card_animations()
        if not emojis:
            tk.Label(self.scroll.inner, text="El servidor todavía no tiene emojis personalizados.",
                     bg=C.CONTENT, fg=C.MUTED, font=self.app.theme.font(10)).pack(pady=30)
            self.scroll.refresh_scroll()
            return
        columns = 6
        grid = tk.Frame(self.scroll.inner, bg=C.CONTENT)
        grid.pack(fill="both", expand=True)
        for column in range(columns):
            grid.grid_columnconfigure(column, weight=1, uniform="emojis")
        for index, emoji in enumerate(emojis):
            card = self._emoji_card(grid, emoji)
            card.grid(row=index // columns, column=index % columns,
                      sticky="nsew", padx=6, pady=6)
        self.scroll.refresh_scroll()

    def _emoji_card(self, parent: tk.Misc, emoji: Emoji) -> tk.Frame:
        app = self.app
        card = Card(parent, padding=10)
        card.configure(cursor="hand2")
        image_label = tk.Label(card.body, bg=C.CARD, fg=C.DIM,
                               text=emoji.name[:1].upper(),
                               font=(app.theme.family, 18, "bold"), width=3, height=1)
        image_label.pack()
        if app.images.enabled and emoji.id:
            if emoji.animated:
                self._load_animated_card(image_label, emoji)
            else:
                photo = app.images.get(
                    emoji.image_url, 40,
                    lambda p, label=image_label: self._apply_photo(label, p))
                if photo is not None:
                    self._apply_photo(image_label, photo)
        name = tk.Label(card.body, text=f":{emoji.name}:", bg=C.CARD, fg=C.TEXT,
                        font=app.theme.font(8, "bold"))
        name.pack(pady=(6, 0))
        if emoji.animated:
            tk.Label(card.body, text="animado", bg=C.CARD_ALT, fg=C.MUTED,
                     font=app.theme.font(7)).pack(pady=(2, 0))
        actions = tk.Frame(card.body, bg=C.CARD)
        actions.pack(fill="x", pady=(6, 0))
        delete = tk.Label(actions, text="Eliminar", bg=C.CARD, fg="#ff8f92",
                          font=app.theme.font(8), cursor="hand2")
        delete.pack()
        delete.bind("<Button-1>", lambda _e, e=emoji: self._delete(e))
        if not self._manage:
            delete.configure(fg=C.FAINT, cursor="")
        for widget in (card, card.body, image_label, name):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", lambda _e, e=emoji: self._edit(e))
        Tooltip(card, f"ID {emoji.id}")
        return card

    def _edit(self, emoji: Emoji) -> None:
        if not self.require("MANAGE_GUILD_EXPRESSIONS", "editar emojis"):
            return
        EmojiEditModal(self, self.app, self, emoji).show()

    def _apply_photo(self, label: tk.Label, photo: tk.PhotoImage | None) -> None:
        if photo is None:
            return
        self._photos[str(label)] = photo
        label.configure(image=photo, text="", width=0, height=0)

    def _load_animated_card(self, label: tk.Label, emoji: Emoji) -> None:
        def work() -> bytes:
            request = urllib.request.Request(
                emoji.image_url, headers={"User-Agent": "DiscordServerStudio/1.0"})
            with urllib.request.urlopen(request, timeout=12) as response:
                return response.read()

        def done(raw: bytes) -> None:
            try:
                from PIL import Image, ImageSequence, ImageTk  # type: ignore
            except ImportError:
                self.app.images.get(
                    emoji.image_url, 40,
                    lambda p: self._apply_photo(label, p))
                return
            try:
                image = Image.open(io.BytesIO(raw))
                frames: list[ImageTk.PhotoImage] = []
                delays: list[int] = []
                for frame in ImageSequence.Iterator(image):
                    delay = int(frame.info.get("duration", 100) or 100)
                    frame = frame.convert("RGBA")
                    frame.thumbnail((40, 40))
                    frames.append(ImageTk.PhotoImage(frame))
                    delays.append(max(40, delay))
                if frames:
                    label._emoji_frames = frames  # type: ignore[attr-defined]
                    self._animate_card(label, frames, delays)
            except Exception:
                pass

        self.run(work, done, lambda _error: None)

    def _animate_card(self, label: tk.Label, frames: list[Any],
                      delays: list[int], index: int = 0) -> None:
        if not label.winfo_exists():
            return
        label.configure(image=frames[index % len(frames)], text="", width=0, height=0)
        delay = delays[index % len(delays)] if delays else 100
        after = label.after(
            delay, lambda: self._animate_card(label, frames, delays, index + 1))
        self._card_animations.append((label, after))

    def _cancel_card_animations(self) -> None:
        for label, after in self._card_animations:
            try:
                label.after_cancel(after)
            except tk.TclError:
                pass
        self._card_animations.clear()

    def _delete(self, emoji: Emoji) -> None:
        if not self.require("MANAGE_GUILD_EXPRESSIONS", "eliminar emojis"):
            return
        dialog = ConfirmDialog(self, "Eliminar emoji",
                               f"Se eliminará :{emoji.name}: del servidor.",
                               confirm_text="Eliminar", danger=True, theme=self.app.theme)
        if not dialog.show():
            return
        client = self.app.client
        guild_id = self.app.guild.id

        def done(_result: Any) -> None:
            self.app.toasts.show(f":{emoji.name}: eliminado.", "success")
            self.refresh()
            self.app.refresh_guild()

        self.run(lambda: client.delete_emoji(guild_id, emoji.id), done)

    def _upload(self) -> None:
        if not self.require("MANAGE_GUILD_EXPRESSIONS", "subir emojis"):
            return
        guild = self.app.guild
        if getattr(self, "_at_limit", False):
            self.toast_warn(
                f"Límite de {guild.max_emoji_slots} emojis alcanzado para el Nivel "
                f"{guild.boost_level}. Mejora el servidor para ampliarlo.")
            return
        EmojiUploadModal(self, self.app, self).show()


class EmojiEditModal(Modal):
    def __init__(self, parent: tk.Misc, app: Any, page: EmojisPage, emoji: Emoji):
        super().__init__(parent, f"Editar :{emoji.name}:", width=520, theme=app.theme,
                         subtitle="Discord permite cambiar el nombre y los roles que pueden "
                                  "usar el emoji; la imagen no se puede reemplazar.")
        self.app = app
        self.page = page
        self.emoji = emoji
        preview = tk.Label(self.body, text="Cargando…", bg=C.INPUT, fg=C.MUTED,
                           font=app.theme.font(9), height=4)
        preview.pack(fill="x", pady=(0, 10))

        def apply(photo: tk.PhotoImage | None) -> None:
            if photo is None:
                preview.configure(text=emoji.name, height=2)
                return
            self._photo = photo
            preview.configure(image=photo, text="", height=0)

        app.images.get(emoji.image_url, 64, apply)

        name_field = Field(self.body, "Nombre del emoji", bg=C.CARD)
        name_field.pack(fill="x", pady=(0, 10))
        self.name_var = tk.StringVar(value=emoji.name)
        name_field.add(ttk.Entry(name_field.slot, textvariable=self.name_var))

        roles_field = Field(self.body, "Roles permitidos (IDs separados por comas)",
                            "Vacío = todos los miembros.", bg=C.CARD)
        roles_field.pack(fill="x")
        self.roles_var = tk.StringVar(value=", ".join(emoji.roles))
        roles_field.add(ttk.Entry(roles_field.slot, textvariable=self.roles_var))
        self.add_button("Cancelar", self.close)
        self.add_button("Guardar cambios", self._submit, style="Accent.TButton")

    def _submit(self) -> None:
        name = self.name_var.get().strip()
        if not name or len(name) > 32 or not all(ch in NAME_ALLOWED for ch in name):
            self.show_error("Nombre no válido: letras, números y guiones bajos (máx. 32).")
            return
        roles = [part.strip() for part in self.roles_var.get().split(",") if part.strip()]
        client = self.app.client
        guild_id = self.app.guild.id
        self.set_busy(True)

        def done(_result: Any) -> None:
            self.app.toasts.show(f":{name}: actualizado.", "success")
            self.close()
            self.page.refresh()
            self.app.refresh_guild()

        def failed(error: BaseException) -> None:
            self.set_busy(False)
            self.show_error(str(error))

        self.app.run_task(
            lambda: client.update_emoji(guild_id, self.emoji.id,
                                        {"name": name, "roles": roles}),
            done, failed)


class EmojiUploadModal(Modal):
    def __init__(self, parent: tk.Misc, app: Any, page: EmojisPage):
        super().__init__(parent, "Subir emoji", width=520, theme=app.theme,
                         subtitle="PNG, JPG o GIF de hasta 256 KB. El nombre usa letras, "
                                  "números y guiones bajos.")
        self.app = app
        self.page = page
        self._data_uri = ""

        name_field = Field(self.body, "Nombre del emoji", bg=C.CARD)
        name_field.pack(fill="x", pady=(0, 12))
        self.name_var = tk.StringVar()
        entry = ttk.Entry(name_field.slot, textvariable=self.name_var)
        name_field.add(entry)
        entry.focus_set()

        file_field = Field(self.body, "Archivo", bg=C.CARD)
        file_field.pack(fill="x", pady=(0, 8))
        row = tk.Frame(file_field.slot, bg=C.CARD)
        row.pack(fill="x")
        self.path_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.path_var, state="readonly").pack(
            side="left", fill="x", expand=True)
        ttk.Button(row, text="Elegir…", style="Small.TButton",
                   command=self._choose).pack(side="left", padx=(6, 0))
        self.preview = tk.Label(self.body, text="Sin archivo seleccionado", bg=C.INPUT,
                                fg=C.MUTED, font=app.theme.font(9), height=4)
        self.preview.pack(fill="x", pady=(8, 0))
        self._photo: tk.PhotoImage | None = None
        self._preview_frames: list[Any] = []
        self._preview_delays: list[int] = []
        self._preview_index = 0
        self._preview_after: str | None = None

        self.add_button("Cancelar", self.close)
        self.add_button("Subir emoji", self._submit, style="Accent.TButton")

    def close(self) -> None:
        self._stop_animation()
        super().close()

    def _choose(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="Elegir imagen",
            filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.gif *.webp")])
        if not path:
            return
        self.path_var.set(path)
        try:
            self._data_uri = image_to_data_uri(path, MAX_EMOJI_BYTES)
        except (ValueError, OSError) as error:
            self._data_uri = ""
            self.show_error(str(error))
            self.preview.configure(text="Archivo no válido", image="")
            return
        self._show_preview(path)
        if not self.name_var.get():
            stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            self.name_var.set("".join(ch for ch in stem if ch in NAME_ALLOWED)[:32])

    def _show_preview(self, path: str) -> None:
        self._stop_animation()
        self.preview.configure(image="", text="Cargando vista previa…", height=2)
        try:
            from PIL import Image, ImageSequence, ImageTk  # type: ignore
        except ImportError:
            Image = None
        if Image is not None:
            try:
                image = Image.open(path)
                frames: list[ImageTk.PhotoImage] = []
                delays: list[int] = []
                for frame in ImageSequence.Iterator(image):
                    duration = int(frame.info.get("duration", 100) or 100)
                    frame = frame.convert("RGBA")
                    frame.thumbnail((260, 150))
                    frames.append(ImageTk.PhotoImage(frame))
                    delays.append(max(40, duration))
                if frames:
                    self._preview_frames = frames
                    self._preview_delays = delays
                    self._preview_index = 0
                    self._animate_preview()
                    return
            except Exception:
                pass
        try:
            photo = tk.PhotoImage(file=path)
            factor = max(1, (photo.width() + 159) // 160,
                         (photo.height() + 139) // 140)
            self._photo = photo.subsample(factor)
            self.preview.configure(image=self._photo, text="", height=0)
        except tk.TclError:
            self.preview.configure(
                text="Vista previa no disponible para este formato. "
                     "Instala Pillow para ver JPG/WebP.",
                image="", height=2)

    def _animate_preview(self) -> None:
        if not self._preview_frames:
            return
        index = self._preview_index % len(self._preview_frames)
        self.preview.configure(image=self._preview_frames[index], text="", height=0)
        delay = self._preview_delays[index] if self._preview_delays else 100
        self._preview_index += 1
        if len(self._preview_frames) > 1:
            self._preview_after = self.after(delay, self._animate_preview)

    def _stop_animation(self) -> None:
        if self._preview_after is not None:
            try:
                self.after_cancel(self._preview_after)
            except tk.TclError:
                pass
            self._preview_after = None

    def _submit(self) -> None:
        name = self.name_var.get().strip()
        if not name or not all(ch in NAME_ALLOWED for ch in name) or len(name) > 32:
            self.show_error("Nombre no válido: usa letras, números y guiones bajos (máx. 32).")
            return
        if not self._data_uri:
            self.show_error("Elige una imagen válida.")
            return
        client = self.app.client
        guild_id = self.app.guild.id
        self.set_busy(True)

        def done(_result: Any) -> None:
            self.app.toasts.show(f":{name}: subido.", "success")
            self.close()
            self.page.refresh()
            self.app.refresh_guild()

        def failed(error: BaseException) -> None:
            self.set_busy(False)
            self.show_error(str(error))

        self.app.run_task(lambda: client.create_emoji(guild_id, name, self._data_uri),
                          done, failed)
