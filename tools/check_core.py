"""Comprobaciones rápidas de la capa de datos (no forma parte de la app)."""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["DSS_HOME"] = str(ROOT / "_testdata_core")
shutil.rmtree(os.environ["DSS_HOME"], ignore_errors=True)
sys.path.insert(0, str(ROOT))

from dss.api import DiscordClient  # noqa: E402
from dss.constants import AUDIT_ACTIONS, PERMISSIONS  # noqa: E402
from dss.errors import DiscordError  # noqa: E402
from dss.http import DiscordHTTP, route_template  # noqa: E402
from dss.models import Channel, Guild, GuildSummary, Member, User  # noqa: E402
from dss.store import TokenStore  # noqa: E402
from dss.util import normalize_channel_name  # noqa: E402

failures = []


def check(name, condition, detail=""):
    print(("OK   " if condition else "FALLO") + f"  {name} {detail}")
    if not condition:
        failures.append(name)


check("permisos", len(PERMISSIONS) == 49, f"({len(PERMISSIONS)})")
check("acciones auditoria", len(AUDIT_ACTIONS) > 40, f"({len(AUDIT_ACTIONS)})")
check("plantilla de ruta", route_template("/channels/123/messages/456") == "channels/:id/messages/:id")

store = TokenStore()
print("       método de cifrado:", store.method_label())
saved = store.save("token-de-prueba-123", "bot")
check("guardar token", saved)
loaded = store.load()
check("recuperar token", loaded == ("token-de-prueba-123", "bot"), str(loaded))
store.clear()
check("borrar token", store.load() is None)

fixed = TokenStore.for_bot()
check("guardar token fijo del bot", fixed.save("token-fijo-123", "bot"))
check("recuperar token fijo del bot", fixed.load() == ("token-fijo-123", "bot"))
fixed.clear()
check("borrar token fijo del bot", fixed.load() is None)

user = User.from_dict({"id": "123456789012345678", "username": "luna_dev",
                       "global_name": "Luna", "discriminator": "0", "bot": False})
check("usuario", user.display_name == "Luna" and user.initials == "LU")
check("avatar por defecto", "embed/avatars" in user.avatar_url, user.avatar_url)

guild = Guild.from_dict({
    "id": "42", "name": "Estudio Lunar", "owner_id": "1", "verification_level": 3,
    "approximate_member_count": 128, "approximate_presence_count": 17,
    "roles": [{"id": "42", "name": "@everyone", "position": 0, "permissions": "1024"},
              {"id": "43", "name": "Admin", "position": 5, "permissions": "8", "color": 15158332}],
    "emojis": [{"id": "1", "name": "luna"}], "features": ["COMMUNITY", "BANNER"],
})
check("guild", guild.member_count == 128 and guild.presence_count == 17)
check("guild roles", len(guild.roles) == 2 and guild.roles[1].color_hex == "#e74c3c")
check("everyone", guild.everyone_role is not None and guild.everyone_role.id == "42")

channel = Channel.from_dict({"id": "9", "type": 0, "name": "general", "position": 3,
                             "topic": "Charla", "parent_id": "5",
                             "permission_overwrites": [{"id": "42", "type": 0, "allow": "2048", "deny": "0"}]})
check("canal", channel.is_text and channel.display_name == "general" and channel.glyph == "#")
check("overwrite", channel.permission_overwrites[0].allow == 2048)

member = Member.from_dict({"user": {"id": "7", "username": "ana"}, "roles": ["43"],
                           "joined_at": "2024-03-01T12:00:00.000000+00:00",
                           "communication_disabled_until": "2099-01-01T00:00:00+00:00"})
check("miembro", member.display_name == "ana" and member.is_timed_out and "Aislado" in member.timeout_label)

import time
client = DiscordHTTP("token-invalido-de-prueba", "bot")
start = time.perf_counter()
try:
    client.get("/users/@me")
    check("401 esperado", False, "la petición no falló")
