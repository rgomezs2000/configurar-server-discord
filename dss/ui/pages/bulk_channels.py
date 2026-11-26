"""Gestión masiva de categorías y canales por JSON."""
from __future__ import annotations

import json
import re
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any

from ...models import Channel
from ...constants import PERMISSION_BY_KEY
from ..theme import C
from ..widgets import Modal, Table, TableColumn
from .bulk_json_nav import clean_json_text, load_clipboard_object, source_block
from .json_syntax import configure_json_tags, highlight_json

ACTIONS = {"create": "Crear", "update": "Actualizar", "delete": "Eliminar",
           "view": "Ver"}
SLUG_TYPES = {0, 5, 15}


class BulkChannelsTab(tk.Frame):
    def __init__(self, parent: tk.Misc, app: Any, page: Any):
        super().__init__(parent, bg=C.CONTENT)
        self.app = app
        self.page = page
        self._ops: list[dict] = []
        self._errors: list[dict] = []
        self._json_data: dict | None = None
        self._table_anchor: str | None = None
        self._drag_mode: str | None = None
        self._drag_start: str | None = None
        self._drag_base: set[str] = set()
        self._drag_toggled: set[str] = set()
        self._drag_deselect = False
        self._drag_moved = False
        self._running = False
        self._index = 0
        self._snapshot = False
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
                                    command=self.paste)
        self.btn_paste.pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Formatear", style="Small.TButton",
                   command=self.format).pack(side="left", padx=(6, 0))
        self.btn_generate = ttk.Button(toolbar, text="Generar JSON",
                                       style="Small.TButton", command=self.generate)
        self.btn_generate.pack(side="left", padx=(6, 0))
        self.btn_copy = ttk.Button(toolbar, text="Copiar JSON", style="Small.TButton",
                                   command=self.copy)
        self.btn_copy.pack(side="left", padx=(6, 0))
        self.btn_export = ttk.Button(toolbar, text="Exportar JSON…",
                                     style="Small.TButton", command=self.export)
        self.btn_export.pack(side="left", padx=(6, 0))

        editor = tk.Frame(outer, bg=C.INPUT, highlightbackground=C.BORDER,
                          highlightthickness=1)
        editor.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        editor.grid_rowconfigure(0, weight=1)
        editor.grid_columnconfigure(0, weight=1)
        self.text = tk.Text(editor, bg=C.INPUT, fg=C.TEXT, insertbackground=C.TEXT,
                            relief="flat", bd=0, wrap="none", undo=True,
                            font=(app.theme.mono_family, 9), padx=10, pady=8)
        self.text.grid(row=0, column=0, sticky="nsew")
        ttk.Scrollbar(editor, orient="vertical", command=self.text.yview).grid(
            row=0, column=1, sticky="ns")
        ttk.Scrollbar(editor, orient="horizontal", command=self.text.xview).grid(
            row=1, column=0, sticky="ew")
        self.text.bind("<<Modified>>", self._on_modified)
        configure_json_tags(self.text, app.theme)
        columns = [TableColumn("action", "Acción", 100),
                   TableColumn("kind", "Grupo", 100),
                   TableColumn("name", "Nombre", 300, stretch=True),
                   TableColumn("detail", "Detalle", 300, stretch=True),
                   TableColumn("status", "Estado", 300, stretch=True)]
        self.table = Table(outer, columns, height=7, theme=app.theme, multi=True,
                           empty_text="Carga o pega el JSON de canales.",
                           on_select=self._selected_operation, hscroll=True)
        self.table.grid(row=2, column=0, sticky="nsew")
        self.table.tree.unbind("<Button-3>")
        self.table.tree.bind("<Button-3>", self._row_context)
        self.table.tree.bind("<ButtonPress-1>", self._table_press)
        self.table.tree.bind("<B1-Motion>", self._table_drag_motion, add="+")
        self.table.tree.bind("<ButtonRelease-1>", self._table_drag_release, add="+")
        self.table.tree.bind("<Shift-Up>", lambda _e: self._extend_selection(-1))
        self.table.tree.bind("<Shift-Down>", lambda _e: self._extend_selection(1))
        self.table.tree.bind("<Shift-Prior>", lambda _e: self._extend_selection(-7))
        self.table.tree.bind("<Shift-Next>", lambda _e: self._extend_selection(7))
        self.table.tree.bind("<Delete>", self._delete_selected)
        self._row_menu = tk.Menu(self, tearoff=0, bg=C.CARD, fg=C.TEXT,
                                 activebackground=C.ACCENT_SOFT,
                                 activeforeground=C.TEXT)
        self._row_menu.add_command(label="Eliminar del JSON",
                                   command=self._delete_selected)
        buttons = tk.Frame(outer, bg=C.CONTENT)
        buttons.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text="Limpiar", style="Ghost.TButton",
                   command=self.clear).pack(side="left")
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

    def on_show(self) -> None:
        self._update_buttons()

    # -- editor --------------------------------------------------------- #
    def load_file(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Cargar JSON de canales",
                                          filetypes=[("JSON", "*.json")])
        if path:
            self.load_text(Path(path).read_text("utf-8-sig"))

    def paste(self) -> None:
        try:
            raw = self.clipboard_get()
        except tk.TclError:
            try:
                raw = self.clipboard_get(type="STRING")
            except tk.TclError:
                self._status("El portapapeles está vacío o no es accesible. "
                             "Copia el JSON y vuelve a intentarlo.", C.RED)
                return
        try:
            load_clipboard_object(raw)
        except ValueError as error:
            self._status(f"{error} No se pegó nada.", C.RED)
            return
        self.load_text(clean_json_text(raw))
        self._status("JSON pegado desde el portapapeles.", C.GREEN)

    def load_text(self, raw: str) -> None:
        try:
            data = json.loads(raw)
            pretty = json.dumps(data, indent=2, ensure_ascii=False)
        except json.JSONDecodeError as error:
            self._status(f"JSON inválido: {error.msg} (línea {error.lineno}).", C.RED)
            return
        self._snapshot = False
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", pretty)
        self.text.edit_modified(False)
        self._highlight()
        self.preview()

    def format(self) -> None:
        self.load_text(self.text.get("1.0", "end-1c"))

    def copy(self) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(self.text.get("1.0", "end-1c"))
            self._status("JSON copiado.", C.GREEN)
        except tk.TclError:
            pass

    def export(self) -> None:
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".json",
                                            filetypes=[("JSON", "*.json")])
        if path:
            Path(path).write_text(self.text.get("1.0", "end-1c"), "utf-8")

    def _on_modified(self, _event: Any = None) -> None:
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self._highlight()
            self.after(400, self.preview)

    def _highlight(self) -> None:
        highlight_json(self.text)

    # -- parser --------------------------------------------------------- #
    def preview(self) -> None:
        raw = self.text.get("1.0", "end-1c").strip()
        if not raw:
            self._ops, self._errors = [], []
            self.table.set_rows([])
            self._status("", C.MUTED)
            self._update_buttons()
            return
        try:
            data = json.loads(raw)
            self._ops = self._parse(data)
        except (json.JSONDecodeError, ValueError) as error:
            self._ops, self._errors = [], []
            self._json_data = None
            self.table.set_rows([])
            self._status(str(error), C.RED)
            self._update_buttons()
            return
        self._json_data = data
        self._snapshot = bool(data.get("readOnly") or data.get("read_only"))
        self._errors = [op for op in self._ops if not op["valid"]]
        extra = []
        if "emojis" in data:
            extra.append("emojis")
        if "roles" in data:
            extra.append("roles")
        extra_text = (" · Ignoradas las secciones: " + ", ".join(extra)
                      + ". Usa su gestor correspondiente.") if extra else ""
        rows: list[dict] = []
        seen_categories = False
        seen_uncategorized = False
        for i, op in enumerate(self._ops):
            if op["kind"] == "Categoría" and not seen_categories:
                rows.append({"_id": "__group_categories", "action": "",
                             "kind": "", "name": "CATEGORÍAS", "detail": "",
                             "status": ""})
                seen_categories = True
            elif op["kind"] == "Sin categoría" and not seen_uncategorized:
                rows.append({"_id": "__group_uncategorized", "action": "",
                             "kind": "", "name": "SIN CATEGORÍA", "detail": "",
                             "status": ""})
                seen_uncategorized = True
            rows.append({"_id": str(i), "_raw": op, "action": op["label"],
                         "kind": op["kind"], "name": op["indent"] + op["name"],
                         "detail": op["detail"], "status": op["status"]})
        self.table.set_rows(rows)
        self.progress.configure(maximum=max(1, len(self._ops)), value=0)
        if self._snapshot:
            self._status(f"Instantánea no ejecutable · {len(self._ops)} filas · "
                         "Cargar está desactivado." + extra_text, C.YELLOW)
        elif self._errors:
            self._status(f"{len(self._ops)} operaciones · "
                         f"{len(self._errors)} con errores." + extra_text, C.RED)
        else:
            self._status(f"{len(self._ops)} operaciones listas." + extra_text, C.GREEN)
        self._update_buttons()

    def _parse(self, data: dict) -> list[dict]:
        if data.get("readOnly"):
            pass  # se muestra como instantánea, pero Cargar queda desactivado
        guild_id = data.get("guildId") or data.get("guild_id")
        if guild_id and str(guild_id) != str(self.app.guild.id):
            raise ValueError("El JSON pertenece a otro servidor.")
        categories = data.get("categories") or []
        uncategorized = data.get("uncategorizedChannels") or []
        snapshot = bool(data.get("readOnly") or data.get("read_only"))
        if not isinstance(categories, list) or not isinstance(uncategorized, list):
            raise ValueError("categories y uncategorizedChannels deben ser listas.")
        by_id = {c.id: c for c in self.page._channels}
        ops: list[dict] = []
        for index, category in enumerate(categories):
            if not isinstance(category, dict):
                raise ValueError(f"categories[{index}] debe ser objeto.")
            action = str(category.get("action") or ("view" if snapshot else "create"))
            name = str(category.get("name") or "")
            category_id = str(category.get("categoryId") or f"__category_{index}")
            if action == "create":
                valid = bool(name.strip())
            else:
                valid = action in ACTIONS and bool(category.get("categoryId"))
            ops.append({"source": f"categories[{index}]", "action": action,
                        "label": ACTIONS.get(action, "Error"), "kind": "Categoría",
                        "name": name or category_id, "indent": "",
                        "detail": category_id, "valid": valid,
                        "error": "" if valid else "Categoría no válida.",
                        "type": 4, "parent_id": None, "channel_id": category_id,
                        "raw": category, "status": "Listo" if valid else "Error"})
            for child_index, child in enumerate(category.get("channels") or []):
                if not isinstance(child, dict):
                    continue
                child_action = str(child.get("action") or ("view" if snapshot else "create"))
                child_name = str(child.get("name") or "")
                child_type = _type_value(child.get("type"))
                final_name = child_name
                child_id = str(child.get("channelId") or "")
                if child_action == "create":
                    valid = bool(final_name.strip() and child.get("type"))
                else:
                    valid = child_action in ACTIONS and bool(child_id)
                ops.append({
                    "source": f"categories[{index}].channels[{child_index}]",
                    "action": child_action, "label": ACTIONS.get(child_action, "Error"),
                    "kind": "Canal", "name": final_name or child_id or "—",
                    "indent": "    ",
                    "detail": f"{child.get('type') or '—'} · {child_id or 'nuevo'}",
                    "valid": bool(valid), "error": "" if valid else "Canal no válido.",
                    "type": child_type, "parent_id": category_id,
                    "channel_id": child_id, "raw": child,
                    "status": "Listo" if valid else "Error"})
        for index, child in enumerate(uncategorized):
            if not isinstance(child, dict):
                continue
            action = str(child.get("action") or ("view" if snapshot else "create"))
            name = str(child.get("name") or "")
            type_value = _type_value(child.get("type"))
            final_name = name
            channel_id = str(child.get("channelId") or "")
            if action == "create":
                valid = bool(final_name.strip() and child.get("type"))
            else:
                valid = action in ACTIONS and bool(channel_id)
            ops.append({
                "source": f"uncategorizedChannels[{index}]", "action": action,
                "label": ACTIONS.get(action, "Error"), "kind": "Sin categoría",
                "name": final_name or channel_id or "—", "indent": "",
                "detail": f"{child.get('type') or '—'} · {channel_id or 'nuevo'}",
                "valid": bool(valid), "error": "" if valid else "Canal no válido.",
                "type": type_value, "parent_id": None,
                "channel_id": channel_id, "raw": child,
                "status": "Listo" if valid else "Error"})
        if not ops:
            raise ValueError("El JSON no contiene categorías ni canales.")
        return ops

    def run(self) -> None:
        if self._running or self._snapshot or not self.page.can("MANAGE_CHANNELS"):
            return
        self.preview()
        if self._errors or not self._ops:
            return
        self._running = True
        self._index = 0
        self._created_categories = {}
        self._runtime_channels: dict[str, Any] = {}
        self.text.configure(state="disabled")
        self._update_buttons()
        self.progress.configure(maximum=max(1, len(self._ops)), value=0)
        self._status("Iniciando…", C.YELLOW)
        self.after(30, self._run_next)

    def _run_next(self) -> None:
        if not self._running:
            return
        if self._index >= len(self._ops):
            self._finish()
            return
        op = self._ops[self._index]
        total = len(self._ops)
        self.progress.configure(value=self._index)
        self._status(f"{self._index + 1}/{total} · {op['label']} "
                     f"«{op['name']}»…", C.YELLOW)
        self.after(120, lambda: self._start_op(op))

    def _start_op(self, op: dict) -> None:
        if not self._running:
            return
        self.page.run(lambda: self._execute_op(op),
                      lambda result: self._step_done(op, result),
                      lambda error: self._step_error(op, error))

    def _execute_op(self, op: dict) -> Any:
        client = self.app.client
        guild_id = self.app.guild.id
        fields = self._fields_for(op, self._created_categories)
        if op["action"] == "create":
            created = client.create_channel(guild_id, fields)
            self._runtime_channels[str(created.id)] = created
            if op["kind"] == "Categoría":
                self._created_categories[op["channel_id"]] = created.id
            return created
        if op["action"] == "update":
            updated = client.update_channel(op["channel_id"], fields)
            self._runtime_channels[str(updated.id)] = updated
            return updated
        client.delete_channel(op["channel_id"])
        return None

    def _step_done(self, op: dict, _result: Any) -> None:
        if not self._running:
            return
        self._index += 1
        self.progress.configure(value=self._index)
        self._status(f"{self._index}/{len(self._ops)} · {op['label']} "
                     f"«{op['name']}» completado.", C.GREEN)
        self.after(120, self._run_next)

    def _step_error(self, op: dict, error: BaseException) -> None:
        self._running = False
        self.text.configure(state="normal")
        self._status(f"Error en {op['label']} «{op['name']}»: {error}", C.RED)
        self._update_buttons()

    def _finish(self) -> None:
        self._running = False
        self.text.configure(state="normal")
        self.progress.configure(value=len(self._ops))
        self._status(f"Completado: {len(self._ops)} operaciones.", C.GREEN)
        self._update_buttons()
        self.app.refresh_guild()

    def _execute_all(self) -> int:
        client = self.app.client
        guild_id = self.app.guild.id
        created_categories: dict[str, str] = {}
        for op in self._ops:
            fields = self._fields_for(op, created_categories)
            if op["action"] == "create":
                created = client.create_channel(guild_id, fields)
                if op["kind"] == "Categoría":
                    created_categories[op["channel_id"]] = created.id
            elif op["action"] == "update":
                client.update_channel(op["channel_id"], fields)
            else:
                client.delete_channel(op["channel_id"])
        return len(self._ops)

    def _fields_for(self, op: dict, created_categories: dict[str, str]) -> dict:
        raw = op["raw"]
        fields: dict[str, Any] = {"name": op["name"]}
        if op["action"] == "update" and not raw.get("name"):
            fields.pop("name", None)
        if op["kind"] == "Categoría":
            if op["action"] == "create":
                fields["type"] = 4
            parent = None
        else:
            if op["action"] == "create":
                fields["type"] = op["type"]
            parent = op["parent_id"]
            if parent and str(parent).startswith("__"):
                parent = created_categories.get(str(parent))
            if "parentId" in raw:
                parent = raw.get("parentId")
                if parent and str(parent).startswith("__"):
                    parent = created_categories.get(str(parent))
            if "parentId" in raw and parent is None:
                fields["parent_id"] = None
            elif parent:
                fields["parent_id"] = parent
            settings = raw.get("settings") or {}
            if "topic" in settings:
                fields["topic"] = settings.get("topic") or None
            if settings.get("slowmode", {}).get("enabled"):
                slow = settings.get("slowmode") or {}
                multiplier = {"seconds": 1, "minutes": 60, "hours": 3600}.get(
                    str(slow.get("unit") or "seconds"), 1)
                fields["rate_limit_per_user"] = int(slow.get("value") or 0) * multiplier
            elif "slowmode" in settings:
                fields["rate_limit_per_user"] = 0
            if "visibility" in settings:
                fields["nsfw"] = str(settings.get("visibility")) in (
                    "spoilers", "age_restricted")
            if settings.get("autoArchiveDurationDays"):
                fields["default_auto_archive_duration"] = (
                    int(settings["autoArchiveDurationDays"]) * 1440)
        sync = bool(raw.get("syncWithCategory"))
        existing = self._existing_channel(op)
        if sync and parent:
            category = (self._runtime_channels.get(str(parent))
                        or next((c for c in self.page._channels
                                 if c.id == str(parent)), None))
            if category is not None:
                fields["permission_overwrites"] = [
                    {"id": ow.id, "type": ow.type,
                     "allow": str(ow.allow), "deny": str(ow.deny)}
                    for ow in category.permission_overwrites]
        elif raw.get("permissions") is not None or op["action"] == "update":
            fields["permission_overwrites"] = _overwrites(
                raw.get("permissions") or {}, existing,
                self.app.guild.everyone_role.id if self.app.guild.everyone_role else None)
        return fields

    def _existing_channel(self, op: dict):
        target = op.get("channel_id") or ""
        return (self._runtime_channels.get(str(target))
                or next((c for c in self.page._channels if c.id == str(target)), None))

    def _execution_done(self, count: int) -> None:
        self._running = False
        self.text.configure(state="normal")
        self.progress.configure(value=count)
        self._status(f"Completado: {count} operaciones.", C.GREEN)
        self._update_buttons()
        self.app.refresh_guild()

    def _execution_failed(self, error: BaseException) -> None:
        self._running = False
        self.text.configure(state="normal")
        self._status(f"Error durante la ejecución: {error}", C.RED)
        self._update_buttons()

    def _next(self) -> None:
        if self._index >= len(self._ops):
            self._running = False
            self.text.configure(state="normal")
            self._status("Completado.", C.GREEN)
            self._update_buttons()
            self.app.refresh_guild()
            return
        op = self._ops[self._index]
        client = self.app.client
        guild_id = self.app.guild.id
        self.progress.configure(value=self._index)
        self._status(f"{self._index + 1}/{len(self._ops)} · {op['label']} "
                     f"«{op['name']}»…", C.YELLOW)

        def work() -> None:
            if op["action"] == "create":
                fields = {"name": op["name"], "type": op["type"]}
                parent = op["parent_id"]
                if parent and str(parent).startswith("__"):
                    parent = self._created_categories.get(str(parent))
                if parent:
                    fields["parent_id"] = parent
                created = client.create_channel(guild_id, fields)
                if op["kind"] == "Categoría":
                    self._created_categories[op["channel_id"]] = created.id
            elif op["action"] == "update":
                fields = {"name": op["name"]}
                raw = op["raw"]
                if "parentId" in raw:
                    parent = raw.get("parentId")
                    if parent and str(parent).startswith("__"):
                        parent = self._created_categories.get(str(parent))
                    fields["parent_id"] = parent
                client.update_channel(op["channel_id"], fields)
            else:
                client.delete_channel(op["channel_id"])

        def done(_result: Any) -> None:
            self._index += 1
            self.progress.configure(value=self._index)
            self.after(20, self._next)

        def failed(error: BaseException) -> None:
            self._running = False
            self.text.configure(state="normal")
            self._status(f"Error en «{op['name']}»: {error}", C.RED)
            self._update_buttons()

        self.page.run(work, done, failed)

    def generate(self) -> None:
        categories: list[dict] = []
        uncategorized: list[dict] = []
        rows: list[dict] = []
        category_items = [c for c in self.page._channels if c.is_category]
        uncategorized_items = [c for c in self.page._channels
                               if not c.is_category and not c.parent_id]
        everyone_id = (self.app.guild.everyone_role.id
                       if self.app.guild.everyone_role else None)
        if category_items:
            rows.append({"_id": "__group_categories", "action": "",
                         "kind": "", "name": "CATEGORÍAS", "detail": "",
                         "status": ""})
        for cat_index, channel in enumerate(category_items):
            children = []
            child_rows: list[dict] = []
            for child_index, child in enumerate(self.page._channels):
                if child.parent_id != channel.id or child.is_category:
                    continue
                children.append({
                    "channelId": child.id,
                    "type": _type_name(child.type), "name": child.name,
                    "parentId": channel.id,
                    "syncWithCategory": _same_overwrites(child, channel),
                    "settings": _settings_json(child),
                    "permissions": _permissions_json(child, everyone_id),
                })
                source = f"categories[{cat_index}].channels[{len(children) - 1}]"
                child_rows.append({"_id": child.id, "action": "Ver", "kind": "Canal",
                                   "name": "    " + (child.name or ""),
                                   "detail": child.id, "status": "Instantánea",
                                   "_raw": {"source": source, "kind": "Canal",
                                            "name": child.name, "label": "Ver",
                                            "detail": child.id}})
            categories.append({
                "categoryId": channel.id,
                "name": channel.name,
                "permissions": _permissions_json(channel, everyone_id),
                "channels": children,
            })
            rows.append({"_id": channel.id, "action": "Ver", "kind": "Categoría",
                         "name": channel.name, "detail": channel.id,
                         "status": "Instantánea",
                         "_raw": {"source": f"categories[{cat_index}]",
                                  "kind": "Categoría", "name": channel.name,
                                  "label": "Ver", "detail": channel.id}})
            rows.extend(child_rows)
        for uncat_index, channel in enumerate(uncategorized_items):
            if uncat_index == 0:
                rows.append({"_id": "__group_uncategorized", "action": "",
                             "kind": "", "name": "SIN CATEGORÍA", "detail": "",
                             "status": ""})
            uncategorized.append({
                "channelId": channel.id,
                "type": _type_name(channel.type), "name": channel.name,
                "parentId": None, "syncWithCategory": False,
                "settings": _settings_json(channel),
                "permissions": _permissions_json(channel, everyone_id),
            })
            rows.append({"_id": channel.id, "action": "Ver", "kind": "Sin categoría",
                         "name": channel.name, "detail": channel.id,
                         "status": "Instantánea",
                         "_raw": {"source": f"uncategorizedChannels[{uncat_index}]",
                                  "kind": "Sin categoría", "name": channel.name,
                                  "label": "Ver", "detail": channel.id}})
        data = {
            "guild_id": self.app.guild.id,
            "guild_name": self.app.guild.name,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "read_only": True,
            "snapshot_version": 1,
            "isCommunity": self.app.guild.is_community,
            "categories": categories,
            "uncategorizedChannels": uncategorized,
        }
        self._json_data = data
        self._snapshot = True
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", json.dumps(data, indent=2, ensure_ascii=False))
        self.text.configure(state="disabled")
        self._highlight()
        self.table.set_rows(rows)
        self._status("JSON generado: instantánea no ejecutable.", C.GREEN)
        self._update_buttons()

    def clear(self) -> None:
        self._snapshot = False
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self._ops, self._errors = [], []
        self._json_data = None
        self.table.set_rows([])
        self._status("", C.MUTED)
        self._update_buttons()

    def _selected_operation(self, rows: list[dict]) -> None:
        if self._running or not rows:
            return
        try:
            self.text.tag_remove("op_focus", "1.0", "end")
        except tk.TclError:
            return
        if len(rows) > 1:
            self._status(f"{len(rows)} filas seleccionadas · Supr o clic derecho → "
                         "Eliminar del JSON.", C.DIM)
            return
        operation = rows[0].get("_raw") or {}
        path = operation.get("source") or ""
        if not path:
            return
        block = source_block(self.text.get("1.0", "end-1c"), path)
        if block:
            start, end = block
            self.text.tag_add("op_focus", f"1.0+{start}c", f"1.0+{end}c")
            self.text.see(f"1.0+{start}c")
        label = operation.get("label") or ""
        name = operation.get("name") or ""
        if operation.get("valid"):
            self._status(f"{label} «{name}» · {operation.get('detail', '')}", C.DIM)
        else:
            self._status(f"{label} «{name}» · {operation.get('error', '')}", C.RED)

    def show_errors(self) -> None:
        if not self._errors:
            return
        modal = Modal(
            self, "Errores del JSON de canales", width=780,
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
        self.btn_run.configure(
            state="normal" if (not self._snapshot and not self._running
                               and self._ops and not self._errors) else "disabled")
        self.btn_export.configure(state="normal" if self._snapshot else "disabled")
        self.btn_copy.configure(
            state="normal" if self.text.get("1.0", "end-1c").strip() else "disabled")
        has_errors = bool(self._errors) and not self._snapshot and not self._running
        self.btn_errors.configure(
            text=(f"Ver errores ({len(self._errors)})"
                  if self._errors else "Ver errores"),
            state="normal" if has_errors else "disabled")

    def _status(self, text: str, color: str = C.MUTED) -> None:
        self.status.configure(text=text, fg=color)

    # -- selección múltiple y borrado de filas ------------------------- #
    def _table_press(self, event: tk.Event) -> str | None:
        row_id = self.table.tree.identify_row(event.y)
        if not row_id:
            self._drag_mode = None
            return None
        shift = bool(event.state & 0x0001)
        ctrl = bool(event.state & 0x0004)
        if ctrl:
            self._drag_mode = "ctrl"
            self._drag_start = row_id
            self._drag_toggled = set()
            self._drag_moved = False
            self._toggle_row(row_id)
            return "break"
        if shift:
            self._drag_mode = "shift"
            self._drag_start = row_id
            self._drag_base = set(self.table.tree.selection())
            self._drag_deselect = row_id in self._drag_base
            self._drag_moved = False
            self._apply_shift_range(row_id)
            return "break"
        self._drag_mode = None
        self._table_anchor = row_id
        return None

    def _table_drag_motion(self, event: tk.Event) -> str | None:
        if self._drag_mode is None:
            return None
        row_id = self.table.tree.identify_row(event.y)
        if not row_id:
            return "break"
        if row_id != self._drag_start:
            self._drag_moved = True
        if self._drag_mode == "ctrl":
            if row_id not in self._drag_toggled:
                self._toggle_row(row_id)
        else:
            self._apply_shift_range(row_id)
        self.table.tree.focus(row_id)
        self.table.tree.see(row_id)
        return "break"

    def _table_drag_release(self, _event: tk.Event) -> str | None:
        mode = self._drag_mode
        if mode is None:
            return None
        if mode == "shift" and not self._drag_moved and not self._drag_deselect:
            start = self._drag_start
            if start:
                rows = list(self.table.tree.get_children())
                anchor = self._table_anchor if self._table_anchor in rows else start
                low, high = sorted((rows.index(start), rows.index(anchor)))
                self._set_selection(self._drag_base | set(rows[low:high + 1]))
        if mode == "shift" and self._drag_moved and self._drag_start:
            self._table_anchor = self._drag_start
        self._drag_mode = None
        self._drag_start = None
        return "break"

    def _apply_shift_range(self, current: str) -> None:
        start = self._drag_start
        if not start:
            return
        rows = list(self.table.tree.get_children())
        if start not in rows or current not in rows:
            return
        low, high = sorted((rows.index(start), rows.index(current)))
        block = set(rows[low:high + 1])
        selected = (self._drag_base - block if self._drag_deselect
                    else self._drag_base | block)
        self._set_selection(selected)
        self.table.tree.focus(current)
        self.table.tree.see(current)

    def _toggle_row(self, row_id: str) -> None:
        selected = set(self.table.tree.selection())
        selected.discard(row_id) if row_id in selected else selected.add(row_id)
        self._drag_toggled.add(row_id)
        self._set_selection(selected)
        self.table.tree.focus(row_id)
        self.table.tree.see(row_id)

    def _set_selection(self, selected: set[str]) -> None:
        rows = list(self.table.tree.get_children())
        ordered = [row for row in rows if row in selected]
        if ordered:
            self.table.tree.selection_set(*ordered)
        else:
            current = self.table.tree.selection()
            if current:
                self.table.tree.selection_remove(*current)

    def _extend_selection(self, delta: int) -> str:
        rows = list(self.table.tree.get_children())
        if not rows:
            return "break"
        focus = self.table.tree.focus()
        if focus not in rows:
            focus = self._table_anchor if self._table_anchor in rows else rows[0]
        anchor = self._table_anchor if self._table_anchor in rows else focus
        target = max(0, min(rows.index(focus) + delta, len(rows) - 1))
        low, high = sorted((rows.index(anchor), target))
        self._set_selection(set(rows[low:high + 1]))
        self.table.tree.focus(rows[target])
        self.table.tree.see(rows[target])
        return "break"

    def _row_context(self, event: tk.Event) -> None:
        row_id = self.table.tree.identify_row(event.y)
        if not row_id:
            return
        if row_id not in self.table.tree.selection():
            self.table.tree.selection_set(row_id)
        self.table.tree.focus(row_id)
        count = len(self.table.tree.selection())
        self._row_menu.entryconfigure(
            0, label=(f"Eliminar {count} filas del JSON" if count > 1
                      else "Eliminar del JSON"))
        try:
            self._row_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._row_menu.grab_release()
            except tk.TclError:
                pass

    def _delete_selected(self, _event: Any = None) -> str:
        rows = [row for row in self.table.selected_rows() if row.get("_raw")]
        if not rows or not self._json_data:
            return "break"
        snapshot = self._snapshot
        data = self._json_data
        categories = data.get("categories") or []
        uncategorized = data.get("uncategorizedChannels") or []
        remove_categories: set[int] = set()
        remove_children: dict[int, set[int]] = {}
        remove_uncategorized: set[int] = set()
        for row in rows:
            source = str((row.get("_raw") or {}).get("source") or "")
            match = re.match(r"categories\[(\d+)\]\.channels\[(\d+)\]$", source)
            if match:
                remove_children.setdefault(int(match.group(1)), set()).add(
                    int(match.group(2)))
                continue
            match = re.match(r"categories\[(\d+)\]$", source)
            if match:
                remove_categories.add(int(match.group(1)))
                continue
            match = re.match(r"uncategorizedChannels\[(\d+)\]$", source)
            if match:
                remove_uncategorized.add(int(match.group(1)))
        for index, child_indexes in remove_children.items():
            if index in remove_categories or index >= len(categories):
                continue
            children = categories[index].get("channels") or []
            for child_index in sorted(child_indexes, reverse=True):
                if child_index < len(children):
                    del children[child_index]
        for index in sorted(remove_categories, reverse=True):
            if index < len(categories):
                del categories[index]
        for index in sorted(remove_uncategorized, reverse=True):
            if index < len(uncategorized):
                del uncategorized[index]
        self.load_text(json.dumps(data, indent=2, ensure_ascii=False))
        self._status(f"{len(rows)} filas eliminadas del JSON y de la tabla. "
                     + ("La instantánea sigue sin poder cargarse."
                        if snapshot else "No se ha modificado Discord."), C.GREEN)
        return "break"


def _bits(keys: Any) -> int:
    value = 0
    if not isinstance(keys, list):
        return 0
    for key in keys:
        entry = PERMISSION_BY_KEY.get(str(key))
        if entry:
            value |= 1 << entry[1]
    return value


def _permissions_json(channel: Any, everyone_id: str | None) -> dict:
    assign = []
    for overwrite in channel.permission_overwrites:
        allow = [key for key, entry in PERMISSION_BY_KEY.items()
                 if overwrite.allow & (1 << entry[1])]
        deny = [key for key, entry in PERMISSION_BY_KEY.items()
                if overwrite.deny & (1 << entry[1])]
        assign.append({"targetId": overwrite.id,
                       "targetType": "user" if overwrite.type == 1 else "role",
                       "allow": allow, "deny": deny})
    private = bool(everyone_id and any(
        ow.id == everyone_id and ow.deny & (1 << 10)
        for ow in channel.permission_overwrites))
    return {"isPrivate": private, "assign": assign, "unassign": []}


def _same_overwrites(channel: Any, category: Any) -> bool:
    left = {(ow.id, ow.type, ow.allow, ow.deny)
            for ow in channel.permission_overwrites}
    right = {(ow.id, ow.type, ow.allow, ow.deny)
             for ow in category.permission_overwrites}
    return left == right


def _settings_json(channel: Any) -> dict:
    minutes = max(1, int(channel.rate_limit_per_user or 0) // 60) if channel.rate_limit_per_user else 0
    return {
        "topic": channel.topic or "",
        "isAnnouncement": channel.type == 5,
        "slowmode": {"enabled": bool(channel.rate_limit_per_user),
                     "value": minutes, "unit": "minutes"},
        "visibility": "spoilers" if channel.nsfw else "normal",
        "autoArchiveDurationDays": max(
            0, int(channel.default_auto_archive_duration or 1440) // 1440),
    }


def _overwrites(data: dict, channel: Any, everyone_id: str | None) -> list[dict]:
    values: dict[str, dict] = {}
    if channel is not None:
        values = {ow.id: {"id": ow.id, "type": ow.type,
                          "allow": str(ow.allow), "deny": str(ow.deny)}
                  for ow in channel.permission_overwrites}
    for target in data.get("unassign") or []:
        values.pop(str(target), None)
    for entry in data.get("assign") or []:
        if not isinstance(entry, dict):
            continue
        target_id = str(entry.get("targetId") or "")
        if not target_id:
            continue
        values[target_id] = {
            "id": target_id,
            "type": 1 if str(entry.get("targetType") or "role") == "user" else 0,
            "allow": str(_bits(entry.get("allow"))),
            "deny": str(_bits(entry.get("deny"))),
        }
    if data.get("isPrivate") and everyone_id:
        current = values.get(everyone_id, {"id": everyone_id, "type": 0,
                                            "allow": "0", "deny": "0"})
        current["deny"] = str(int(current["deny"]) | (1 << 10))
        values[everyone_id] = current
    return list(values.values())



def _type_value(name: Any) -> int:
    return {"text": 0, "voice": 2, "announcement": 5, "stage": 13,
            "forum": 15, "media": 16}.get(str(name).lower(), 0)


def _type_name(value: int) -> str:
    return {0: "text", 2: "voice", 5: "announcement", 13: "stage",
            15: "forum", 16: "media"}.get(value, "text")
