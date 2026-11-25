"""Pestaña de gestión masiva de roles a partir de un JSON editable."""
from __future__ import annotations

import base64
import binascii
import json
import re
import tkinter as tk
import unicodedata
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any

from ...constants import PERMISSIONS
from ...models import Role, permission_names
from ..theme import C
from ..widgets import Modal, Table, TableColumn
from .bulk_json_nav import clean_json_text, load_clipboard_object
from .json_syntax import configure_json_tags, highlight_json

ACTION_LABELS = {
    "create": "Crear",
    "modify": "Modificar",
    "delete": "Eliminar",
    "view": "Ver permisos",
    "assign": "Asignar rol",
    "unassign": "Quitar rol",
}
ALLOWED_KEYS = {"guild_id", "roles", "role_members",
                "create", "modify", "delete", "view", "permissions"}
ROLE_KEYS = {"create", "modify", "delete", "view", "permissions"}
HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


class BulkError(Exception):
    pass


def _norm(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_value.lower())


_PERMISSION_ALIASES: dict[str, int] = {}
_PERMISSION_BITS: dict[str, int] = {}
for _key, _bit, _cat, _label, _desc in PERMISSIONS:
    _PERMISSION_ALIASES[_norm(_key)] = _bit
    _PERMISSION_ALIASES[_norm(_label)] = _bit
    _PERMISSION_BITS[_key] = _bit