except DiscordError as error:
    check("error 401", error.status == 401, f"-> {error.message}")
    check("mensaje en español", "Token inválido" in str(error) or "Token no válido" in str(error), f"-> {error}")
elapsed = time.perf_counter() - start
check("sin reintentos inútiles", elapsed < 6, f"({elapsed:.2f}s)")

session = DiscordClient("x", "bot")
check("guild summary admin", GuildSummary.from_dict({"id": "1", "name": "x", "permissions": "8"}).is_admin)
check("nivel de acceso propietario",
      GuildSummary.from_dict({"id": "1", "name": "x", "owner": True, "permissions": "0"}).access_label
      == "Propietario")
check("nivel de acceso administrador",
      GuildSummary.from_dict({"id": "1", "name": "x", "permissions": "8"}).access_label
      == "Administrador")
check("nivel de acceso moderador",
      GuildSummary.from_dict({"id": "1", "name": "x", "permissions": str(1 << 2)}).access_label
      == "Moderador")
check("nivel de acceso miembro",
      GuildSummary.from_dict({"id": "1", "name": "x", "permissions": str(1 << 10)}).access_label
      == "Miembro")
check("gestión de servidor",
      GuildSummary.from_dict({"id": "1", "name": "x", "permissions": str(1 << 5)}).can_manage)

check("normaliza nombre de canal",
      normalize_channel_name("  Mi Canal Ñandú!!  ") == "mi-canal-nandu",
      normalize_channel_name("  Mi Canal Ñandú!!  "))
check("conserva números y guiones",
      normalize_channel_name("Sala 2 - Copia") == "sala-2-copia",
      normalize_channel_name("Sala 2 - Copia"))
check("quita caracteres no permitidos",
      normalize_channel_name("hola@mundo#2024") == "holamundo2024",
      normalize_channel_name("hola@mundo#2024"))
check("nombre vacío tras limpiar", normalize_channel_name("¡¡¡") == "")

nitro_user = User.from_dict({"id": "5", "username": "nitro", "premium_type": 2})
check("cuenta con Nitro", nitro_user.has_nitro and nitro_user.nitro_label == "Nitro")
check("cuenta sin Nitro", not User.from_dict({"id": "6", "username": "free"}).has_nitro)
check("bot sin Nitro", not User.from_dict({"id": "7", "username": "bot",
                                           "bot": True, "premium_type": 2}).has_nitro)

guild_free = Guild.from_dict({"id": "1", "name": "libre", "features": [],
                              "premium_tier": 0, "premium_subscription_count": 0})
check("servidor sin comunidad", not guild_free.is_community)
check("límites sin mejoras", guild_free.max_emoji_slots == 50
      and guild_free.max_voice_bitrate == 96000 and not guild_free.can_use_banner)

guild_boosted = Guild.from_dict({"id": "2", "name": "boost", "features": ["COMMUNITY", "BANNER"],
                                 "premium_tier": 2, "premium_subscription_count": 9})
check("comunidad activa", guild_boosted.is_community)
check("límites nivel 2", guild_boosted.max_emoji_slots == 150
      and guild_boosted.max_voice_bitrate == 256000)
check("beneficios nivel 2", guild_boosted.can_use_animated_icon
      and guild_boosted.can_use_banner and not guild_boosted.can_use_vanity_url)
check("boosts para nivel 3", guild_boosted.boosts_to_next_level == 5,
      str(guild_boosted.boosts_to_next_level))

guild_max = Guild.from_dict({"id": "3", "name": "max", "features": ["COMMUNITY"],
                             "premium_tier": 3, "premium_subscription_count": 20})
check("nivel máximo", guild_max.max_emoji_slots == 250
      and guild_max.can_use_vanity_url and guild_max.boosts_to_next_level == 0)

print("\nRESULTADO:", "TODO OK" if not failures else f"FALLOS: {failures}")
sys.exit(1 if failures else 0)
