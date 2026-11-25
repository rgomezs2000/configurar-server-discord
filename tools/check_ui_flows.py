"""Pruebas funcionales de la interfaz en modo demostración (herramienta de desarrollo)."""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DSS_HOME"] = str(ROOT / "_testdata_flows")
shutil.rmtree(os.environ["DSS_HOME"], ignore_errors=True)

RESULTS: list[tuple[bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((bool(condition), name))
    print(("OK    " if condition else "FALLO ") + name + (f"  {detail}" if detail else ""))


def pump(app: tk.Misc, seconds: float = 0.7) -> None:
    end = time.time() + seconds
    while time.time() < end:
        try:
            app.update()
        except tk.TclError:
            return
        time.sleep(0.02)


class FakeConfirm:
    def __init__(self, *args, **kwargs):
        self.value = True

    def show(self):
        return self.value


def main() -> None:
    from dss.ui.app import App
    from dss.ui.pages import moderation as moderation_module
    from dss.ui.pages.automod import AutomodRuleModal
    from dss.ui.pages.channels import ChannelCreateModal
    from dss.ui.pages.emojis import EmojiUploadModal
    from dss.ui.pages.modals import BanModal
    from dss.ui.pages.webhooks import WebhookCreateModal
    from dss.util import image_to_data_uri

    moderation_module.ConfirmDialog = FakeConfirm  # type: ignore[assignment]
    import dss.ui.pages.channels as channels_module

    channels_module.ConfirmDialog = FakeConfirm  # type: ignore[assignment]

    app = App()
    app.settings.set("live_sync", False)
    check("login OAuth + bot",
          hasattr(app._view, "bot_token") and not hasattr(app._view, "kind"),
          type(app._view).__name__)
    app.start_demo()
    pump(app, 0.6)
    check("solo servidores administrados", len(app.guilds) == 2
          and all(guild.can_manage for guild in app.guilds),
          f"-> {[g.name for g in app.guilds]}")
    check("servidor sin permisos oculto",
          not any(guild.name == "Comunidad Nova" for guild in app.guilds))
    check("ocultos contados", app.hidden_guilds == 1, str(app.hidden_guilds))

    summary = next(g for g in app.guilds if g.name == "Estudio Lunar")
    app.open_guild(summary)
    pump(app, 1.0)
    check("abrir servidor", app.guild is not None and app.shell is not None)
    check("cuenta de demostración con Nitro", app.user.has_nitro)
    check("servidor comunidad activa", app.guild.is_community)
    check("servidor con nivel 2 de mejoras", app.guild.boost_level == 2)
    check("beneficios de nivel 2", app.guild.can_use_animated_icon and app.guild.can_use_banner)

    # ---------------- Canales ----------------
    app.shell.switch_page("channels")
    pump(app, 0.8)
    page = app.shell._pages["channels"]
    channel = next(c for c in app.channels if c.is_text and c.name == "general")
    page._select(channel)
    pump(app, 0.2)
    page.name_var.set("general-editado")
    page._save(channel)
    pump(app, 1.0)
    updated = next(c for c in app.channels if c.id == channel.id)
    check("canal renombrado", updated.name == "general-editado", f"-> {updated.name}")

    page._select(updated)
    pump(app, 0.2)
    page.name_var.set("OTRO Nombre Ñ")
    pump(app, 0.2)
    check("nombre normalizado al editar", page.name_var.get() == "otro-nombre-n",
          f"-> {page.name_var.get()!r}")
    page._save(updated)
    pump(app, 1.0)
    updated = next(c for c in app.channels if c.id == channel.id)
    check("canal editado en minúsculas", updated.name == "otro-nombre-n", f"-> {updated.name}")

    page._insert_topic_emoji("🔥")
    check("emoji insertado en el tema", "🔥" in page.topic_text.get("1.0", "end"))

    from dss.ui.widgets import ConfirmDialog

    confirm = ConfirmDialog(app, "Prueba", "Prueba", require_text="otro-nombre-n")
    confirm.require_var.set("OTRO-NOMBRE-N")
    confirm._confirm()
    check("confirmación sin distinguir mayúsculas", confirm._result is True)

    modal = ChannelCreateModal(page, app, page)
    types = [label for _value, label in modal._types]
    check("comunidad permite anuncios y foro", "Anuncios" in types and "Foro" in types,
          str(types))
    modal.name_var.set("Sala Nueva!! 2")
    pump(app, 0.2)
    check("nombre normalizado al crear", modal.name_var.get() == "sala-nueva-2",
          f"-> {modal.name_var.get()!r}")
    modal.type_var.set("Texto")
    modal._submit()
    pump(app, 1.0)
    created = next((c for c in app.channels if c.name == "sala-nueva-2"), None)
    check("canal creado", created is not None)

    if created is not None:
        page._select(created)
        pump(app, 0.2)
        page._delete(created)
        pump(app, 1.0)
        check("canal eliminado", not any(c.id == created.id for c in app.channels))

    # Permisos por canal
    from dss.ui.pages.channels import OverwritesModal

    target_channel = next(c for c in app.channels if c.is_text and c.name == "memes")
    member_role = next(r for r in app.guild.roles if r.name == "Miembro")
    overwrites = OverwritesModal(page, app, target_channel)
    overwrites.target_var.set(member_role.name)
    overwrites._change_target()
    overwrites._editor._set_all(1)
    overwrites._save()
    pump(app, 1.0)
    refreshed = next(c for c in app.client.list_channels(app.guild.id)
                     if c.id == target_channel.id)
    check("permisos de canal guardados",
          any(o.id == member_role.id for o in refreshed.permission_overwrites))

    # ---------------- Roles ----------------
    app.shell.switch_page("roles")
    pump(app, 0.9)
    roles_page = app.shell._pages["roles"]
    role = next(r for r in app.guild.roles if r.name == "Miembro")
    roles_page._select(role)
    pump(app, 0.2)
    before = role.permissions
    roles_page.grid.set_bits(before | (1 << 7))  # ver registro de auditoría
    roles_page._save(role)
    pump(app, 1.0)
    updated_role = next(r for r in app.guild.roles if r.id == role.id)
    check("rol actualizado", updated_role.permissions & (1 << 7) != 0,
          f"antes={before} ahora={updated_role.permissions}")

    # ---------------- Reordenar roles arrastrando ----------------
    dragged = next(r for r in app.guild.roles if r.name == "Artista")
    target = next(r for r in app.guild.roles if r.name == "Soporte")
    roles_page._select(dragged)
    pump(app, 0.3)
    target_index = next(i for i, (item, _row) in enumerate(roles_page._drag_rows)
                        if item.id == target.id)
    old_position = dragged.position
    roles_page._drag_press(dragged, SimpleNamespace(x_root=0, y_root=0))
    roles_page._drag_started = True
    roles_page._drag_target = target_index
    roles_page._drag_release(SimpleNamespace(x_root=0, y_root=0))
    pump(app, 0.9)
    dragged_now = next(r for r in app.guild.roles if r.id == dragged.id)
    check("rol reordenado arrastrando", dragged_now.position != old_position,
          f"{old_position} -> {dragged_now.position}")

    # ---------------- Roles masivos (JSON) ----------------
    roles_page.tabs.select("bulk")
    pump(app, 0.4)
    bulk = roles_page.bulk
    victim = next(r for r in app.guild.roles if r.name == "Silenciado")
    payload = {
        "create": [{
            "name": "Bulk Creado", "color": "#112233", "hoist": True,
            "mentionable": True, "permissions": ["SendMessages", "AttachFiles"],
        }],
        "modify": [{"target_name": "Miembro", "name": "Miembro Masivo",
                    "color": "#445566"}],
        "delete": [{"id": victim.id, "reason": "Prueba masiva"}],
        "view": [{"target_name": "Administrador"}],
    }
    bulk.load_text(json.dumps(payload), format_json=True)
    pump(app, 0.3)
    check("roles masivos previsualizados", len(bulk._ops) == 4
          and len(bulk.table._rows) == 4, f"{len(bulk._ops)} operaciones")
    check("JSON indentado y coloreado", "\n  \"create\"" in bulk.text.get("1.0", "end")
          and bool(bulk.text.tag_ranges("key")))
    bulk.run_bulk()
    deadline = time.time() + 8
    while bulk._running and time.time() < deadline:
        pump(app, 0.2)
    pump(app, 0.8)
    created = next((r for r in app.guild.roles if r.name == "Bulk Creado"), None)
    modified = next((r for r in app.guild.roles if r.name == "Miembro Masivo"), None)
    check("rol masivo creado", created is not None
          and created.permissions & (1 << 11) and created.permissions & (1 << 15))
    check("rol masivo modificado", modified is not None and modified.color == 0x445566)
    check("rol masivo eliminado", all(r.id != victim.id for r in app.guild.roles))
    check("roles masivos completados", not bulk._running
          and "Completado" in bulk.status_label.cget("text")
          and bulk.progress.cget("value") == 4,
          bulk.status_label.cget("text"))
    bulk.load_text('{"create": [{"name": "X", "permissions": ["NoExiste"]}]}')
    pump(app, 0.3)
    check("error de permiso bloquea la carga",
          bool(bulk._ops) and not bulk._ops[0]["valid"]
          and str(bulk.btn_run.cget("state")) == "disabled")
    bulk.clear()

    # ---------------- Miembros ----------------
    app.shell.switch_page("members")
    pump(app, 0.9)
    members_page = app.shell._pages["members"]
    member = members_page._members[3]
    from dss.ui.pages.members import MemberModal

    member_modal = MemberModal(members_page, app, members_page, member)
    admin_role = next(r for r in app.guild.roles if r.name == "Administrador")
    member_modal.role_vars[admin_role.id].set(True)
    member_modal._save()
    pump(app, 1.2)
    saved_member = next(m for m in app.client.list_members(app.guild.id, 100) if m.user.id == member.user.id)
    check("rol asignado a miembro", admin_role.id in saved_member.roles)

    from dss.ui.pages.modals import DirectMessageModal

    dm = DirectMessageModal(members_page, app, member.user.id, member.display_name)
    dm._insert_emoji("🎉")
    check("emoji insertado en mensaje directo",
          "🎉" in dm.text.get("1.0", "end"))
    dm.close()

    # ---------------- Sanciones ----------------
    app.shell.switch_page("moderation")
    pump(app, 0.9)
    moderation_page = app.shell._pages["moderation"]
    bans_tab = moderation_page._frames["bans"]
    before_bans = len(bans_tab._bans)
    ban_modal = BanModal(bans_tab, app, user_id="123456789012345678",
                         username="cuenta_de_prueba", on_done=bans_tab.load)
    ban_modal.reason_text.insert("1.0", "Prueba automatizada")
    ban_modal._submit()
    pump(app, 1.2)
    check("baneo creado", len(bans_tab._bans) == before_bans + 1,
          f"{before_bans} -> {len(bans_tab._bans)}")

    # ---------------- Mensajes ----------------
    moderation_page.tabbar.select("messages")
    pump(app, 0.8)
    messages_tab = moderation_page._frames["messages"]
    messages_tab.channel_var.set("#otro-nombre-n")
    messages_tab.load()
    pump(app, 0.8)
    total_messages = len(messages_tab._messages)
    messages_tab.composer_var.set("Mensaje enviado por la prueba")
    messages_tab._send()
    pump(app, 0.9)
    check("mensaje enviado", any("prueba" in m.content for m in messages_tab._messages),
          f"mensajes={total_messages}")

    # Selector de emojis (estándar y del servidor)
    messages_tab._open_emoji_picker()
    pump(app, 0.3)
    picker = getattr(app, "_emoji_picker", None)
    check("selector de emojis abierto", picker is not None)
    if picker is not None:
        picker._can_close = False
        picker._pick("🎉", "fiesta")
        check("emoji insertado en el mensaje", "🎉" in messages_tab.composer_var.get(),
              f"-> {messages_tab.composer_var.get()!r}")
        picker._on_tab("guild")
        pump(app, 0.4)
        picker._pick("<:luna:123>", "luna")
        check("emoji de servidor insertado", "<:luna:123>" in messages_tab.composer_var.get())
        picker.close()
        pump(app, 0.2)

    first_ids = messages_tab.table.selected_ids()
    messages_tab.table.tree.selection_set(messages_tab.table.tree.get_children()[0])
    before_purge = len(messages_tab._messages)
    messages_tab._purge()
    pump(app, 1.2)
    check("mensajes eliminados", len(messages_tab._messages) == before_purge - 1,
          f"{before_purge} -> {len(messages_tab._messages)}")

    # ---------------- Invitaciones ----------------
    app.shell.switch_page("invites")
    pump(app, 0.9)
    invites_page = app.shell._pages["invites"]
    before_invites = len(invites_page._invites)
    invites_page.channel_var.set(invites_page.channel_combo["values"][0])
    invites_page._create()
    pump(app, 1.0)
    check("invitación creada", len(invites_page._invites) == before_invites + 1,
          f"{before_invites} -> {len(invites_page._invites)}")

    # ---------------- Webhooks ----------------
    app.shell.switch_page("webhooks")
    pump(app, 0.9)
    webhooks_page = app.shell._pages["webhooks"]
    before_webhooks = len(webhooks_page._webhooks)
    webhook_modal = WebhookCreateModal(webhooks_page, app, webhooks_page)
    webhook_modal.name_var.set("Webhook de prueba")
    webhook_modal._submit()
    pump(app, 1.0)
    check("webhook creado", len(webhooks_page._webhooks) == before_webhooks + 1,
          f"{before_webhooks} -> {len(webhooks_page._webhooks)}")

    # ---------------- Emojis ----------------
    app.shell.switch_page("emojis")
    pump(app, 0.9)
    emojis_page = app.shell._pages["emojis"]
    before_emojis = len(emojis_page._emojis)
    emoji_modal = EmojiUploadModal(emojis_page, app, emojis_page)
    emoji_modal.name_var.set("prueba_emoji")
    emoji_modal._data_uri = image_to_data_uri(ROOT / "dss" / "ui" / "assets" / "app.png")
    emoji_modal._submit()
    pump(app, 1.0)
    check("emoji subido", len(emojis_page._emojis) == before_emojis + 1,
          f"{before_emojis} -> {len(emojis_page._emojis)}")

    # ---------------- Automod ----------------
    app.shell.switch_page("automod")
    pump(app, 0.9)
    automod_page = app.shell._pages["automod"]
    before_rules = len(automod_page._rules)
    automod_modal = AutomodRuleModal(automod_page, app, None, automod_page.refresh)
    automod_modal.name_var.set("Regla de prueba")
    automod_modal.trigger_var.set("Palabras clave")
    automod_modal._sync_fields()
    automod_modal.keywords_text.insert("1.0", "palabra-prohibida\nfrase prohibida")
    automod_modal._submit()
    pump(app, 1.2)
    check("regla de automod creada", len(automod_page._rules) == before_rules + 1,
          f"{before_rules} -> {len(automod_page._rules)}")

    # ---------------- Ajustes ----------------
    app.shell.switch_page("settings")
    pump(app, 0.9)
    settings_page = app.shell._pages["settings"]
    check("ajustes con comunidad", settings_page._community)
    check("banner habilitado con nivel 2",
          str(settings_page.banner_change_button.cget("state")) == "normal")
    settings_page.name_var.set("Estudio Lunar Renombrado")
    settings_page.desc_text.delete("1.0", "end")
    settings_page.desc_text.insert("1.0", "Descripción actualizada por la prueba.")
    settings_page._save()
    pump(app, 1.2)
    check("ajustes guardados", app.guild.name == "Estudio Lunar Renombrado",
          f"-> {app.guild.name}")
    check("subtítulo de cabecera actualizado", app.shell.guild_name.cget("text") == app.guild.name)

    # ---------------- Servidor oculto (sin permisos administrativos) ----------------
    all_summaries = app.client.list_guilds()
    nova = next(guild for guild in all_summaries if guild.name == "Comunidad Nova")
    current_id = app.guild.id
    app.open_guild(nova)
    pump(app, 0.6)
    check("servidor sin permisos no se abre", app.guild.id == current_id)
    check("servidor oculto no está en la lista",
          not any(guild.id == nova.id for guild in app.guilds))

    # ---------------- Servidor sin comunidad ni mejoras ----------------
    pruebas = next(g for g in app.guilds if g.name == "Servidor de Pruebas")
    app.open_guild(pruebas)
    pump(app, 1.2)
    check("servidor sin comunidad", not app.guild.is_community)
    check("servidor sin mejoras", app.guild.boost_level == 0 and not app.guild.can_use_banner)
    app.shell.switch_page("channels")
    pump(app, 0.9)
    channels_page = app.shell._pages["channels"]
    plain_modal = ChannelCreateModal(channels_page, app, channels_page)
    plain_types = [label for _value, label in plain_modal._types]
    check("sin comunidad solo texto y voz", plain_types == ["Texto", "Voz"], str(plain_types))
    plain_modal.close()
    app.shell.switch_page("settings")
    pump(app, 0.9)
    plain_settings = app.shell._pages["settings"]
    check("sin comunidad no hay canal de reglas", plain_settings.rules_channel_var is None)
    check("banner bloqueado sin nivel 2",
          str(plain_settings.banner_change_button.cget("state")) == "disabled")
    app.shell.switch_page("emojis")
    pump(app, 0.9)
    emojis_plain = app.shell._pages["emojis"]
    check("límite de emojis nivel 0", "/50" in emojis_plain.count_label.cget("text"),
          emojis_plain.count_label.cget("text"))

    # ---------------- Logout ----------------
    import dss.ui.app as app_module
    app_module.ConfirmDialog = FakeConfirm  # type: ignore[assignment]
    app.logout()
    pump(app, 0.6)
    check("cerrar sesión", app.client is None and app.guild is None)
    app.on_close()

    # ---------------- Estado del login ----------------
    app2 = App()
    pump(app2, 0.4)
    check("sin usuarios internos", hasattr(app2._view, "bot_token")
          and hasattr(app2._view, "login_button"))
    check("OAuth configurado por defecto",
          app2._view.client_id.get() == "1574502573577343058",
          app2._view.client_id.get())
    app2.on_close()

    total = len(RESULTS)
    failed = [name for ok, name in RESULTS if not ok]
    print(f"\nRESULTADO: {total - len(failed)}/{total} correctas")
    if failed:
        print("FALLOS:", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