def _as_bool(value: Any, field: str, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise BulkError(f"«{field}» debe ser true o false.")


def _parse_position(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise BulkError("«position» debe ser un número entero mayor que 0.")
    if value < 1:
        raise BulkError("«position» debe ser mayor que 0.")
    return value


def _parse_icon(value: Any, premium_tier: int) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise BulkError("«icon» debe ser un objeto con image_base64 o unicode_emoji.")
    unknown = set(value) - {"image_base64", "unicode_emoji"}
    if unknown:
        raise BulkError(f"Clave no reconocida en icon: «{sorted(unknown)[0]}».")
    image = value.get("image_base64")
    emoji = value.get("unicode_emoji")
    if image not in (None, "") and emoji not in (None, ""):
        raise BulkError("Usa image_base64 o unicode_emoji, no ambos a la vez.")
    if image in (None, "") and emoji in (None, ""):
        return {"icon": None, "unicode_emoji": None}
    if premium_tier < 2:
        raise BulkError("El icono de rol requiere que el servidor tenga Nivel 2 de mejoras.")
    fields: dict[str, Any] = {"icon": None, "unicode_emoji": None}
    if image not in (None, ""):
        text = str(image)
        header, _sep, data = text.partition(",")
        if not header.startswith("data:image/"):
            raise BulkError("image_base64 debe ser un data URI data:image/...")
        try:
            raw = base64.b64decode(data, validate=True)
        except (ValueError, binascii.Error):
            raise BulkError("image_base64 no contiene base64 válido.") from None
        if len(raw) > 256 * 1024:
            raise BulkError("El icono supera 256 KB.")
        fields["icon"] = text
    if emoji not in (None, ""):
        text = str(emoji).strip()
        if not text:
            raise BulkError("unicode_emoji no puede quedar vacío.")
        fields["unicode_emoji"] = text
    return fields


def _parse_members(value: Any) -> tuple[list[str], list[str]]:
    if value is None:
        return [], []
    if not isinstance(value, dict):
        raise BulkError("«members» debe ser un objeto con add y remove.")
    unknown = set(value) - {"add", "remove"}
    if unknown:
        raise BulkError(f"Clave no reconocida en members: «{sorted(unknown)[0]}».")
    add = _user_id_list(value.get("add"), "members.add")
    remove = _user_id_list(value.get("remove"), "members.remove")
    conflict = set(add) & set(remove)
    if conflict:
        raise BulkError(f"El usuario {sorted(conflict)[0]} está en add y remove.")
    return add, remove


def _parse_links(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise BulkError("«links» debe ser un objeto.")
    unknown = set(value) - {"is_linked_role", "requirements"}
    if unknown:
        raise BulkError(f"Clave no reconocida en links: «{sorted(unknown)[0]}».")
    linked = _as_bool(value.get("is_linked_role"), "is_linked_role")
    requirements = value.get("requirements") or []
    if not isinstance(requirements, list):
        raise BulkError("links.requirements debe ser una lista.")
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            raise BulkError(f"links.requirements[{index}] debe ser un objeto.")
        missing = [key for key in ("connection_type", "application_id", "metadata_key",
                                   "operator", "value") if key not in requirement]
        if missing:
            raise BulkError(
                f"links.requirements[{index}] necesita «{missing[0]}».")
    if not linked and not requirements:
        return {}
    return {"is_linked_role": linked, "requirements": requirements}


def _parse_color(value: Any, *, default: int | None = None) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool):
        raise BulkError("«color» debe ser un color hex o un número.")
    if isinstance(value, int):
        if 0 <= value <= 0xFFFFFF:
            return value
        raise BulkError("«color» está fuera del rango 0..0xFFFFFF.")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return 0
        match = HEX_RE.match(text)
        if match:
            return int(match.group(1), 16)
        raise BulkError(f"Color no válido: «{value}». Usa #RRGGBB.")
    raise BulkError("«color» debe ser un color hex o un número.")


def _parse_permissions(value: Any, *, default: int | None) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool):
        raise BulkError("«permissions» no puede ser un booleano.")
    if isinstance(value, int):
        if value < 0:
            raise BulkError("«permissions» no puede ser negativo.")
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return 0
        if text.isdigit():
            return int(text)
        names = [part.strip() for part in text.split(",") if part.strip()]
        bits = 0
        for name in names:
            key = _norm(name)
            if key not in _PERMISSION_ALIASES:
                raise BulkError(f"Permiso desconocido: «{name}».")
            bits |= 1 << _PERMISSION_ALIASES[key]
        return bits
    if isinstance(value, list):
        bits = 0
        for item in value:
            if isinstance(item, int) and not isinstance(item, bool):
                bits |= item
                continue
            name = str(item).strip()
            if not name:
                continue
            key = _norm(name)
            if key not in _PERMISSION_ALIASES:
                raise BulkError(f"Permiso desconocido: «{name}».")
            bits |= 1 << _PERMISSION_ALIASES[key]
        return bits
    if isinstance(value, dict):
        bits = 0
        for name, enabled in value.items():
            key = _norm(str(name))
            if key not in _PERMISSION_ALIASES:
                raise BulkError(f"Permiso desconocido: «{name}».")
            if enabled:
                bits |= 1 << _PERMISSION_ALIASES[key]
        return bits
    raise BulkError("«permissions» debe ser una lista de nombres o un número.")


def _parse_permission_patch(value: Any, base: int) -> int:
    """Acepta lista/número (reemplazo) u objeto grant/revoke (relativo)."""
    if isinstance(value, dict) and ("grant" in value or "revoke" in value):
        unknown = set(value) - {"grant", "revoke"}
        if unknown:
            raise BulkError(f"Clave no reconocida en permissions: «{sorted(unknown)[0]}».")
        grant = _parse_permissions(value.get("grant"), default=0) or 0
        revoke = _parse_permissions(value.get("revoke"), default=0) or 0
        overlap = grant & revoke
        if overlap:
            names = permission_names(overlap)
            raise BulkError(
                f"Un permiso no puede estar en grant y revoke: {names[0] if names else overlap}.")
        return (base | grant) & ~revoke
    parsed = _parse_permissions(value, default=base)
    return int(parsed if parsed is not None else base)


def _permission_text(bits: int | None) -> str:
    if bits is None:
        return "—"
    names = permission_names(bits)
    if not names:
        return "Ninguno"
    if len(names) > 8:
        return ", ".join(names[:8]) + f" (+{len(names) - 8})"
    return ", ".join(names)


def _permission_text_from_keys(keys: list[str]) -> str:
    bits = 0
    for key in keys:
        bit = _PERMISSION_BITS.get(key)
        if bit is not None:
            bits |= 1 << bit
    return _permission_text(bits)


def _color_text(color: int | None) -> str:
    return "Sin color" if not color else f"#{color:06X}"


def _extras_text(operation: dict) -> str:
    parts: list[str] = []
    if operation.get("icon_fields"):
        parts.append("icono")
    add = len(operation.get("member_add") or [])
    remove = len(operation.get("member_remove") or [])
    if add or remove:
        parts.append(f"miembros +{add}/-{remove}")
    if operation.get("links"):
        parts.append("enlaces manual")
    return " · ".join(parts) or "—"


def _status_text(operation: dict) -> str:
    if operation.get("links"):
        return "Listo · enlaces manuales en Discord"
    return "Listo"


def _base_op(action: str, **kwargs: Any) -> dict[str, Any]:
    op = {
        "action": action,
        "action_label": ACTION_LABELS[action],
        "valid": True,
        "error": "",
        "target": "—",
        "name": "",
        "color": None,
        "hoist": None,
        "mentionable": None,
        "permissions": None,
        "position": None,
        "icon_fields": {},
        "member_add": [],
        "member_remove": [],
        "links": {},
        "reason": "",
        "fields": {},
        "role": None,
        "role_id": None,
        "user_id": "",
    }
    op.update(kwargs)
    return op


def _invalid(action: str, item: dict, error: str) -> dict:
    base_action = "view" if action == "permissions" else action
    target = (item.get("target_name") or item.get("id") or item.get("role_id") or "—")
    name = item.get("name") or ""
    return _base_op(base_action, valid=False, error=error, target=str(target),
                    name=str(name))


def _resolve(item: dict, roles: list[Role]) -> Role:
    role_id = item.get("id")
    if role_id not in (None, ""):
        role = next((r for r in roles if r.id == str(role_id)), None)
        if role is None:
            raise BulkError(f"No existe un rol con ID «{role_id}».")
        return role
    target_name = item.get("target_name")
    if target_name in (None, ""):
        raise BulkError("Indica «id» o «target_name» del rol.")
    name = str(target_name).casefold()
    matches = [r for r in roles if r.name.casefold() == name]
    if not matches:
        raise BulkError(f"No existe un rol llamado «{target_name}».")
    if len(matches) > 1:
        raise BulkError(f"Hay varios roles llamados «{target_name}»; usa el ID.")
    return matches[0]


def parse_bulk(data: Any, roles: list[Role], guild_id: str,
               premium_tier: int = 0) -> list[dict]:
    if not isinstance(data, dict):
        raise BulkError("El JSON debe ser un objeto con «roles» y «role_members».")
    if data.get("read_only") or data.get("snapshot_version"):
        raise BulkError(
            "Este JSON es una instantánea de solo lectura generada por «Generar JSON»; "
            "no se puede cargar. Usa Limpiar para volver al modo de gestión.")
    unknown = set(data) - ALLOWED_KEYS
    if unknown:
        raise BulkError(f"Clave no reconocida: «{sorted(unknown)[0]}».")
    json_guild = data.get("guild_id")
    if json_guild not in (None, "") and str(json_guild) != str(guild_id):
        raise BulkError(
            f"El JSON pertenece al servidor {json_guild}, pero el servidor abierto es "
            f"{guild_id}.")

    operations: list[dict] = []
    role_section = data.get("roles")
    if role_section is not None:
        if not isinstance(role_section, dict):
            raise BulkError("«roles» debe ser un objeto con create/modify/delete.")
        unknown_roles = set(role_section) - ROLE_KEYS
        if unknown_roles:
            raise BulkError(f"Clave no reconocida en roles: «{sorted(unknown_roles)[0]}».")
        if any(key in data for key in ROLE_KEYS):
            raise BulkError("Usa «roles» o las listas en la raíz, no ambas formas.")
        operations.extend(_parse_role_actions(role_section, roles, premium_tier, "roles"))
    else:
        operations.extend(_parse_role_actions(data, roles, premium_tier, ""))

    member_items = data.get("role_members")
    if member_items is not None:
        if not isinstance(member_items, list):
            raise BulkError("«role_members» debe ser una lista.")
        operations.extend(_parse_role_members(member_items, roles))

    if not operations:
        raise BulkError("El JSON no contiene operaciones de roles ni de miembros.")
    return operations


def _parse_role_actions(section: dict, roles: list[Role],
                        premium_tier: int = 0, prefix: str = "roles") -> list[dict]:
    operations: list[dict] = []
    for action in ("create", "modify", "delete", "view", "permissions"):
        items = section.get(action)
        if items is None:
            continue
        if not isinstance(items, list):
            raise BulkError(f"«{action}» debe ser una lista.")
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise BulkError(f"Cada elemento de «{action}» debe ser un objeto.")
            source = f"{prefix}.{action}[{index}]" if prefix else f"{action}[{index}]"
            try:
                operation = _parse_item(action, item, roles, premium_tier)
            except BulkError as error:
                operation = _invalid(action, item, str(error))
            operation["source"] = source
            operations.append(operation)
    return operations


def _parse_role_members(items: list, roles: list[Role]) -> list[dict]:
    operations: list[dict] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise BulkError("Cada elemento de «role_members» debe ser un objeto.")
        source = f"role_members[{index}]"
        reason = str(item.get("reason") or "")
        try:
            ref = dict(item)
            if "id" not in ref and "role_id" in ref:
                ref["id"] = ref["role_id"]
            role = _resolve(ref, roles)
            if role.is_everyone:
                raise BulkError("No se puede asignar ni quitar @everyone.")
            if role.managed:
                raise BulkError("No se puede asignar un rol gestionado por una app.")
            add_users = _user_id_list(item.get("add_users"), "add_users")
            remove_users = _user_id_list(item.get("remove_users"), "remove_users")
            conflict = set(add_users) & set(remove_users)
            if conflict:
                raise BulkError(
                    f"El usuario {sorted(conflict)[0]} aparece en add_users y remove_users.")
            if not add_users and not remove_users:
                raise BulkError("Indica «add_users» o «remove_users».")
        except BulkError as error:
            operation = _invalid("assign", item, str(error))
            operation["source"] = source
            operations.append(operation)
            continue
        for user_id in add_users:
            operation = _base_op(
                "assign", target=role.name, name=user_id, color=role.color,
                hoist=role.hoist, mentionable=role.mentionable,
                permissions=role.permissions, position=role.position,
                role=role, role_id=role.id, user_id=user_id, reason=reason)
            operation["source"] = source
            operations.append(operation)
        for user_id in remove_users:
            operation = _base_op(
                "unassign", target=role.name, name=user_id, color=role.color,
                hoist=role.hoist, mentionable=role.mentionable,
                permissions=role.permissions, position=role.position,
                role=role, role_id=role.id, user_id=user_id, reason=reason)
            operation["source"] = source
            operations.append(operation)
    return operations


def _user_id_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise BulkError(f"«{field}» debe ser una lista de IDs.")
    users: list[str] = []
    for entry in value:
        user_id = str(entry or "").strip()
        if not user_id:
            raise BulkError(f"«{field}» contiene un ID vacío.")
        if user_id not in users:
            users.append(user_id)
    return users


def _parse_item(action: str, item: dict, roles: list[Role],
                premium_tier: int = 0) -> dict:
    if action == "create":
        name = str(item.get("name") or "").strip()
        if not name:
            raise BulkError("Cada rol de «create» necesita «name».")
        color = _parse_color(item.get("color"), default=0) or 0
        hoist = _as_bool(item.get("hoist"), "hoist")
        mentionable = _as_bool(item.get("mentionable"), "mentionable")
        bits = _parse_permission_patch(item.get("permissions"), 0)
        position = _parse_position(item.get("position"))
        icon_fields = _parse_icon(item.get("icon"), premium_tier)
        member_add, member_remove = _parse_members(item.get("members"))
        links = _parse_links(item.get("links"))
        fields: dict[str, Any] = {
            "name": name,
            "color": color,
            "hoist": hoist,
            "mentionable": mentionable,
            "permissions": str(bits),
        }
        fields.update(icon_fields)
        return _base_op("create", target="—", name=name, color=color, hoist=hoist,
                        mentionable=mentionable, permissions=bits, position=position,
                        icon_fields=icon_fields, member_add=member_add,
                        member_remove=member_remove, links=links, fields=fields,
                        reason=str(item.get("reason") or ""))

    role = _resolve(item, roles)
    if action in ("view", "permissions"):
        return _base_op("view", target=role.name, name=role.name, color=role.color,
                        hoist=role.hoist, mentionable=role.mentionable,
                        permissions=role.permissions, position=role.position,
                        role=role, role_id=role.id, reason="")

    if action == "delete":
        if role.is_everyone:
            raise BulkError("No se puede eliminar el rol @everyone.")
        if role.managed:
            raise BulkError("No se puede eliminar un rol gestionado por una app.")
        return _base_op("delete", target=role.name, name=role.name, color=role.color,
                        hoist=role.hoist, mentionable=role.mentionable,
                        permissions=role.permissions, position=role.position,
                        role=role, role_id=role.id,
                        reason=str(item.get("reason") or ""))

    # modify
    if role.is_everyone and "name" in item:
        raise BulkError("El rol @everyone no puede cambiar de nombre.")
    if role.managed:
        raise BulkError("No se puede modificar un rol gestionado por una app.")
    fields: dict[str, Any] = {}
    name = role.name
    if "name" in item:
        name = str(item["name"] or "").strip()
        if not name:
            raise BulkError("«name» no puede quedar vacío.")
        fields["name"] = name
    color = role.color
    if "color" in item:
        parsed = _parse_color(item["color"], default=0)
        color = int(parsed or 0)
        fields["color"] = color
    hoist = role.hoist
    if "hoist" in item:
        hoist = _as_bool(item["hoist"], "hoist")
        fields["hoist"] = hoist
    mentionable = role.mentionable
    if "mentionable" in item:
        mentionable = _as_bool(item["mentionable"], "mentionable")
        fields["mentionable"] = mentionable
    bits = role.permissions
    if "permissions" in item:
        bits = _parse_permission_patch(item["permissions"], role.permissions)
        fields["permissions"] = str(bits)
    position = _parse_position(item.get("position"))
    icon_fields = _parse_icon(item.get("icon"), premium_tier)
    fields.update(icon_fields)
    member_add, member_remove = _parse_members(item.get("members"))
    links = _parse_links(item.get("links"))
    if not fields and position is None:
        if links:
            raise BulkError(
                "Los requisitos de un rol vinculado se configuran manualmente en Discord; "
                "la API no permite aplicarlos.")
        raise BulkError("La modificación no incluye ningún campo.")
    return _base_op("modify", target=role.name, name=name, color=color, hoist=hoist,
                    mentionable=mentionable, permissions=bits, position=position,
                    icon_fields=icon_fields, member_add=member_add,
                    member_remove=member_remove, links=links, fields=fields, role=role,
                    role_id=role.id, reason=str(item.get("reason") or ""))


class BulkRolesTab(tk.Frame):
    """Editor JSON, previsualización y ejecución secuencial de roles."""

    def __init__(self, parent: tk.Misc, app: Any, page: Any):
        super().__init__(parent, bg=C.CONTENT)
        self.app = app
        self.page = page
        self._roles: list[Role] = []
        self._ops: list[dict] = []
        self._running = False
        self._generating = False
        self._index = 0
        self._snapshot_mode = False
        self._snapshot_data: dict[str, Any] | None = None
        self._text_has_json = False
        self._errors: list[dict[str, Any]] = []
        self._json_data: Any = None
        self._preview_after: str | None = None
        self._drag_mode: str | None = None
        self._drag_start: str | None = None
        self._drag_base: set[str] = set()
        self._drag_toggled: set[str] = set()
        self._drag_deselect = False
        self._drag_moved = False
        self._build()

    # ------------------------------------------------------------------ #
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
        self.btn_copy_guild = ttk.Button(toolbar, text="Copiar ID del servidor",
                                         style="Small.TButton", command=self.copy_guild_id)
        self.btn_copy_guild.pack(side="left", padx=(6, 0))
        self.btn_generate = ttk.Button(toolbar, text="Generar JSON",
                                       style="Small.TButton",
                                       command=self.generate_snapshot)
        self.btn_generate.pack(side="left", padx=(6, 0))
        self.btn_copy_json = ttk.Button(toolbar, text="Copiar JSON",
                                        style="Small.TButton",
                                        command=self.copy_json, state="disabled")
        self.btn_copy_json.pack(side="left", padx=(6, 0))
        self.btn_export = ttk.Button(toolbar, text="Exportar JSON…",
                                     style="Small.TButton",
                                     command=self.export_snapshot, state="disabled")
        self.btn_export.pack(side="left", padx=(6, 0))
        self.manage_label = tk.Label(
            toolbar, text="", bg=C.CONTENT, fg=C.MUTED, font=app.theme.font(8))
        self.manage_label.pack(side="right")
        self._update_manage_label()

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
        self._configure_tags()
        self.text.bind("<<Modified>>", self._on_modified)

        columns = [
            TableColumn("action", "Acción", 90),
            TableColumn("target", "Rol actual", 135),
            TableColumn("name", "Nombre final", 145),
            TableColumn("position", "Pos.", 50),
            TableColumn("color", "Color", 70),
            TableColumn("hoist", "Separado", 70),
            TableColumn("mentionable", "Mencionable", 90),
            TableColumn("permissions", "Permisos", 200, stretch=True),
            TableColumn("extras", "Extras", 150),
            TableColumn("status", "Estado", 170, stretch=True),
        ]
        self.table = Table(outer, columns, height=7, theme=app.theme, multi=True,
                           empty_text="Carga un JSON o pégalo arriba para previsualizar.",
                           on_select=self._selected_operation, hscroll=True)
        self.table.grid(row=2, column=0, sticky="nsew")
        self._table_anchor: str | None = None
        self.table.tree.unbind("<Button-3>")
        self.table.tree.bind("<Button-3>", self._row_context)
        self.table.tree.bind("<ButtonPress-1>", self._table_button_press)
        self.table.tree.bind("<B1-Motion>", self._table_drag_motion, add="+")
        self.table.tree.bind("<ButtonRelease-1>", self._table_drag_release, add="+")
        self.table.tree.bind("<Shift-Up>", lambda _e: self._shift_arrow(-1))
        self.table.tree.bind("<Shift-Down>", lambda _e: self._shift_arrow(1))
        self.table.tree.bind("<Shift-Prior>", lambda _e: self._shift_page(-1))
        self.table.tree.bind("<Shift-Next>", lambda _e: self._shift_page(1))
        self.table.tree.bind("<Delete>", self._delete_selected_json)
        self._row_menu = tk.Menu(self, tearoff=0, bg=C.CARD, fg=C.TEXT,
                                 activebackground=C.ACCENT_SOFT,
                                 activeforeground=C.TEXT)
        self._row_menu.add_command(label="Eliminar rol del JSON",
                                   command=self._delete_selected_json)

        buttons = tk.Frame(outer, bg=C.CONTENT)
        buttons.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.btn_clear = ttk.Button(buttons, text="Limpiar", style="Ghost.TButton",
                                    command=self.clear)
        self.btn_clear.pack(side="left")
        self.btn_errors = ttk.Button(buttons, text="Ver errores",
                                     style="SmallDanger.TButton",
                                     command=self.show_errors, state="disabled")
        self.btn_errors.pack(side="left", padx=(8, 0))
        self.btn_run = ttk.Button(buttons, text="Cargar", style="Accent.TButton",
                                  command=self.run_bulk)
        self.btn_run.pack(side="right")
        tk.Label(buttons, text="«Cargar» ejecuta las operaciones del JSON.",
                 bg=C.CONTENT, fg=C.FAINT, font=app.theme.font(8)).pack(
            side="right", padx=(0, 10))

        self.progress = ttk.Progressbar(outer, mode="determinate",
                                        style="Horizontal.TProgressbar")
        self.progress.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self.status_label = tk.Label(outer, text="", bg=C.CONTENT, fg=C.MUTED,
                                     font=app.theme.font(8), anchor="w",
                                     justify="left", wraplength=1000)
        self.status_label.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        self._update_buttons()

    def _configure_tags(self) -> None:
        configure_json_tags(self.text, self.app.theme)

    def _update_manage_label(self) -> None:
        if self._snapshot_mode:
            self.manage_label.configure(
                text="Instantánea no ejecutable · puedes quitar filas o exportar",
                fg=C.YELLOW)
        elif self.page.can("MANAGE_ROLES"):
            self.manage_label.configure(text="", fg=C.MUTED)
        else:
            self.manage_label.configure(text="Solo lectura: falta «Gestionar roles».",
                                        fg=C.YELLOW)

    def set_roles(self, roles: list[Role]) -> None:
        self._roles = list(roles)
        self._update_manage_label()

    def on_show(self) -> None:
        self._update_manage_label()
        if (not self._running and not self._snapshot_mode
                and self.text.get("1.0", "end-1c").strip()):
            self.preview()

    # ------------------------------------------------------------------ #
    def load_file(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="Cargar JSON de roles",
            filetypes=[("JSON", "*.json"), ("Todos los archivos", "*.*")])
        if not path:
            return
        try:
            raw = Path(path).read_text("utf-8-sig")
        except (OSError, UnicodeError) as error:
            self._set_status(f"No se pudo leer el archivo: {error}", C.RED)
            return
        self.load_text(raw, format_json=True)

    def paste_json(self) -> None:
        if self._running or self._generating:
            return
        try:
            raw = self.clipboard_get()
        except tk.TclError:
            try:
                raw = self.clipboard_get(type="STRING")
            except tk.TclError:
                self._set_status("El portapapeles está vacío o no es accesible.", C.RED)
                return
        if not raw:
            self._set_status("El portapapeles está vacío.", C.RED)
            return
        try:
            load_clipboard_object(raw)
        except ValueError as error:
            self._set_status(f"{error} No se pegó nada.", C.RED)
            self.page.toast_warn("El portapapeles no contiene un objeto JSON válido.")
            return
        self.load_text(clean_json_text(raw), format_json=True)
        self._set_status("JSON pegado desde el portapapeles.", C.GREEN)
        self.page.toast_ok("JSON pegado.")

    def copy_json(self) -> None:
        if self._running or self._generating:
            return
        if not self._snapshot_mode and not self._text_has_json:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(self.text.get("1.0", "end-1c"))
            self.update_idletasks()
        except tk.TclError:
            return
        self._set_status("JSON copiado al portapapeles.", C.GREEN)
        self.page.toast_ok("JSON copiado.")

    def load_text(self, raw: str, *, format_json: bool = True) -> None:
        self._snapshot_mode = False
        self._snapshot_data = None
        self.text.configure(state="normal")
        data = None
        if format_json:
            try:
                data = json.loads(raw)
                raw = json.dumps(data, indent=2, ensure_ascii=False)
            except json.JSONDecodeError as error:
                self._set_status(
                    f"JSON inválido: {error.msg} (línea {error.lineno}, "
                    f"columna {error.colno}).", C.RED)
        self._set_text(raw)
        self._set_table_hint("Carga un JSON o pégalo arriba para previsualizar.")
        self._update_manage_label()
        self.preview()

    def _set_text(self, raw: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", raw)
        self.text.edit_modified(False)
        self._highlight()

    def _on_modified(self, _event: Any = None) -> None:
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        self._highlight()
        self._text_has_json = False
        self._update_buttons()
        if self._preview_after is not None:
            try:
                self.after_cancel(self._preview_after)
            except tk.TclError:
                pass
        self._preview_after = self.after(400, self.preview)

    def _highlight(self) -> None:
        highlight_json(self.text)

    def format_document(self) -> None:
        raw = self.text.get("1.0", "end-1c")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as error:
            self._set_status(
                f"JSON inválido: {error.msg} (línea {error.lineno}, "
                f"columna {error.colno}).", C.RED)
            return
        pretty = json.dumps(data, indent=2, ensure_ascii=False)
        self._set_text(pretty)
        self.preview()

    def copy_guild_id(self) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(self.app.guild.id)
            self.update_idletasks()
            self._set_status("ID del servidor copiado.", C.GREEN)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ #
    # Instantánea de solo lectura
    # ------------------------------------------------------------------ #
    def generate_snapshot(self) -> None:
        if self._running or self._generating:
            return
        if self.app.client is None or self.app.guild is None:
            return
        self._generating = True
        self._update_buttons()
        self._set_status("Generando JSON de roles y miembros…", C.YELLOW)
        guild_id = self.app.guild.id

        def done(members: list[Any]) -> None:
            self._generating = False
            snapshot = self._snapshot_payload(members)
            self._snapshot_data = snapshot
            self._snapshot_mode = True
            self._json_data = snapshot
            pretty = json.dumps(snapshot, indent=2, ensure_ascii=False)
            self._set_text(pretty)
            self.text.configure(state="disabled")
            self._text_has_json = True
            self._errors = []
            self.table.set_rows(self._snapshot_table_rows(snapshot))
            self._set_table_hint(
                "Instantánea no ejecutable · puedes quitar filas y exportar.")
            self.progress.configure(maximum=1, value=0)
            total_members = len(members)
            self._set_status(
                f"JSON generado: {len(snapshot['roles'])} roles · "
                f"{total_members} miembros · instantánea no ejecutable. "
                "Puedes quitar filas, copiarlo o exportarlo.", C.GREEN)
            self._update_buttons()

        def failed(error: BaseException) -> None:
            self._generating = False
            self._update_buttons()
            if getattr(error, "status", None) == 50001:
                self._set_status(
                    "No se pudo generar el JSON: falta activar Server Members Intent. "
                    "No es un permiso del rol: ve al Portal de Desarrolladores → tu app "
                    "→ Bot → Privileged Gateway Intents → Server Members Intent, guárdalo "
                    "y reinicia la app.", C.RED)
                self.page.toast_warn(
                    "Activa Server Members Intent en el Portal de Desarrolladores.")
            else:
                self._set_status(
                    f"No se pudo generar el JSON: {error}. Revisa Server Members Intent.",
                    C.RED)

        self.page.run(lambda: self.app.client.list_members(guild_id, 1000),
                      done, failed)

    def _snapshot_payload(self, members: list[Any]) -> dict[str, Any]:
        guild = self.app.guild
        roles = [role for role in guild.sorted_roles() if not role.is_everyone]
        everyone = next((role for role in guild.roles if role.is_everyone), None)
        if everyone is not None:
            roles.append(everyone)
        by_role: dict[str, list[str]] = {role.id: [] for role in roles}
        all_members = [member.user.id for member in members]
        for member in members:
            for role_id in member.roles:
                if role_id in by_role:
                    by_role[role_id].append(member.user.id)
        rows: list[dict[str, Any]] = []
        for role in roles:
            role_members = (all_members if role.is_everyone
                            else by_role.get(role.id, []))
            rows.append({
                "id": role.id,
                "name": role.name,
                "position": role.position,
                "color": role.color_hex,
                "hoist": role.hoist,
                "mentionable": role.mentionable,
                "managed": role.managed,
                "everyone": role.is_everyone,
                "permissions": [
                    key for key, bit, _cat, _label, _desc in PERMISSIONS
                    if role.permissions & (1 << bit)
                ],
                "icon": {
                    "image_hash": role.icon,
                    "unicode_emoji": role.unicode_emoji,
                },
                "links": {
                    "is_linked_role": None,
                    "requirements": [],
                    "available_via_api": False,
                },
                "members": sorted(set(role_members)),
                "member_count": len(set(role_members)),
            })
        return {
            "guild_id": guild.id,
            "guild_name": guild.name,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "read_only": True,
            "snapshot_version": 1,
            "roles": rows,
        }

    def _snapshot_table_rows(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for role in snapshot["roles"]:
            icon = role.get("icon") or {}
            member_count = int(role.get("member_count", 0) or 0)
            extras = [("1 miembro" if member_count == 1
                       else f"{member_count} miembros")]
            if icon.get("image_hash"):
                extras.append("icono")
            elif icon.get("unicode_emoji"):
                extras.append(icon["unicode_emoji"])
            if role.get("everyone"):
                status = "@everyone"
            elif role.get("managed"):
                status = "Bot"
            elif "ADMINISTRATOR" in role.get("permissions", []):
                status = "Admin"
            else:
                status = "Solo lectura"
            rows.append({
                "_id": str(role["id"]),
                "_raw": role,
                "action": "Rol",
                "target": role["name"],
                "name": role["name"],
                "position": role["position"],
                "color": role["color"],
                "hoist": "Sí" if role["hoist"] else "No",
                "mentionable": "Sí" if role["mentionable"] else "No",
                "permissions": _permission_text_from_keys(role.get("permissions", [])),
                "extras": " · ".join(extras),
                "status": status,
            })
        return rows

    def export_snapshot(self) -> None:
        if not self._snapshot_mode or self._snapshot_data is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Exportar JSON de roles",
            defaultextension=".json",
            initialfile="roles-snapshot.json",
            filetypes=[("JSON", "*.json"), ("Todos los archivos", "*.*")])
        if not path:
            return
        try:
            Path(path).write_text(self.text.get("1.0", "end-1c"), "utf-8")
        except OSError as error:
            self._set_status(f"No se pudo exportar: {error}", C.RED)
            return
        self._set_status(f"JSON exportado a {path}", C.GREEN)
        self.page.toast_ok("JSON de roles exportado.")

    def clear(self) -> None:
        if self._running or self._generating:
            return
        self._snapshot_mode = False
        self._snapshot_data = None
        self._text_has_json = False
        self._errors = []
        self._json_data = None
        self.text.configure(state="normal")
        self._set_text("")
        self._ops = []
        self.table.set_rows([])
        self._set_table_hint("Carga un JSON o pégalo arriba para previsualizar.")
        self.progress.configure(maximum=1, value=0)
        self._set_status("", C.MUTED)
        self._update_manage_label()
        self._update_buttons()

    # ------------------------------------------------------------------ #
    def preview(self) -> None:
        if self._snapshot_mode:
            return
        if self._preview_after is not None:
            try:
                self.after_cancel(self._preview_after)
            except tk.TclError:
                pass
            self._preview_after = None
        if self._running:
            return
        if not self._roles and self.app.guild is not None:
            self.set_roles(self.app.guild.sorted_roles())
        raw = self.text.get("1.0", "end-1c").strip()
        if not raw:
            self._text_has_json = False
            self._json_data = None
            self._ops = []
            self._errors = []
            self.table.set_rows([])
            self.progress.configure(maximum=1, value=0)
            self._set_status("", C.MUTED)
            self._update_buttons()
            return
        try:
            data = json.loads(raw)
            self._text_has_json = True
            self._json_data = data
            operations = parse_bulk(data, self._roles, self.app.guild.id,
                                   self.app.guild.premium_tier)
        except json.JSONDecodeError as error:
            self._text_has_json = False
            self._json_data = None
            self._ops = []
            self._errors = []
            self.table.set_rows([])
            self.progress.configure(maximum=1, value=0)
            self._set_status(
                f"JSON inválido: {error.msg} (línea {error.lineno}, "
                f"columna {error.colno}).", C.RED)
            self._update_buttons()
            return
        except BulkError as error:
            self._json_data = None
            self._ops = []
            self._errors = []
            self.table.set_rows([])
            self.progress.configure(maximum=1, value=0)
            self._set_status(str(error), C.RED)
            self._update_buttons()
            return
        self._ops = operations
        errors = [operation for operation in operations if not operation["valid"]]
        self.progress.configure(maximum=max(1, len(operations)), value=0)
        rows = []
        for index, operation in enumerate(operations):
            rows.append({
                "_id": str(index),
                "_raw": operation,
                "action": operation["action_label"],
                "target": operation["target"],
                "name": operation["name"],
                "position": operation["position"] if operation["position"] is not None else "—",
                "color": _color_text(operation["color"]),
                "hoist": "Sí" if operation["hoist"] else "No",
                "mentionable": "Sí" if operation["mentionable"] else "No",
                "permissions": _permission_text(operation["permissions"]),
                "extras": _extras_text(operation),
                "status": (_status_text(operation) if operation["valid"]
                           else f"Error: {operation['error']}"),
            })
        self.table.set_rows(rows)
        self._errors = errors
        if errors:
            self._set_status(
                f"{len(operations)} operaciones · {len(errors)} con errores. "
                "Pulsa «Ver errores» para ver la ruta y el motivo.", C.RED)
        else:
            self._set_status(f"{len(operations)} operaciones listas.", C.GREEN)
        self._update_buttons()

    def _update_buttons(self) -> None:
        busy = self._running or self._generating
        editable = self.page.can("MANAGE_ROLES") and not busy
        snapshot = self._snapshot_mode
        for button in (self.btn_load, self.btn_format):
            button.configure(state="normal" if not busy and not snapshot else "disabled")
        self.btn_copy_guild.configure(state="disabled" if busy else "normal")
        self.btn_paste.configure(state="disabled" if busy else "normal")
        self.btn_generate.configure(state="disabled" if busy else "normal")
        has_json = self._snapshot_mode or self._text_has_json
        self.btn_copy_json.configure(
            state="normal" if has_json and not busy else "disabled")
        self.btn_export.configure(
            state="normal" if snapshot and not busy else "disabled")
        self.btn_clear.configure(state="disabled" if busy else "normal")
        has_errors = bool(self._errors) and not snapshot
        self.btn_errors.configure(
            text=f"Ver errores ({len(self._errors)})" if self._errors else "Ver errores",
            state="normal" if has_errors and not busy else "disabled")
        can_run = (editable and not snapshot and bool(self._ops)
                   and all(operation["valid"] for operation in self._ops))
        self.btn_run.configure(state="normal" if can_run else "disabled")

    def show_errors(self) -> None:
        if not self._errors:
            return
        modal = Modal(
            self, "Errores del JSON", width=780,
            subtitle=f"{len(self._errors)} operaciones no se pueden ejecutar. "
                     "La ruta indica dónde está el problema en el JSON.",
            theme=self.app.theme)
        text = tk.Text(modal.body, bg=C.INPUT, fg=C.TEXT, relief="flat", bd=0,
                       wrap="word", font=(self.app.theme.mono_family, 9),
                       padx=10, pady=8, height=18)
        text.pack(fill="both", expand=True)
        for number, operation in enumerate(self._errors, 1):
            source = operation.get("source") or "?"
            target = operation.get("target") or operation.get("name") or "—"
            text.insert("end", f"{number}. {source}\n")
            text.insert("end", f"   {operation['action_label']} «{target}»\n")
            text.insert("end", f"   {operation['error']}\n\n")
        text.configure(state="disabled")
        modal.add_button("Cerrar", modal.close)
        modal.show()

    def _selected_operation(self, rows: list[dict]) -> None:
        if self._running or self._generating or not rows:
            return
        if len(rows) > 1:
            try:
                self.text.tag_remove("op_focus", "1.0", "end")
            except tk.TclError:
                pass
            self._set_status(
                f"{len(rows)} operaciones seleccionadas · Supr o clic derecho → "
                "Eliminar del JSON.", C.DIM)
            return
        operation = rows[0].get("_raw") or {}
        if not operation:
            return
        if self._snapshot_mode:
            self._reveal_operation(operation)
            self._set_status(
                f"Rol «{operation.get('name', '')}» · posición "
                f"{operation.get('position', '—')} · "
                f"{operation.get('member_count', 0)} miembros · "
                f"{_permission_text_from_keys(operation.get('permissions', []))}",
                C.DIM)
            return
        self._reveal_operation(operation)
        if operation.get("valid"):
            self._set_status(
                f"{operation['action_label']} «{operation['name']}» · "
                f"{_permission_text(operation['permissions'])}", C.DIM)
        else:
            self._set_status(
                f"{operation['action_label']} «{operation['name']}» · "
                f"{operation['error']}", C.RED)

    def _reveal_operation(self, operation: dict) -> None:
        if self._snapshot_mode:
            needle = operation.get("id")
        else:
            needle = (operation.get("user_id") or operation.get("role_id")
                      or operation.get("name"))
        if not needle:
            return
        text = self.text.get("1.0", "end-1c")
        target = json.dumps(str(needle), ensure_ascii=False)
        position = text.find(target)
        if position < 0:
            return
        start = text.rfind("{", 0, position)
        if start < 0:
            return
        end = self._matching_brace(text, start)
        if end is None:
            return
        self.text.tag_remove("op_focus", "1.0", "end")
        self.text.tag_add("op_focus", f"1.0+{start}c", f"1.0+{end}c")
        self.text.see(f"1.0+{start}c")

    @staticmethod
    def _matching_brace(text: str, start: int) -> int | None:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return index + 1
        return None

    def _table_button_press(self, event: tk.Event) -> str | None:
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
            self._ctrl_toggle(row_id)
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
                self._ctrl_toggle(row_id)
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
                start_index = rows.index(start)
                anchor_index = rows.index(anchor)
                low, high = sorted((start_index, anchor_index))
                selected = self._drag_base | set(rows[low:high + 1])
                self._set_selection(selected)
                self.table.tree.focus(start)
                self.table.tree.see(start)
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
        start_index = rows.index(start)
        current_index = rows.index(current)
        low, high = sorted((start_index, current_index))
        block = set(rows[low:high + 1])
        selected = (self._drag_base - block if self._drag_deselect
                    else self._drag_base | block)
        self._set_selection(selected)
        self.table.tree.focus(current)
        self.table.tree.see(current)

    def _ctrl_toggle(self, row_id: str) -> None:
        selected = set(self.table.tree.selection())
        if row_id in selected:
            selected.discard(row_id)
        else:
            selected.add(row_id)
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

    def _shift_arrow(self, delta: int) -> str:
        return self._extend_selection(delta)

    def _shift_page(self, direction: int) -> str:
        try:
            page = max(1, int(self.table.tree.cget("height")))
        except (TypeError, ValueError, tk.TclError):
            page = 7
        return self._extend_selection(direction * page)

    def _extend_selection(self, delta: int) -> str:
        rows = list(self.table.tree.get_children())
        if not rows:
            return "break"
        focus = self.table.tree.focus()
        if focus not in rows:
            focus = self._table_anchor if self._table_anchor in rows else rows[0]
        anchor = self._table_anchor if self._table_anchor in rows else focus
        index = rows.index(focus)
        target = max(0, min(index + delta, len(rows) - 1))
        start = min(rows.index(anchor), target)
        end = max(rows.index(anchor), target)
        self.table.tree.selection_set(*rows[start:end + 1])
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
        self._table_anchor = row_id
        count = len(self.table.tree.selection())
        self._row_menu.entryconfigure(
            0, label=(f"Eliminar {count} roles del JSON" if count > 1
                      else "Eliminar rol del JSON"))
        try:
            self._row_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._row_menu.grab_release()
            except tk.TclError:
                pass

    def _delete_selected_json(self, _event: Any = None) -> str:
        rows = self.table.selected_rows()
        if not rows:
            return "break"
        if self._snapshot_mode:
            snapshot = self._snapshot_data
            if not snapshot:
                return "break"
            role_ids = {str((row.get("_raw") or {}).get("id")) for row in rows}
            roles = snapshot.get("roles") or []
            remaining = [role for role in roles if str(role.get("id")) not in role_ids]
            removed = len(roles) - len(remaining)
            if not removed:
                self._set_status("No se pudieron localizar los roles en la instantánea.", C.RED)
                return "break"
            snapshot["roles"] = remaining
            pretty = json.dumps(snapshot, indent=2, ensure_ascii=False)
            self.text.configure(state="normal")
            self._set_text(pretty)
            self.text.configure(state="disabled")
            self._json_data = snapshot
            self._text_has_json = True
            self.table.set_rows(self._snapshot_table_rows(snapshot))
            self._table_anchor = None
            self._set_status(
                f"{removed} roles eliminados de la instantánea. No se ha borrado nada en "
                "Discord; puedes exportar el JSON actualizado.", C.GREEN)
            self.page.toast_ok(f"{removed} roles eliminados de la instantánea.")
            self._update_buttons()
            return "break"
        data = self._json_data
        if not data:
            self._set_status("No se pudo localizar el JSON.", C.RED)
            return "break"
        operations = [row.get("_raw") or {} for row in rows]
        removed = self._remove_json_operations(data, operations)
        if not removed:
            self._set_status("No se pudieron localizar las operaciones seleccionadas.", C.RED)
            return "break"
        self.load_text(json.dumps(data, indent=2, ensure_ascii=False),
                       format_json=True)
        self._table_anchor = None
        self._set_status(
            f"{removed} operaciones eliminadas del JSON y de la tabla. No se ha "
            "modificado Discord.", C.GREEN)
        self.page.toast_ok(f"{removed} operaciones eliminadas del JSON.")
        return "break"

    def _remove_json_operations(self, data: dict[str, Any],
                                operations: list[dict]) -> int:
        role_groups: dict[tuple[str | None, str], set[int]] = {}
        member_ops: list[tuple[int, str, str]] = []
        for operation in operations:
            source = operation.get("source") or ""
            if source.startswith("role_members["):
                match = re.match(r"role_members\[(\d+)\]$", source)
                if match:
                    member_ops.append((int(match.group(1)),
                                       str(operation.get("user_id") or ""),
                                       str(operation.get("action") or "")))
                continue
            match = re.match(r"(?:(roles)\.)?([a-z_]+)\[(\d+)\]$", source)
            if not match:
                continue
            scope, action, raw_index = match.groups()
            role_groups.setdefault((scope, action), set()).add(int(raw_index))
        removed = 0
        for (scope, action), indexes in role_groups.items():
            container = data.get("roles") if scope else data
            items = container.get(action) if isinstance(container, dict) else None
            if not isinstance(items, list):
                continue
            for index in sorted(indexes, reverse=True):
                if index < len(items):
                    del items[index]
                    removed += 1
        if member_ops:
            grouped: dict[int, list[tuple[str, str]]] = {}
            for index, user_id, action in member_ops:
                grouped.setdefault(index, []).append((user_id, action))
            items = data.get("role_members")
            if isinstance(items, list):
                for index in sorted(grouped, reverse=True):
                    if index >= len(items):
                        continue
                    item = items[index]
                    for user_id, action in grouped[index]:
                        key = "add_users" if action == "assign" else "remove_users"
                        users = item.get(key) or []
                        if user_id in users:
                            users.remove(user_id)
                            item[key] = users
                            removed += 1
                    if not (item.get("add_users") or item.get("remove_users")):
                        del items[index]
        return removed

    def _set_status(self, text: str, color: str = C.MUTED) -> None:
        self.status_label.configure(text=text, fg=color)

    def _set_table_hint(self, text: str) -> None:
        try:
            self.table._empty.configure(text=text)
        except (AttributeError, tk.TclError):
            pass

    # ------------------------------------------------------------------ #
    def run_bulk(self) -> None:
        if self._running or self._generating or self._snapshot_mode:
            return
        if not self.page.can("MANAGE_ROLES"):
            return
        self.preview()
        if not self._ops or any(not operation["valid"] for operation in self._ops):
            return
        self._running = True
        self._index = 0
        self.text.configure(state="disabled")
        self.progress.configure(maximum=max(1, len(self._ops)), value=0)
        self._update_buttons()
        self._set_status("Iniciando…", C.YELLOW)
        self.after(20, self._run_next)

    def _run_next(self) -> None:
        if not self._running:
            return
        if self._index >= len(self._ops):
            self._finish()
            return
        operation = self._ops[self._index]
        total = len(self._ops)
        self.progress.configure(value=self._index)
        label = operation["name"] or operation["target"]
        self._set_status(
            f"{self._index + 1}/{total} · {operation['action_label']} «{label}»…",
            C.YELLOW)
        if operation["action"] == "view":
            self.after(30, lambda: self._step_done(operation, None))
            return
        if operation["action"] in ("assign", "unassign"):
            work = lambda: self._apply_member(operation)
        else:
            work = lambda: self._apply_role(operation)
        self.page.run(work, lambda result: self._step_done(operation, result),
                      lambda error: self._step_error(operation, error))

    def _apply_role(self, operation: dict) -> Any:
        client = self.app.client
        guild_id = self.app.guild.id
        action = operation["action"]
        if action == "create":
            fields = {key: value for key, value in operation["fields"].items()
                      if key not in ("icon", "unicode_emoji")}
            role = client.create_role(guild_id, fields,
                                      reason=operation["reason"] or None)
            if operation["icon_fields"]:
                role = client.update_role(guild_id, role.id, operation["icon_fields"],
                                          reason=operation["reason"] or None)
        elif action == "modify":
            if operation["fields"]:
                role = client.update_role(guild_id, operation["role_id"],
                                          operation["fields"],
                                          reason=operation["reason"] or None)
            else:
                role = operation["role"]
            if role is None:
                return None
        else:
            client.delete_role(guild_id, operation["role_id"],
                               reason=operation["reason"] or None)
            return None
        if operation["position"] is not None:
            client.reorder_roles(guild_id, [{
                "id": role.id, "position": int(operation["position"]),
            }])
        for user_id in operation["member_add"]:
            self._change_member_role(guild_id, user_id, role.id, True,
                                     operation["reason"] or None)
        for user_id in operation["member_remove"]:
            self._change_member_role(guild_id, user_id, role.id, False,
                                     operation["reason"] or None)
        return role

    def _apply_member(self, operation: dict) -> None:
        self._change_member_role(self.app.guild.id, operation["user_id"],
                                 operation["role_id"],
                                 operation["action"] == "assign",
                                 operation["reason"] or None)

    def _change_member_role(self, guild_id: str, user_id: str, role_id: str,
                            add: bool, reason: str | None) -> None:
        client = self.app.client
        member = client.get_member(guild_id, user_id)
        roles = set(member.roles)
        if add:
            roles.add(role_id)
        else:
            roles.discard(role_id)
        client.update_member(guild_id, user_id, {"roles": sorted(roles)},
                             reason=reason)

    def _step_done(self, operation: dict, _result: Any) -> None:
        if not self._running:
            return
        self._index += 1
        self.progress.configure(value=self._index)
        self._set_status(
            f"{self._index}/{len(self._ops)} · {operation['action_label']} "
            f"«{operation['name'] or operation['target']}» completado"
            + (" (enlaces manuales en Discord)" if operation.get("links") else "") + ".",
            C.GREEN)
        self.after(25, self._run_next)

    def _step_error(self, operation: dict, error: BaseException) -> None:
        self._running = False
        self.text.configure(state="normal")
        self._update_buttons()
        label = operation["name"] or operation["target"]
        if getattr(error, "status", None) == 50013:
            detail = (
                "Discord rechazó la operación (50013). El JSON es válido, pero el bot no "
                "puede dar permisos que él no tiene o su rol está por debajo del rol que "
                "intenta gestionar. Dale «Administrador» al rol del bot, súbelo por encima "
                "de los roles que vas a crear/modificar y vuelve a cargar.")
        else:
            detail = str(error)
        self._set_status(
            f"Error en {operation['action_label']} «{label}»: {detail}", C.RED)
        self.page.toast_warn(f"Error en «{label}»: {detail}")
        self.app.refresh_guild()

    def _finish(self) -> None:
        self._running = False
        self.text.configure(state="normal")
        self.progress.configure(value=len(self._ops))
        self._set_status(f"Completado: {len(self._ops)} operaciones.", C.GREEN)
        self._update_buttons()
        self.page.toast_ok(f"Roles masivos completados ({len(self._ops)} operaciones).")
        self.app.refresh_guild()
