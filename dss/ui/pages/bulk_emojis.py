"""Gestión masiva de emojis mediante JSON (crear, actualizar y eliminar)."""
from __future__ import annotations

import base64
import json
import mimetypes
import re
import tkinter as tk
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any

from ...models import Emoji
from ...util import MAX_EMOJI_BYTES
from ..theme import C
from ..widgets import Modal, Table, TableColumn
from .bulk_json_nav import clean_json_text, load_clipboard_object, source_block
from .json_syntax import configure_json_tags, highlight_json
from .base import Page

NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,32}$")
ACTIONS = {"create": "Crear", "update": "Actualizar", "delete": "Eliminar",
           "view": "Ver"}


class BulkEmojisTab(tk.Frame):
    def __init__(self, parent: tk.Misc, app: Any, page: Page):
        super().__init__(parent, bg=C.CONTENT)
        self.app = app
        self.page = page
        self._emojis: list[Emoji] = []
        self._ops: list[dict[str, Any]] = []
        self._errors: list[dict[str, Any]] = []
        self._running = False
        self._index = 0
        self._snapshot = False
        self._preview_after: str | None = None
        self._build()

    def _build(self) -> None:
        app = self.app
        outer = tk.Frame(self, bg=C.CONTENT)
        outer.pack(fill="both", expand=True, padx=28, pady=(10, 20))
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(1, weight=3)
        outer.grid_rowconfigure(2, weight=2)

        toolbar = tk.Frame(outer, bg=C.CONTENT)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.btn_load = ttk.Button(toolbar, text="Cargar archivo JSON…",
                                   style="Small.TButton", command=self.load_file)
        self.btn_load.pack(side="left")
        self.btn_paste = ttk.Button(toolbar, text="Pegar JSON", style="Small.TButton",
                                    command=self.paste_json)
        self.btn_paste.pack(side="left", padx=(6, 0))
        self.btn_format = ttk.Button(toolbar, text="Formatear", style="Small.TButton",
                                     command=self.format_document)
        self.btn_format.pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Copiar ID del servidor", style="Small.TButton",
                   command=self.copy_guild_id).pack(side="left", padx=(6, 0))
        self.btn_generate = ttk.Button(toolbar, text="Generar JSON",
                                       style="Small.TButton", command=self.generate)
        self.btn_generate.pack(side="left", padx=(6, 0))
        self.btn_copy = ttk.Button(toolbar, text="Copiar JSON", style="Small.TButton",
                                   command=self.copy_json)
        self.btn_copy.pack(side="left", padx=(6, 0))
        self.btn_export = ttk.Button(toolbar, text="Exportar JSON…",
                                     style="Small.TButton", command=self.export,
                                     state="disabled")
        self.btn_export.pack(side="left", padx=(6, 0))

        editor = tk.Frame(outer, bg=C.INPUT, highlightbackground=C.BORDER,
                          highlightthickness=1)
        editor.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        editor.grid_rowconfigure(0, weight=1)
        editor.grid_columnconfigure(0, weight=1)
        self.text = tk.Text(editor, bg=C.INPUT, fg=C.TEXT, insertbackground=C.TEXT,
                            selectbackground=C.ACCENT, selectforeground=C.WHITE,
                            relief="flat", bd=0, wrap="none", undo=True,
                            font=(app.theme.mono_family, 9), padx=10, pady=8,
                            highlightthickness=0)
        self.text.grid(row=0, column=0, sticky="nsew")
        vbar = ttk.Scrollbar(editor, orient="vertical", command=self.text.yview)
        vbar.grid(row=0, column=1, sticky="ns")
        hbar = ttk.Scrollbar(editor, orient="horizontal", command=self.text.xview)
        hbar.grid(row=1, column=0, sticky="ew")
        self.text.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        self.text.bind("<<Modified>>", self._on_modified)
        configure_json_tags(self.text, app.theme)

        columns = [
            TableColumn("action", "Acción", 90),
            TableColumn("name", "Nombre", 180, stretch=True),
            TableColumn("detail", "ID / Imagen", 260, stretch=True),
            TableColumn("roles", "Roles", 220, stretch=True),
            TableColumn("status", "Estado", 260, stretch=True),
        ]
        self.table = Table(outer, columns, height=7, theme=app.theme, multi=False,
                           empty_text="Carga o pega el JSON de emojis.",
                           on_select=self._selected_operation, hscroll=True)
        self.table.grid(row=2, column=0, sticky="nsew")

        buttons = tk.Frame(outer, bg=C.CONTENT)
        buttons.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.btn_clear = ttk.Button(buttons, text="Limpiar", style="Ghost.TButton",
                                    command=self.clear)
        self.btn_clear.pack(side="left")
        self.btn_errors = ttk.Button(buttons, text="Ver errores",
                                     style="SmallDanger.TButton",
                                     command=self.show_errors, state="disabled")
        self.btn_errors.pack(side="left", padx=(6, 0))
        self.btn_run = ttk.Button(buttons, text="Cargar", style="Accent.TButton",
                                  command=self.run)
        self.btn_run.pack(side="right")
        self.progress = ttk.Progressbar(outer, mode="determinate",
                                        style="Horizontal.TProgressbar")
        self.progress.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self.status = tk.Label(outer, text="", bg=C.CONTENT, fg=C.MUTED,
                               font=app.theme.font(8), anchor="w", justify="left",
                               wraplength=1000)
        self.status.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        self._update_buttons()

    def set_emojis(self, emojis: list[Emoji]) -> None:
        self._emojis = list(emojis)

    def on_show(self) -> None:
        self._update_buttons()

    # -- editor --------------------------------------------------------- #
    def load_file(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="Cargar JSON de emojis",
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")])
        if not path:
            return
        try:
            self.load_text(Path(path).read_text("utf-8-sig"))
        except (OSError, UnicodeError) as error:
            self._set_status(f"No se pudo leer: {error}", C.RED)

    def paste_json(self) -> None:
        try:
            raw = self.clipboard_get()
        except tk.TclError:
            try:
                raw = self.clipboard_get(type="STRING")
            except tk.TclError:
                self._set_status("El portapapeles está vacío o no es accesible.", C.RED)
                return
        try:
            load_clipboard_object(raw)
        except ValueError as error:
            self._set_status(f"{error} No se pegó nada.", C.RED)
            return
        self.load_text(clean_json_text(raw))
        self._set_status("JSON pegado desde el portapapeles.", C.GREEN)

    def load_text(self, raw: str) -> None:
        try:
            data = json.loads(raw)
            pretty = json.dumps(data, indent=2, ensure_ascii=False)
        except json.JSONDecodeError as error:
            self._set_status(f"JSON inválido: {error.msg} "
                             f"(línea {error.lineno}, columna {error.colno}).", C.RED)
            return
        self._snapshot = False
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", pretty)
        self.text.edit_modified(False)
        self._highlight()
        self.preview()

    def format_document(self) -> None:
        self.load_text(self.text.get("1.0", "end-1c"))

    def copy_guild_id(self) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(self.app.guild.id)
            self._set_status("ID del servidor copiado.", C.GREEN)
        except tk.TclError:
            pass

    def copy_json(self) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(self.text.get("1.0", "end-1c"))
            self._set_status("JSON copiado.", C.GREEN)
        except tk.TclError:
            pass

    def export(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, title="Exportar JSON de emojis",
            defaultextension=".json", initialfile="emojis.json",
            filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            Path(path).write_text(self.text.get("1.0", "end-1c"), "utf-8")
            self._set_status(f"Exportado a {path}", C.GREEN)
        except OSError as error:
            self._set_status(f"No se pudo exportar: {error}", C.RED)

    def _on_modified(self, _event: Any = None) -> None:
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        self._highlight()
        if self._preview_after:
            self.after_cancel(self._preview_after)
        self._preview_after = self.after(400, self.preview)

    def _highlight(self) -> None:
        highlight_json(self.text)

    # -- parser --------------------------------------------------------- #
    def preview(self) -> None:
        self._preview_after = None
        raw = self.text.get("1.0", "end-1c").strip()
        if not raw:
            self._ops, self._errors = [], []
            self.table.set_rows([])
            self._set_status("", C.MUTED)
            self._update_buttons()
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as error:
            self._ops, self._errors = [], []
            self.table.set_rows([])
            self._set_status(f"JSON inválido: {error.msg} "
                             f"(línea {error.lineno}, columna {error.colno}).", C.RED)
            self._update_buttons()
            return
        try:
            self._ops = self._parse(data)
        except ValueError as error:
            self._ops, self._errors = [], []
            self.table.set_rows([])
            self._set_status(str(error), C.RED)
            self._update_buttons()
            return
        self._snapshot = bool(data.get("readOnly") or data.get("read_only"))
        self._errors = [op for op in self._ops if not op["valid"]]
        extra = []
        if "categories" in data or "channels" in data:
            extra.append("canales")
        if "roles" in data:
            extra.append("roles")
        extra_text = (" · Ignoradas las secciones: " + ", ".join(extra)
                      + ". Usa su gestor correspondiente.") if extra else ""
        rows = []
        for index, op in enumerate(self._ops):
            rows.append({
                "_id": str(index), "_raw": op,
                "action": op["label"], "name": op["name"],
                "detail": op["detail"], "roles": op["roles_text"],
                "status": "Listo" if op["valid"] else f"Error: {op['error']}",
            })
        self.table.set_rows(rows)
        self.progress.configure(maximum=max(1, len(self._ops)), value=0)
        if self._snapshot and not self._errors:
            self._set_status(f"Instantánea no ejecutable · {len(self._ops)} emojis · "
                             "Cargar está desactivado." + extra_text, C.YELLOW)
        elif self._errors:
            self._set_status(f"{len(self._ops)} operaciones · "
                             f"{len(self._errors)} con errores." + extra_text, C.RED)
        else:
            self._set_status(f"{len(self._ops)} operaciones listas." + extra_text, C.GREEN)
        self._update_buttons()

    def _parse(self, data: dict) -> list[dict]:
        if not isinstance(data, dict):
            raise ValueError("El JSON debe ser un objeto.")
        if data.get("readOnly") or data.get("read_only"):
            snapshot = True
        else:
            snapshot = False
        guild_id = data.get("guildId") or data.get("guild_id")
        if guild_id not in (None, "") and str(guild_id) != str(self.app.guild.id):
            raise ValueError("El JSON pertenece a otro servidor.")
        items = data.get("emojis")
        if not isinstance(items, list):
            raise ValueError("Falta la lista «emojis».")
        by_id = {emoji.id: emoji for emoji in self._emojis}
        limit = self.app.guild.max_emoji_slots
        creates = 0
        operations: list[dict] = []
        for index, item in enumerate(items):
            source = f"emojis[{index}]"
            if not isinstance(item, dict):
                raise ValueError(f"{source} debe ser un objeto.")
            action = str(item.get("action") or ("view" if snapshot else "")).lower()
            if action == "view" and snapshot:
                emoji_id = str(item.get("emojiId") or "")
                operations.append({
                    "source": source, "action": "view", "label": "Ver",
                    "name": str(item.get("name") or ""), "detail": emoji_id or "—",
                    "roles_text": _roles_text(item.get("roles") or []),
                    "valid": True, "error": "", "fields": {}, "emoji_id": emoji_id,
                    "image": "", "roles": [],
                })
                continue
            if action not in ("create", "update", "delete"):
                operations.append(self._invalid(source, item, "action debe ser create/update/delete."))
                continue
            if action == "create":
                creates += 1
                name = str(item.get("name") or "").strip()
                image = str(item.get("image") or "").strip()
                roles = item.get("roles") or []
                error = ""
                if not NAME_RE.match(name):
                    error = "Nombre no válido (1-32 letras, números o _)."
                elif not image:
                    error = "Falta «image»."
                elif len(self._emojis) + creates > limit:
                    error = f"Supera el límite de {limit} emojis del servidor."
                elif not isinstance(roles, list):
                    error = "«roles» debe ser una lista."
                op = self._op(source, action, name, image, roles, error)
                operations.append(op)
            elif action == "update":
                emoji_id = str(item.get("emojiId") or "")
                emoji = by_id.get(emoji_id)
                fields = {}
                if "name" in item:
                    name = str(item["name"] or "").strip()
                    if not NAME_RE.match(name):
                        operations.append(self._invalid(source, item,
                                                        "Nombre no válido.", emoji_id))
                        continue
                    fields["name"] = name
                if "roles" in item:
                    roles = item.get("roles") or []
                    if not isinstance(roles, list):
                        operations.append(self._invalid(source, item,
                                                        "«roles» debe ser una lista.", emoji_id))
                        continue
                    fields["roles"] = [str(role) for role in roles]
                if emoji is None:
                    operations.append(self._invalid(source, item, "El emoji no existe.", emoji_id))
                elif not fields:
                    operations.append(self._invalid(source, item, "No hay cambios.", emoji_id))
                else:
                    operations.append({
                        "source": source, "action": "update", "label": "Actualizar",
                        "name": fields.get("name", emoji.name), "detail": emoji_id,
                        "roles_text": _roles_text(fields.get("roles", emoji.roles)),
                        "valid": True, "error": "", "fields": fields,
                        "emoji_id": emoji_id, "image": "", "roles": [],
                    })
            else:
                emoji_id = str(item.get("emojiId") or "")
                emoji = by_id.get(emoji_id)
                if emoji is None:
                    operations.append(self._invalid(source, item, "El emoji no existe.", emoji_id))
                else:
                    operations.append({
                        "source": source, "action": "delete", "label": "Eliminar",
                        "name": emoji.name, "detail": emoji_id,
                        "roles_text": _roles_text(emoji.roles), "valid": True,
                        "error": "", "fields": {}, "emoji_id": emoji_id,
                        "image": "", "roles": [],
                    })
        return operations

    def _op(self, source: str, action: str, name: str, image: str,
            roles: list, error: str) -> dict:
        return {
            "source": source, "action": action, "label": ACTIONS[action],
            "name": name, "detail": _image_detail(image),
            "roles_text": _roles_text(roles), "valid": not error, "error": error,
            "fields": {}, "emoji_id": "", "image": image,
            "roles": [str(role) for role in roles] if isinstance(roles, list) else [],
        }

    def _invalid(self, source: str, item: dict, error: str,
                 emoji_id: str = "") -> dict:
        action = str(item.get("action") or "create").lower()
        return {
            "source": source, "action": action,
            "label": ACTIONS.get(action, "Error"),
            "name": str(item.get("name") or ""), "detail": emoji_id or "—",
            "roles_text": _roles_text(item.get("roles") or []), "valid": False,
            "error": error, "fields": {}, "emoji_id": emoji_id, "image": "",
            "roles": [],
        }

    # -- ejecución / instantánea --------------------------------------- #
    def run(self) -> None:
        if self._running or self._snapshot or not self.page.can("MANAGE_GUILD_EXPRESSIONS"):
            return
        self.preview()
        if not self._ops or self._errors:
            return
        self._running = True
        self._index = 0
        self.text.configure(state="disabled")
        self._update_buttons()
        self._set_status("Iniciando…", C.YELLOW)
        self.after(20, self._run_next)

    def _run_next(self) -> None:
        if not self._running:
            return
        if self._index >= len(self._ops):
            self._running = False
            self.text.configure(state="normal")
            self.progress.configure(value=len(self._ops))
            self._set_status(f"Completado: {len(self._ops)} operaciones.", C.GREEN)
            self._update_buttons()
            self.page.refresh()
            self.app.refresh_guild()
            return
        op = self._ops[self._index]
        self.progress.configure(value=self._index)
        self._set_status(f"{self._index + 1}/{len(self._ops)} · {op['label']} "
                         f"«{op['name']}»…", C.YELLOW)
        self.after(120, lambda: self._start_op(op))

    def _start_op(self, op: dict) -> None:
        if not self._running:
            return
        client = self.app.client
        guild_id = self.app.guild.id

        def work() -> None:
            if op["action"] == "create":
                client.create_emoji(guild_id, op["name"],
                                    _image_to_uri(op["image"]), op["roles"] or None)
            elif op["action"] == "update":
                client.update_emoji(guild_id, op["emoji_id"], op["fields"])
            else:
                client.delete_emoji(guild_id, op["emoji_id"])

        def done(_result: Any) -> None:
            self._index += 1
            self.progress.configure(value=self._index)
            self._set_status(f"{self._index}/{len(self._ops)} · {op['label']} completado.",
                             C.GREEN)
            self.after(120, self._run_next)

        def failed(error: BaseException) -> None:
            self._running = False
            self.text.configure(state="normal")
            self._set_status(f"Error en «{op['name']}»: {error}", C.RED)
            self._update_buttons()
            self.page.refresh()

        self.page.run(work, done, failed)

    def generate(self) -> None:
        if self._running:
            return
        data = {
            "guild_id": self.app.guild.id,
            "guild_name": self.app.guild.name,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "read_only": True,
            "snapshot_version": 1,
            "emojis": [{
                "emojiId": emoji.id,
                "name": emoji.name,
                "animated": emoji.animated,
                "roles": emoji.roles,
            } for emoji in self._emojis],
        }
        self._snapshot = True
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", json.dumps(data, indent=2, ensure_ascii=False))
        self.text.configure(state="disabled")
        self._highlight()
        rows = [{
            "_id": emoji.id, "action": "Ver", "name": emoji.name,
            "detail": "animado" if emoji.animated else "estático",
            "roles": _roles_text(emoji.roles), "status": "Instantánea",
        } for emoji in self._emojis]
        self.table.set_rows(rows)
        self.progress.configure(maximum=1, value=0)
        self._set_status(f"JSON generado: {len(self._emojis)} emojis. "
                         "Instantánea no ejecutable; puedes copiarla o exportarla.", C.GREEN)
        self._update_buttons()

    def clear(self) -> None:
        if self._running:
            return
        self._snapshot = False
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self._ops, self._errors = [], []
        self.table.set_rows([])
        self.progress.configure(maximum=1, value=0)
        self._set_status("", C.MUTED)
        self._update_buttons()

    def _selected_operation(self, rows: list[dict]) -> None:
        if self._running or not rows:
            return
        try:
            self.text.tag_remove("op_focus", "1.0", "end")
        except tk.TclError:
            return
        operation = rows[0].get("_raw") or {}
        path = operation.get("source") or ""
        if path:
            block = source_block(self.text.get("1.0", "end-1c"), path)
            if block:
                start, end = block
                self.text.tag_add("op_focus", f"1.0+{start}c", f"1.0+{end}c")
                self.text.see(f"1.0+{start}c")
        if operation:
            self._set_status(f"{operation.get('label')} "
                             f"«{operation.get('name')}» · "
                             f"{operation.get('error') or operation.get('detail')}",
                             C.RED if not operation.get("valid") else C.DIM)

    def show_errors(self) -> None:
        if not self._errors:
            return
        modal = Modal(
            self, "Errores del JSON de emojis", width=780,
            subtitle=f"{len(self._errors)} operaciones no se pueden ejecutar. "
                     "La ruta indica dónde está el problema.",
            theme=self.app.theme)
        text = tk.Text(modal.body, bg=C.INPUT, fg=C.TEXT, relief="flat", bd=0,
                       wrap="word", font=(self.app.theme.mono_family, 9),
                       padx=10, pady=8, height=18)
        text.pack(fill="both", expand=True)
        for number, operation in enumerate(self._errors, 1):
            text.insert("end", f"{number}. {operation.get('source') or '?'}\n")
            text.insert("end", f"   {operation.get('label')} "
                               f"«{operation.get('name') or '—'}»\n")
            text.insert("end", f"   {operation.get('error')}\n\n")
        text.configure(state="disabled")
        modal.add_button("Cerrar", modal.close)
        modal.show()

    def _update_buttons(self) -> None:
        busy = self._running
        can_edit = self.page.can("MANAGE_GUILD_EXPRESSIONS") and not busy and not self._snapshot
        for button in (self.btn_load, self.btn_paste, self.btn_format,
                       self.btn_generate):
            button.configure(state="disabled" if busy else "normal")
        self.btn_export.configure(state="normal" if self._snapshot else "disabled")
        self.btn_copy.configure(state="normal" if self.text.get("1.0", "end-1c").strip()
                                else "disabled")
        self.btn_clear.configure(state="disabled" if busy else "normal")
        self.btn_run.configure(
            state="normal" if (can_edit and self._ops and not self._errors) else "disabled")
        has_errors = bool(self._errors) and not self._snapshot and not busy
        self.btn_errors.configure(
            text=(f"Ver errores ({len(self._errors)})"
                  if self._errors else "Ver errores"),
            state="normal" if has_errors else "disabled")

    def _set_status(self, text: str, color: str = C.MUTED) -> None:
        self.status.configure(text=text, fg=color)


def _roles_text(roles: list) -> str:
    values = [str(role) for role in roles if str(role)]
    return ", ".join(values) if values else "Todos"


def _image_detail(image: str) -> str:
    if image.startswith("data:"):
        return "data URI"
    if image.startswith(("http://", "https://")):
        return image[:80]
    return image


def _image_to_uri(image: str) -> str:
    if image.startswith("data:image/"):
        return image
    if image.startswith(("http://", "https://")):
        request = urllib.request.Request(image, headers={"User-Agent": "DiscordServerStudio/1.0"})
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read(MAX_EMOJI_BYTES + 1)
            content_type = response.headers.get("Content-Type", "image/png").split(";")[0]
    else:
        raw = Path(image).read_bytes()
        content_type = mimetypes.guess_type(image)[0] or "image/png"
    if len(raw) > MAX_EMOJI_BYTES:
        raise ValueError("La imagen supera 256 KB.")
    if not content_type.startswith("image/"):
        raise ValueError("El archivo no es una imagen.")
    return f"data:{content_type};base64,{base64.b64encode(raw).decode('ascii')}"
