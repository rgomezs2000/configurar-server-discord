"""Moderación automática (automod): reglas de Discord gestionadas manualmente."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from ...constants import (AUTOMOD_ACTION_TYPES, AUTOMOD_KEYWORD_PRESETS,
                          AUTOMOD_TRIGGERS)
from ...models import AutoModRule
from ..theme import C
from ..widgets import (Checkbox, ConfirmDialog, Field, Modal, PageHeader,
                       ScrollFrame, ScrollableModal, Switch, Table, TableColumn,
                       labeled_text)
from .base import Page


class AutomodPage(Page):
    key = "automod"
    label = "Automod"
    glyph = "◈"

    def build(self) -> None:
        app = self.app
        self.header = PageHeader(self, app, "Moderación automática",
                                 "Reglas de Discord que actúan solas ante spam, insultos o "
                                 "menciones masivas. Tú las creas y decides cuándo aplicarlas.")
        self.header.pack(fill="x", padx=28, pady=(22, 0))
        self._manage = app.can("MANAGE_GUILD")
        self.new_button = self.header.button("Nueva regla", self._create, style="Accent.TButton")
        self.header.button("Actualizar", self.refresh)

        toolbar = tk.Frame(self, bg=C.CONTENT)
        toolbar.pack(fill="x", padx=28, pady=(14, 6))
        self.count_label = tk.Label(toolbar, text="", bg=C.CONTENT, fg=C.MUTED,
                                    font=app.theme.font(9))
        self.count_label.pack(side="left")
        self.delete_button = ttk.Button(toolbar, text="Eliminar", style="SmallDanger.TButton",
                                        command=self._delete)
        self.delete_button.pack(side="right")
        self.toggle_button = ttk.Button(toolbar, text="Activar / desactivar",
                                        style="Small.TButton", command=self._toggle)
        self.toggle_button.pack(side="right", padx=(0, 6))
        self.edit_button = ttk.Button(toolbar, text="Editar", style="Small.TButton",
                                      command=self._edit)
        self.edit_button.pack(side="right", padx=(0, 6))
        if not self._manage:
            for button in (self.new_button, self.delete_button, self.toggle_button,
                           self.edit_button):
                button.configure(state="disabled")
            tk.Label(self, text="Solo lectura: falta el permiso «Gestionar servidor».",
                     bg=C.YELLOW_SOFT, fg="#ffd98a", font=app.theme.font(8),
                     anchor="w", padx=10, pady=5).pack(fill="x", padx=28, pady=(0, 8))

        columns = [TableColumn("name", "Nombre", 220, stretch=True),
                   TableColumn("trigger", "Disparador", 200),
                   TableColumn("actions", "Acciones", 260, stretch=True),
                   TableColumn("status", "Estado", 100, anchor="center"),
                   TableColumn("exempt", "Exenciones", 90, anchor="center")]
        self.table = Table(self, columns, height=14, theme=app.theme,
                           on_double=lambda _row: self._edit(), multi=False,
                           empty_text="No hay reglas de automod en este servidor.")
        self.table.pack(fill="both", expand=True, padx=28, pady=(0, 20))
        self._rules: list[AutoModRule] = []

    def refresh(self) -> None:
        client = self.app.client
        guild_id = self.app.guild.id
        self.run(lambda: client.list_automod_rules(guild_id), self._done)

    def _done(self, rules: list[AutoModRule]) -> None:
        self._rules = rules
        rows = [{
            "_id": rule.id,
            "name": rule.name,
            "trigger": rule.trigger_label,
            "actions": rule.actions_label,
            "status": "Activa" if rule.enabled else "Pausada",
            "exempt": str(len(rule.exempt_roles) + len(rule.exempt_channels)) or "—",
            "_tags": ("success",) if rule.enabled else ("muted",),
            "_raw": {"name": rule.name, "status": rule.enabled},
            "_rule": rule,
        } for rule in rules]
        self.table.set_rows(rows)
        self.count_label.configure(text=f"{len(rules)} reglas")

    def _selected(self) -> AutoModRule | None:
        rows = self.table.selected_rows()
        return rows[0].get("_rule") if rows else None

    def _create(self) -> None:
        if not self.require("MANAGE_GUILD", "crear reglas de automod"):
            return
        AutomodRuleModal(self, self.app, None, self.refresh).show()

    def _edit(self) -> None:
        rule = self._selected()
        if rule is None:
            self.toast_warn("Selecciona una regla.")
            return
        if not self.require("MANAGE_GUILD", "editar reglas de automod"):
            return
        AutomodRuleModal(self, self.app, rule, self.refresh).show()

    def _toggle(self) -> None:
        rule = self._selected()
        if rule is None:
            self.toast_warn("Selecciona una regla.")
            return
        if not self.require("MANAGE_GUILD", "cambiar reglas de automod"):
            return
        client = self.app.client
        guild_id = self.app.guild.id
        new_state = not rule.enabled

        def done(_result: Any) -> None:
            self.app.toasts.show("Regla activada." if new_state else "Regla pausada.", "success")
            self.refresh()

        self.run(lambda: client.update_automod_rule(guild_id, rule.id, {"enabled": new_state}),
                 done)

    def _delete(self) -> None:
        rule = self._selected()
        if rule is None:
            self.toast_warn("Selecciona una regla.")
            return
        if not self.require("MANAGE_GUILD", "eliminar reglas de automod"):
            return
        dialog = ConfirmDialog(self, "Eliminar regla",
                               f"Se eliminará la regla «{rule.name}».",
                               confirm_text="Eliminar", danger=True,
                               theme=self.app.theme)
        if not dialog.show():
            return
        client = self.app.client
        guild_id = self.app.guild.id

        def done(_result: Any) -> None:
            self.app.toasts.show("Regla eliminada.", "success")
            self.refresh()

        self.run(lambda: client.delete_automod_rule(guild_id, rule.id), done)


# --------------------------------------------------------------------------- #
# Editor de reglas
# --------------------------------------------------------------------------- #

class AutomodRuleModal(ScrollableModal):
    def __init__(self, parent: tk.Misc, app: Any, rule: AutoModRule | None,
                 on_saved: Any):
        super().__init__(parent,
                         "Editar regla de automod" if rule else "Nueva regla de automod",
                         width=620, theme=app.theme, desired_height=590,
                         subtitle="Las reglas se aplican a los mensajes nuevos.")
        self.app = app
        self.rule = rule
        self.on_saved = on_saved
        body = self.content

        name_field = Field(body, "Nombre de la regla", bg=C.CARD)
        name_field.pack(fill="x", pady=(0, 12))
        self.name_var = tk.StringVar(value=rule.name if rule else "Nueva regla")
        ttk.Entry(name_field.slot, textvariable=self.name_var).pack(fill="x")

        trigger_field = Field(body, "Disparador", "Qué debe ocurrir para activar la regla.",
                              bg=C.CARD)
        trigger_field.pack(fill="x", pady=(0, 12))
        trigger_value = rule.trigger_type if rule else AUTOMOD_TRIGGERS[0][0]
        trigger_label = next((label for value, label, _d in AUTOMOD_TRIGGERS
                              if value == trigger_value), AUTOMOD_TRIGGERS[0][1])
        self.trigger_var = tk.StringVar(value=trigger_label)
        trigger_combo = ttk.Combobox(trigger_field.slot, state="readonly",
                                     values=[label for _v, label, _d in AUTOMOD_TRIGGERS],
                                     textvariable=self.trigger_var)
        trigger_combo.pack(fill="x")
        trigger_combo.bind("<<ComboboxSelected>>", lambda _e: self._sync_fields())
        self.trigger_hint = tk.Label(trigger_field.slot, text="", bg=C.CARD, fg=C.FAINT,
                                     font=app.theme.font(8), anchor="w", justify="left",
                                     wraplength=540)
        self.trigger_hint.pack(fill="x", pady=(4, 0))

        self.dynamic = tk.Frame(body, bg=C.CARD)
        self.dynamic.pack(fill="x")
        self.dynamic.grid_columnconfigure(0, weight=1)

        self.keywords_frame, self.keywords_text = labeled_text(
            self.dynamic, app, "Palabras o frases prohibidas",
            "Una por línea. No distingue mayúsculas.", height=5)
        self.keywords_frame.grid(row=0, column=0, sticky="ew", pady=(12, 12))
        if rule and rule.keywords:
            self.keywords_text.insert("1.0", "\n".join(rule.keywords))

        self.presets_frame = tk.Frame(self.dynamic, bg=C.CARD)
        self.presets_frame.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        tk.Label(self.presets_frame, text="LISTAS PREDEFINIDAS", bg=C.CARD, fg=C.MUTED,
                 font=app.theme.font(8, "bold"), anchor="w").pack(fill="x")
        self.preset_vars: dict[str, tk.BooleanVar] = {}
        for key, label in AUTOMOD_KEYWORD_PRESETS:
            var = tk.BooleanVar(value=bool(rule and key in rule.presets))
            Checkbox(self.presets_frame, label, variable=var, bg=C.CARD,
                     font=app.theme.font(9)).pack(anchor="w", pady=1)
            self.preset_vars[key] = var

        self.mention_frame = tk.Frame(self.dynamic, bg=C.CARD)
        self.mention_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        tk.Label(self.mention_frame, text="LÍMITE DE MENCIONES", bg=C.CARD, fg=C.MUTED,
                 font=app.theme.font(8, "bold"), anchor="w").pack(fill="x")
        row = tk.Frame(self.mention_frame, bg=C.CARD)
        row.pack(fill="x", pady=(4, 0))
        self.mention_var = tk.StringVar(value=str(rule.mention_limit if rule and rule.mention_limit else 5))
        ttk.Spinbox(row, from_=1, to=50, width=6, textvariable=self.mention_var).pack(side="left")
        tk.Label(row, text="menciones en un mismo mensaje", bg=C.CARD, fg=C.MUTED,
                 font=app.theme.font(8)).pack(side="left", padx=(8, 0))

        actions_label = tk.Label(body, text="ACCIONES AL DETECTAR", bg=C.CARD, fg=C.MUTED,
                                 font=app.theme.font(8, "bold"), anchor="w")
        actions_label.pack(fill="x", pady=(10, 0))
        self.block_var = tk.BooleanVar(value=self._has_action(1))
        Checkbox(body, "Bloquear el mensaje", variable=self.block_var, bg=C.CARD,
                 font=app.theme.font(9)).pack(anchor="w", pady=1)
        self.alert_var = tk.BooleanVar(value=self._has_action(2))
        Checkbox(body, "Enviar una alerta a un canal", variable=self.alert_var, bg=C.CARD,
                 font=app.theme.font(9)).pack(anchor="w", pady=1)
        self.alert_channel_var = tk.StringVar()
        self.alert_combo = ttk.Combobox(
            body, values=[f"#{c.display_name}" for c in app.channels if c.is_text],
            state="readonly", textvariable=self.alert_channel_var)
        self.alert_combo.pack(fill="x", pady=(0, 6))
        if rule and self.alert_var.get():
            metadata = next((a.get("metadata") or {} for a in rule.actions
                             if int(a.get("type") or 0) == 2), {})
            channel_id = str(metadata.get("channel_id") or "")
            channel = next((c for c in app.channels if c.id == channel_id), None)
            if channel:
                self.alert_channel_var.set(f"#{channel.display_name}")

        self.timeout_var = tk.BooleanVar(value=self._has_action(3))
        Checkbox(body, "Aislar al autor temporalmente (timeout)", variable=self.timeout_var,
                 bg=C.CARD, font=app.theme.font(9)).pack(anchor="w", pady=1)
        timeout_row = tk.Frame(body, bg=C.CARD)
        timeout_row.pack(fill="x", pady=(0, 6))
        self.timeout_seconds = tk.StringVar(value=str(self._timeout_seconds()))
        ttk.Spinbox(timeout_row, from_=60, to=86400, increment=60, width=8,
                    textvariable=self.timeout_seconds).pack(side="left")
        tk.Label(timeout_row, text="segundos", bg=C.CARD, fg=C.MUTED,
                 font=app.theme.font(8)).pack(side="left", padx=(6, 0))

        enabled_row = tk.Frame(body, bg=C.CARD)
        enabled_row.pack(fill="x", pady=(8, 4))
        tk.Label(enabled_row, text="Regla activa", bg=C.CARD, fg=C.TEXT,
                 font=app.theme.font(9)).pack(side="left")
        self.enabled_var = tk.BooleanVar(value=rule.enabled if rule else True)
        Switch(enabled_row, self.enabled_var, bg=C.CARD).pack(side="right")

        self.add_button("Cancelar", self.close)
        self.add_button("Guardar regla", self._submit, style="Accent.TButton")
        self._sync_fields()

    # -- ayudas ------------------------------------------------------------- #
    def _has_action(self, action_type: int) -> bool:
        if not self.rule:
            return action_type in (1, 2)
        return any(int(action.get("type") or 0) == action_type for action in self.rule.actions)

    def _timeout_seconds(self) -> int:
        if not self.rule:
            return 600
        for action in self.rule.actions:
            if int(action.get("type") or 0) == 3:
                return int((action.get("metadata") or {}).get("duration_seconds") or 600)
        return 600

    def _trigger_value(self) -> int:
        return next((value for value, label, _d in AUTOMOD_TRIGGERS
                     if label == self.trigger_var.get()), 1)

    def _sync_fields(self) -> None:
        trigger = self._trigger_value()
        hint = next((desc for value, _label, desc in AUTOMOD_TRIGGERS if value == trigger), "")
        self.trigger_hint.configure(text=hint)
        if trigger in (1, 6):
            self.keywords_frame.grid()
        else:
            self.keywords_frame.grid_remove()
        if trigger == 4:
            self.presets_frame.grid()
        else:
            self.presets_frame.grid_remove()
        if trigger == 5:
            self.mention_frame.grid()
        else:
            self.mention_frame.grid_remove()

    # -- guardado ----------------------------------------------------------- #
    def _submit(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            self.show_error("Ponle un nombre a la regla.")
            return
        trigger = self._trigger_value()
        metadata: dict[str, Any] = {}
        if trigger in (1, 6):
            keywords = [line.strip() for line in self.keywords_text.get("1.0", "end").splitlines()
                        if line.strip()]
            if not keywords:
                self.show_error("Añade al menos una palabra o frase.")
                return
            metadata["keyword_filter"] = keywords
        if trigger == 4:
            presets = [key for key, var in self.preset_vars.items() if var.get()]
            if not presets:
                self.show_error("Selecciona al menos una lista predefinida.")
                return
            metadata["presets"] = presets
        if trigger == 5:
            metadata["mention_total_limit"] = int(self.mention_var.get() or 5)
        actions: list[dict] = []
        if self.block_var.get():
            actions.append({"type": 1})
        if self.alert_var.get():
            channel = next((c for c in self.app.channels
                            if f"#{c.display_name}" == self.alert_channel_var.get()), None)
            if channel:
                actions.append({"type": 2, "metadata": {"channel_id": channel.id}})
        if self.timeout_var.get():
            actions.append({"type": 3,
                            "metadata": {"duration_seconds": int(self.timeout_seconds.get() or 600)}})
        if trigger == 6:
            actions = [{"type": 4}]
        if not actions:
            self.show_error("Marca al menos una acción.")
            return
        body = {
            "name": name,
            "event_type": 1 if trigger != 6 else 2,
            "trigger_type": trigger,
            "trigger_metadata": metadata,
            "actions": actions,
            "enabled": bool(self.enabled_var.get()),
        }
        client = self.app.client
        guild_id = self.app.guild.id
        self.set_busy(True)
        if self.rule:
            work = lambda: client.update_automod_rule(guild_id, self.rule.id, body)
        else:
            work = lambda: client.create_automod_rule(guild_id, body)

        def done(_result: Any) -> None:
            self.app.toasts.show("Regla guardada.", "success")
            self.close()
            self.on_saved()

        def failed(error: BaseException) -> None:
            self.set_busy(False)
            self.show_error(str(error))

        self.app.run_task(work, done, failed)
