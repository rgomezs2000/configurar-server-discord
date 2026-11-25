"""Informe de texto completo del servidor a partir de los datos cargados."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .constants import CHANNEL_TYPES, GUILD_FEATURES
from .models import Channel, Guild, permission_names, snowflake_time

TYPE_NAMES = {0: "Texto", 2: "Voz", 4: "Categoría", 5: "Anuncios",
              13: "Escenario", 15: "Foro", 16: "Media"}


def _line(char: str = "─", size: int = 78) -> str:
    return char * size


def _features(guild: Guild) -> str:
    if not guild.features:
        return "—"
    return ", ".join(GUILD_FEATURES.get(feature, feature) for feature in guild.features)


def _channel_type(channel: Channel) -> str:
    return TYPE_NAMES.get(channel.type, f"Tipo {channel.type}")


def _overwrites(channel: Channel, role_names: dict[str, str], everyone: str | None) -> list[str]:
    lines: list[str] = []
    for overwrite in channel.permission_overwrites:
        if overwrite.id == everyone:
            name = "@everyone"
        elif overwrite.type == 1:
            name = f"Usuario {overwrite.id}"
        else:
            name = f"@{role_names.get(overwrite.id, overwrite.id)}"
        allowed = ", ".join(permission_names(overwrite.allow)) or "—"
        denied = ", ".join(permission_names(overwrite.deny)) or "—"
        lines.append(f"      · {name}")
        lines.append(f"        Permitir: {allowed}")
        lines.append(f"        Denegar:  {denied}")
    return lines


def build_server_report(guild: Guild, channels: list[Channel],
                        emojis: list[Any] | None = None,
                        invites: list[Any] | None = None) -> str:
    created = snowflake_time(guild.id)
    role_names = {role.id: role.name for role in guild.roles}
    everyone = guild.everyone_role.id if guild.everyone_role else None
    lines: list[str] = [
        "DISCORD SERVER STUDIO · INFORME DEL SERVIDOR",
        f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        _line("="),
        "",
        "SERVIDOR",
        _line(),
        f"Nombre:          {guild.name}",
        f"ID:              {guild.id}",
        f"Creado:          {created.strftime('%Y-%m-%d %H:%M:%S') if created else '—'}",
        f"Propietario ID:  {guild.owner_id or '—'}",
        f"Descripción:     {guild.description or '—'}",
        f"Miembros:        {guild.member_count}",
        f"En línea:        {guild.presence_count}",
        f"Comunidad:       {'Sí' if guild.is_community else 'No'}",
        f"Nivel de mejoras:{guild.boost_level} ({guild.premium_subscription_count} boosts)",
        f"Verificación:    {guild.verification_level}",
        f"Filtro contenido:{guild.explicit_content_filter}",
        f"Idioma:          {guild.preferred_locale}",
        f"Emojis:          {guild.emoji_count}/{guild.max_emoji_slots}",
        f"Stickers:        {guild.sticker_count}/{guild.max_sticker_slots}",
        f"Funciones:       {_features(guild)}",
        "",
        f"ROLES ({len(guild.roles)})",
        _line(),
    ]
    for role in sorted(guild.roles, key=lambda r: r.position, reverse=True):
        flags = []
        if role.is_everyone:
            flags.append("@everyone")
        if role.managed:
            flags.append("gestionado por app")
        if role.hoist:
            flags.append("separado")
        if role.mentionable:
            flags.append("mencionable")
        lines.append(f"  @{role.name}  [ID {role.id}]")
        lines.append(f"    Posición: {role.position} · Color: {role.color}"
                     + (f" · {', '.join(flags)}" if flags else ""))
        lines.append("    Permisos: " + (", ".join(permission_names(role.permissions))
                                         or "—"))
        lines.append("")

    categories = sorted((c for c in channels if c.is_category),
                        key=lambda c: c.position)
    used: set[str] = set()
    lines += [f"CATEGORÍAS Y CANALES ({len([c for c in channels if not c.is_category])} canales)",
              _line()]
    for category in categories:
        lines.append(f"  📁 {category.name}  [ID {category.id}] · posición {category.position}")
        lines.extend(_overwrites(category, role_names, everyone))
        for child in sorted((c for c in channels
                             if c.parent_id == category.id and not c.is_category),
                            key=lambda c: c.position):
            used.add(child.id)
            lines.append(f"    #{child.display_name}  [{_channel_type(child)}] · ID {child.id}")
            if child.topic:
                lines.append(f"      Tema: {child.topic}")
            if child.nsfw:
                lines.append("      NSFW: sí")
            if child.rate_limit_per_user:
                lines.append(f"      Modo lento: {child.rate_limit_per_user}s")
            if child.user_limit:
                lines.append(f"      Límite de usuarios: {child.user_limit}")
            lines.extend(_overwrites(child, role_names, everyone))
        lines.append("")

    leftovers = [c for c in channels if not c.is_category and c.id not in used]
    if leftovers:
        lines.append("  SIN CATEGORÍA")
        for channel in sorted(leftovers, key=lambda c: c.position):
            lines.append(f"    #{channel.display_name}  [{_channel_type(channel)}] · ID {channel.id}")
            if channel.topic:
                lines.append(f"      Tema: {channel.topic}")
            if channel.nsfw:
                lines.append("      NSFW: sí")
            if channel.rate_limit_per_user:
                lines.append(f"      Modo lento: {channel.rate_limit_per_user}s")
            lines.extend(_overwrites(channel, role_names, everyone))
        lines.append("")

    if emojis is not None:
        lines += [f"EMOJIS ({len(emojis)})", _line()]
        for emoji in emojis:
            lines.append(f"  :{emoji.name}:  [ID {emoji.id}]"
                         + (" · animado" if emoji.animated else ""))
        lines.append("")

    if invites is not None:
        lines += [f"INVITACIONES ACTIVAS ({len(invites)})", _line()]
        for invite in invites:
            lines.append(f"  {invite.code} · usos {invite.uses_label} · "
                         f"expira {invite.expires_label} · canal {invite.channel_id}")
        lines.append("")

    lines += [
        _line("="),
        "Fin del informe. Los datos se tomaron de la caché actual de la app.",
    ]
    return "\n".join(lines)
