"""Cliente de demostración: mismos métodos que DiscordClient, datos inventados.

Permite recorrer toda la aplicación sin token (y sin tocar ningún servidor real).
Todas las acciones modifican el estado en memoria para que la interfaz se sienta
viva: crear un canal, banear a alguien o editar un rol se refleja al instante.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .errors import DiscordError
from .models import (AuditEntry, AutoModRule, Ban, Channel, Emoji, Guild,
                     GuildSummary, Invite, Member, Message, PermissionOverwrite,
                     Role, User, Webhook, bits, parse_ts)

DEMO_TOKEN = "DEMO"
_EPOCH = datetime.now(timezone.utc) - timedelta(days=430)


def perm(*bit_numbers: int) -> int:
    value = 0
    for bit in bit_numbers:
        value |= 1 << bit
    return value


EVERYONE_PERMS = perm(10, 11, 16, 6, 20, 21, 25, 14, 15, 18)
MEMBER_PERMS = perm(10, 11, 16, 6, 14, 15, 18)
SUPPORT_PERMS = perm(10, 11, 16, 6, 13, 14, 15, 18)
MOD_PERMS = perm(10, 11, 16, 6, 13, 1, 2, 40, 7, 17, 22, 23, 24, 27, 14, 15)
ARTIST_PERMS = perm(10, 11, 16, 6, 14, 15, 18, 37)
BOT_PERMS = perm(10, 11, 16, 13, 14, 15)
MUTED_PERMS = perm(10, 16)

NAMES = [
    "luna_dev", "mateo", "valentina", "santi", "camila", "nico", "sofi", "tomas",
    "isabella", "joaquin", "renata", "benja", "martina", "lucas", "emilia",
    "franco", "julieta", "alonzo", "delfina", "bruno", "agustina", "ian",
    "malena", "thiago", "olivia", "gonzalo", "paula", "fede", "antonella",
    "maximo", "clara", "dante", "lara", "emiliano", "ximena", "ulises",
    "paloma", "tobias", "ines", "aaron", "noe", "riba",
]
BOTS = [("midnight", "Midnight"), ("rythm", "Rythm"), ("carl-bot", "Carl-bot"), ("wanderer", "Wanderer")]

CHAT_LINES = [
    "¿Alguien probó el nuevo canal de foro?",
    "Subí las capturas del evento de ayer 📸",
    "Buenass, ¿cómo va la semana?",
    "Recuerden leer #reglas antes de publicar",
    "El bot de música está caído, avisamos al admin",
    "Propongo hacer una noche de películas el viernes",
    "Ya está el resumen del torneo en #anuncios",
    "Cambié el tema del canal, se ve mucho mejor",
    "¿Se puede pedir el rol de artista?",
    "Gracias por la mano con el diseño 🙌",
    "Nuevo récord: 120 personas conectadas",
    "Ojo con los enlaces sospechosos en MD",
    "Voy a estar desconectado unos días, nos vemos",
    "¿Qué opinan del nuevo icono del servidor?",
    "Pasen por el escenario, hay charla de arte",
    "El sorteo cierra a las 20:00",
    "Arreglado el problema de los permisos",
    "Bienvenidos a los nuevos 👋",
]


class _GuildState:
    def __init__(self) -> None:
        self.guild: Guild | None = None
        self.channels: list[Channel] = []
        self.members: list[Member] = []
        self.bans: list[Ban] = []
        self.invites: list[Invite] = []
        self.webhooks: list[Webhook] = []
        self.emojis: list[Emoji] = []
        self.rules: list[AutoModRule] = []
        self.audit: list[AuditEntry] = []
        self.messages: dict[str, list[Message]] = {}
        self.dm_channels: dict[str, str] = {}


class DemoClient:
    kind = "demo"
    token = ""

    def __init__(self) -> None:
        self.me = User(id="800000000000000001", username="tu_cuenta", global_name="Tú",
                       discriminator="0", premium_type=2)
        self.application = {"id": "800000000000000900", "name": "Discord Server Studio (demo)",
                            "description": "Sesión de demostración con datos inventados."}
        self._states: dict[str, _GuildState] = {}
        self._counter = 0
        self._rng = random.Random(7)
        self._build_all()

    # -- helpers ------------------------------------------------------------ #
    def _id(self) -> str:
        self._counter += 1
        return str(900000000000000000 + self._counter)

    def _state(self, guild_id: str) -> _GuildState:
        state = self._states.get(str(guild_id))
        if state is None:
            raise DiscordError("El servidor de demostración no existe.", status=404)
        return state

    def _audit(self, state: _GuildState, action_type: int, target_id: str | None = None,
               reason: str | None = None) -> None:
        state.audit.insert(0, AuditEntry(
            id=self._id(), action_type=action_type, user_id=self.me.id,
            target_id=target_id, reason=reason, created_at=datetime.now(timezone.utc),
            actor=self.me,
        ))

    def _member(self, state: _GuildState, user_id: str) -> Member:
        for member in state.members:
            if member.user.id == str(user_id):
                return member
        raise DiscordError("Ese miembro no está en el servidor de demostración.", status=404)

    # -- construcción de datos --------------------------------------------- #
    def _build_all(self) -> None:
        self._build_guild(
            guild_id="710000000000000001", name="Estudio Lunar", owner=True,
            description="Comunidad de arte, música y desarrollo. Un lugar tranquilo para crear.",
            member_target=46, features=["COMMUNITY", "BANNER", "ANIMATED_ICON", "NEWS"],
            verification_level=3, color="#5865f2", premium_tier=2, boosts=9,
        )
        self._build_guild(
            guild_id="710000000000000002", name="Comunidad Nova", owner=False,
            description="Servidor de soporte técnico y charlas sobre software libre.",
            member_target=18, features=["COMMUNITY", "DISCOVERABLE"],
            verification_level=2, color="#23a55a", admin=False,
            premium_tier=0, boosts=0,
        )
        self._build_guild(
            guild_id="710000000000000003", name="Servidor de Pruebas", owner=True,
            description="Laboratorio personal para probar roles, permisos y automatizaciones.",
            member_target=5, features=[], verification_level=0,
            color="#f0b232", premium_tier=0, boosts=0,
        )

    def _build_guild(self, *, guild_id: str, name: str, owner: bool, description: str,
                     member_target: int, features: list[str], verification_level: int,
                     color: str, admin: bool = True, premium_tier: int = 0,
                     boosts: int = 0) -> None:
        state = _GuildState()
        roles = [
            Role(id=guild_id, name="@everyone", position=0, permissions=EVERYONE_PERMS),
            Role(id=self._id(), name="Administrador", position=6, permissions=8,
                 color=0xE74C3C, hoist=True, mentionable=False),
            Role(id=self._id(), name="Moderador", position=5, permissions=MOD_PERMS,
                 color=0x3498DB, hoist=True, mentionable=True),
            Role(id=self._id(), name="Soporte", position=4, permissions=SUPPORT_PERMS,
                 color=0x2ECC71, hoist=True, mentionable=True),
            Role(id=self._id(), name="Artista", position=3, permissions=ARTIST_PERMS,
                 color=0xEB459E, hoist=True, mentionable=True),
            Role(id=self._id(), name="Miembro", position=2, permissions=MEMBER_PERMS,
                 color=0x5865F2, hoist=False, mentionable=True),
            Role(id=self._id(), name="Bot", position=1, permissions=BOT_PERMS,
                 color=0x95A5A6, hoist=False, mentionable=False),
            Role(id=self._id(), name="Silenciado", position=1, permissions=MUTED_PERMS,
                 color=0x4F545C, hoist=False, mentionable=False),
        ]
        guild = Guild(
            id=guild_id, name=name, icon=None, description=description,
            owner_id=self.me.id if owner else "700000000000000042",
            member_count=member_target, presence_count=max(3, member_target // 3),
            verification_level=verification_level, explicit_content_filter=2,
            afk_timeout=300, premium_tier=premium_tier,
            premium_subscription_count=boosts,
            nsfw_level=1, mfa_level=1, default_message_notifications=1,
            preferred_locale="es-ES", features=features, roles=roles,
            emoji_count=7, sticker_count=2,
        )
        state.guild = guild

        categories = [
            Channel(id=self._id(), type=4, name="INFORMACIÓN", position=0, guild_id=guild_id),
            Channel(id=self._id(), type=4, name="COMUNIDAD", position=6, guild_id=guild_id),
            Channel(id=self._id(), type=4, name="VOZ", position=12, guild_id=guild_id),
        ]
        if admin:
            text_specs = [
                ("bienvenida", 1, categories[0].id, "Preséntate y lee las normas del servidor."),
                ("reglas", 2, categories[0].id, "Normas de convivencia. Léelas antes de participar."),
                ("anuncios", 3, categories[0].id, "Novedades y comunicados oficiales.", 5),
                ("general", 7, categories[1].id, "Charla general del servidor.", 0),
                ("memes", 8, categories[1].id, "Solo memes. Sin política ni spam.", 0),
                ("sugerencias", 9, categories[1].id, "Ideas para mejorar la comunidad.", 0),
                ("dudas", 10, categories[1].id, "Preguntas y ayuda técnica.", 15),
            ]
            voice_specs = [("Sala general", 13, 0), ("Música", 14, 0), ("Estudio", 15, 10)]
        else:
            text_specs = [
                ("anuncios", 1, categories[0].id, "Anuncios de la comunidad.", 5),
                ("general", 7, categories[1].id, "Charla general.", 0),
                ("soporte", 8, categories[1].id, "Pide ayuda con tu instalación.", 0),
            ]
            voice_specs = [("Voz general", 13, 0)]

        for text_name, position, parent, topic, *rest in text_specs:
            channel_type = rest[0] if rest else 0
            state.channels.append(Channel(
                id=self._id(), type=channel_type, name=text_name, position=position,
                parent_id=parent, topic=topic, guild_id=guild_id,
                rate_limit_per_user=5 if text_name == "general" else 0,
                nsfw=False,
            ))
        for voice_name, position, limit in voice_specs:
            state.channels.append(Channel(
                id=self._id(), type=2, name=voice_name, position=position,
                parent_id=categories[2].id, guild_id=guild_id, user_limit=limit,
                bitrate=96000,
            ))
        state.channels = categories + state.channels

        if "COMMUNITY" in features:
            rules = next((c for c in state.channels if c.name == "reglas"), None)
            updates = next((c for c in state.channels if c.name == "anuncios"), None)
            if rules is not None:
                guild.rules_channel_id = rules.id
            if updates is not None:
                guild.public_updates_channel_id = updates.id
                guild.system_channel_id = updates.id
            voice = next((c for c in state.channels if c.type == 2), None)
            if voice is not None:
                guild.afk_channel_id = voice.id

        # Miembros
        admin_role = roles[1]
        member_role = roles[5]
        joined_base = datetime.now(timezone.utc) - timedelta(days=390)
        total = member_target + 1
        for index in range(total):
            if index == 0:
                user = self.me
                role_ids = [roles[0].id, admin_role.id if admin else roles[2].id]
            elif index <= len(BOTS):
                username, display = BOTS[index - 1]
                user = User(id=str(710000000000100000 + index), username=username,
                            global_name=display, bot=True)
                role_ids = [roles[0].id, roles[6].id]
            else:
                username = NAMES[(index - 5) % len(NAMES)]
                if index > len(NAMES):
                    username = f"{username}_{index}"
                user = User(id=str(710000000000200000 + index), username=username,
                            global_name=username.replace("_", " ").title(),
                            discriminator="0")
                role_ids = [roles[0].id, member_role.id]
                if index % 7 == 0:
                    role_ids.append(roles[3].id)
                if index % 11 == 0:
                    role_ids.append(roles[4].id)
                if index % 9 == 0:
                    role_ids.append(roles[2].id)
                if index % 13 == 0:
                    role_ids.append(roles[7].id)

            member = Member(
                user=user,
                nick=None if index % 4 else f"{user.username} ✦",
                roles=role_ids,
                joined_at=joined_base + timedelta(days=index * 6, hours=index % 12),
                communication_disabled_until=(
                    datetime.now(timezone.utc) + timedelta(hours=2) if index in (4, 18) else None),
                mute=index % 17 == 0,
                pending=index % 23 == 0,
            )
            state.members.append(member)

        # Mensajes
        text_channels = [c for c in state.channels if c.is_text]
        for channel in text_channels:
            count = 26 if channel.name == "general" else (10 if channel.name in ("memes", "anuncios") else 4)
            messages: list[Message] = []
            base_id = int(self._id())
            for position in range(count):
                author = state.members[(position * 3 + 1) % len(state.members)].user
                when = datetime.now(timezone.utc) - timedelta(minutes=(count - position) * 17)
                messages.append(Message(
                    id=str(base_id + position), content=CHAT_LINES[(position + count) % len(CHAT_LINES)],
                    author=author, timestamp=when, pinned=(position == 1),
                ))
            state.messages[channel.id] = messages

        # Sanciones, invitaciones, webhooks, emojis, automod y auditoría
        for index, reason in enumerate(["Spam masivo en #general", "Insultos reiterados",
                                        "Publicidad no autorizada"]):
            state.bans.append(Ban(user=User(id=str(720000000000300000 + index),
                                            username=f"cuenta_retirada_{index + 1}"),
                                  reason=reason))
        state.invites = [
            Invite(code="luna-comunidad", uses=128, max_uses=0, max_age=0,
                   created_at=datetime.now(timezone.utc) - timedelta(days=42),
                   inviter=self.me, channel_id=text_channels[0].id,
                   channel_name=text_channels[0].display_name),
            Invite(code="evento-arte-2026", uses=34, max_uses=200, max_age=604800,
                   created_at=datetime.now(timezone.utc) - timedelta(days=3),
                   expires_at=datetime.now(timezone.utc) + timedelta(days=4),
                   inviter=state.members[2].user, channel_id=text_channels[1].id,
                   channel_name=text_channels[1].display_name),
        ]
        state.webhooks = [
            Webhook(id=self._id(), name="Anuncios automáticos", channel_id=text_channels[0].id,
                    token="demo-token-anuncios"),
            Webhook(id=self._id(), name="Registro de auditoría", channel_id=text_channels[-1].id,
                    token="demo-token-logs"),
        ]
        for emoji_name in ("luna", "cohete", "pixel", "gato", "fuego", "fiesta", "robot"):
            state.emojis.append(Emoji(id=self._id(), name=emoji_name))
        state.rules = [
            AutoModRule(id=self._id(), name="Anti spam", trigger_type=3,
                        trigger_metadata={"keyword_filter": ["discord.gg/", "free nitro"],
                                          "presets": ["PROFANITY"]},
                        actions=[{"type": 1}, {"type": 2, "metadata": {"channel_id": text_channels[-1].id}}],
                        enabled=True),
            AutoModRule(id=self._id(), name="Menciones masivas", trigger_type=5,
                        trigger_metadata={"mention_total_limit": 6},
                        actions=[{"type": 1}, {"type": 3, "metadata": {"duration_seconds": 600}}],
                        enabled=True, exempt_roles=[admin_role.id]),
        ]
        for index, (action, target, reason) in enumerate([
            (30, "Nuevo rol Miembro", None), (10, "Canal general", None),
            (22, "cuenta_retirada_1", "Spam masivo en #general"),
            (25, "ana", "Roles actualizados"), (11, "Canal reglas", "Actualizar normas"),
            (23, "cuenta_retirada_2", "Apelación aceptada"),
            (40, "evento-arte-2026", None), (72, "Mensaje en #memes", "Contenido duplicado"),
            (31, "Rol Artista", "Nuevo color"), (144, "Mensaje en #general", "Marcado por automod"),
            (14, "Canal privado", None), (20, "usuario_931", "Incumplimiento de normas"),
        ]):
            state.audit.append(AuditEntry(
                id=self._id(), action_type=action, user_id=self.me.id if index % 3 else "710000000000100000",
                target_id=target, reason=reason,
                created_at=datetime.now(timezone.utc) - timedelta(hours=index * 9 + 1),
                actor=self.me if index % 3 else state.members[3].user,
            ))

        self._states[guild_id] = state

    # ------------------------------------------------------------------ #
    # Sesión y servidores
    # ------------------------------------------------------------------ #
    def login(self) -> User:
        return self.me

    @property
    def bot_invite_url(self) -> None:
        return None

    def validate_token(self) -> User:
        return self.me

    def ping(self) -> float:
        return 18.0

    def list_guilds(self) -> list[GuildSummary]:
        summaries = []
        for state in self._states.values():
            guild = state.guild
            assert guild is not None
            owner = guild.owner_id == self.me.id
            admin = any(r.permissions & 8 for r in guild.roles if r.id in
                        next((m.roles for m in state.members if m.user.id == self.me.id), []))
            summaries.append(GuildSummary(
                id=guild.id, name=guild.name, icon=guild.icon, owner=owner,
                permissions=-1 if owner else (8 if admin else MOD_PERMS),
                features=guild.features, member_count=guild.member_count,
            ))
        return sorted(summaries, key=lambda g: g.name.lower())

    def get_guild(self, guild_id: str) -> Guild:
        guild = self._state(guild_id).guild
        assert guild is not None
        return guild

    def update_guild(self, guild_id: str, fields: dict, reason: str | None = None) -> Guild:
        state = self._state(guild_id)
        guild = state.guild
        assert guild is not None
        for key, value in fields.items():
            if key in {"icon", "banner"} and isinstance(value, str) and value.startswith("data:"):
                continue  # las imágenes demo no se renderizan
            if hasattr(guild, key):
                setattr(guild, key, value)
        self._audit(state, 1, reason=reason)
        return guild

    def leave_guild(self, guild_id: str) -> None:
        self._states.pop(str(guild_id), None)

    def get_member(self, guild_id: str, user_id: str) -> Member:
        return self._member(self._state(guild_id), user_id)

    def get_my_member(self, guild_id: str) -> Member:
        return self._member(self._state(guild_id), self.me.id)

    # ------------------------------------------------------------------ #
    # Canales
    # ------------------------------------------------------------------ #
    def list_channels(self, guild_id: str) -> list[Channel]:
        channels = list(self._state(guild_id).channels)
        return sorted(channels, key=lambda c: (c.position, int(c.id)))

    def create_channel(self, guild_id: str, fields: dict, reason: str | None = None) -> Channel:
        state = self._state(guild_id)
        channel = Channel(
            id=self._id(), type=int(fields.get("type") or 0), name=fields.get("name") or "nuevo-canal",
            parent_id=fields.get("parent_id"), topic=fields.get("topic"),
            nsfw=bool(fields.get("nsfw")), rate_limit_per_user=int(fields.get("rate_limit_per_user") or 0),
            position=int(fields.get("position") or len(state.channels)), guild_id=guild_id,
            user_limit=int(fields.get("user_limit") or 0),
            default_auto_archive_duration=int(
                fields.get("default_auto_archive_duration") or 1440),
        )
        for overwrite in fields.get("permission_overwrites") or []:
            channel.permission_overwrites.append(PermissionOverwrite(
                id=str(overwrite.get("id")), type=int(overwrite.get("type") or 0),
                allow=bits(overwrite.get("allow")), deny=bits(overwrite.get("deny"))))
        state.channels.append(channel)
        state.messages[channel.id] = []
        self._audit(state, 10, target_id=channel.id)
        return channel

    def update_channel(self, channel_id: str, fields: dict, reason: str | None = None) -> Channel:
        for state in self._states.values():
            for channel in state.channels:
                if channel.id == str(channel_id):
                    for key, value in fields.items():
                        if key == "permission_overwrites":
                            channel.permission_overwrites = [
                                PermissionOverwrite(id=str(o.get("id")), type=int(o.get("type") or 0),
                                                    allow=bits(o.get("allow")), deny=bits(o.get("deny")))
                                for o in value
                            ]
                        elif hasattr(channel, key):
                            setattr(channel, key, value)
                    self._audit(state, 11, target_id=channel.id, reason=reason)
                    return channel
        raise DiscordError("El canal no existe.", status=404)

    def delete_channel(self, channel_id: str, reason: str | None = None) -> None:
        for state in self._states.values():
            for channel in list(state.channels):
                if channel.id == str(channel_id):
                    state.channels.remove(channel)
                    state.messages.pop(channel.id, None)
                    self._audit(state, 12, target_id=channel.id, reason=reason)
                    return
        raise DiscordError("El canal no existe.", status=404)

    def reorder_channels(self, guild_id: str, positions: list[dict]) -> None:
        state = self._state(guild_id)
        index = {str(item["id"]): item for item in positions}
        for channel in state.channels:
            data = index.get(channel.id)
            if data:
                channel.position = int(data.get("position", channel.position))
                if "parent_id" in data:
                    channel.parent_id = data["parent_id"]

    # ------------------------------------------------------------------ #
    # Roles
    # ------------------------------------------------------------------ #
    def list_roles(self, guild_id: str) -> list[Role]:
        guild = self._state(guild_id).guild
        assert guild is not None
        return sorted(guild.roles, key=lambda role: role.position, reverse=True)

    def create_role(self, guild_id: str, fields: dict, reason: str | None = None) -> Role:
        state = self._state(guild_id)
        guild = state.guild
        assert guild is not None
        role = Role(
            id=self._id(), name=str(fields.get("name") or "nuevo rol"),
            color=int(fields.get("color") or 0), hoist=bool(fields.get("hoist")),
            position=max((r.position for r in guild.roles), default=0) + 1,
            permissions=bits(fields.get("permissions")), mentionable=bool(fields.get("mentionable")),
        )
        guild.roles.append(role)
        self._audit(state, 30, target_id=role.id)
        return role

    def update_role(self, guild_id: str, role_id: str, fields: dict,
                    reason: str | None = None) -> Role:
        state = self._state(guild_id)
        guild = state.guild
        assert guild is not None
        for role in guild.roles:
            if role.id == str(role_id):
                for key, value in fields.items():
                    if key == "permissions":
                        role.permissions = bits(value)
                    elif hasattr(role, key):
                        setattr(role, key, value)
                self._audit(state, 31, target_id=role.id, reason=reason)
                return role
        raise DiscordError("El rol no existe.", status=404)

    def delete_role(self, guild_id: str, role_id: str, reason: str | None = None) -> None:
        state = self._state(guild_id)
        guild = state.guild
        assert guild is not None
        role = next((r for r in guild.roles if r.id == str(role_id)), None)
        if role is None:
            raise DiscordError("El rol no existe.", status=404)
        guild.roles.remove(role)
        for member in state.members:
            if role.id in member.roles:
                member.roles.remove(role.id)
        self._audit(state, 32, target_id=role.id, reason=reason)

    def reorder_roles(self, guild_id: str, positions: list[dict]) -> None:
        state = self._state(guild_id)
        guild = state.guild
        assert guild is not None
        index = {str(item["id"]): int(item.get("position", 0)) for item in positions}
        for role in guild.roles:
            if role.id in index:
                role.position = index[role.id]

    # ------------------------------------------------------------------ #
    # Miembros
    # ------------------------------------------------------------------ #
    def list_members(self, guild_id: str, limit: int = 100, after: str | None = None) -> list[Member]:
        members = sorted(self._state(guild_id).members, key=lambda m: int(m.user.id))
        if after:
            members = [m for m in members if int(m.user.id) > int(after)]
        return members[: max(1, min(limit, 1000))]

    def search_members(self, guild_id: str, query: str, limit: int = 100) -> list[Member]:
        needle = (query or "").strip().lower()
        if not needle:
            return []
        results = [m for m in self._state(guild_id).members
                   if needle in m.user.username.lower() or needle in (m.nick or "").lower()
                   or needle in m.user.display_name.lower()]
        return results[:limit]

    def update_member(self, guild_id: str, user_id: str, fields: dict,
                      reason: str | None = None) -> None:
        state = self._state(guild_id)
        member = self._member(state, user_id)
        if "nick" in fields:
            member.nick = fields["nick"] or None
        if "roles" in fields:
            member.roles = [str(r) for r in fields["roles"]]
        if "communication_disabled_until" in fields:
            member.communication_disabled_until = parse_ts(fields["communication_disabled_until"])
        for flag in ("mute", "deaf"):
            if flag in fields:
                setattr(member, flag, bool(fields[flag]))
        self._audit(state, 24, target_id=member.user.id, reason=reason)

    def modify_voice_state(self, guild_id: str, user_id: str,
                           channel_id: str | None = None,
                           suppress: bool | None = None) -> None:
        return None

    def kick_member(self, guild_id: str, user_id: str, reason: str | None = None) -> None:
        state = self._state(guild_id)
        member = self._member(state, user_id)
        state.members.remove(member)
        self._audit(state, 20, target_id=member.user.id, reason=reason)

    def ban_member(self, guild_id: str, user_id: str, delete_message_seconds: int = 0,
                   reason: str | None = None) -> None:
        state = self._state(guild_id)
        user = next((m.user for m in state.members if m.user.id == str(user_id)), None) or User(
            id=str(user_id), username=f"usuario_{user_id}")
        state.members = [m for m in state.members if m.user.id != str(user_id)]
        state.bans.append(Ban(user=user, reason=reason))
        self._audit(state, 22, target_id=str(user_id), reason=reason)

    def unban_member(self, guild_id: str, user_id: str, reason: str | None = None) -> None:
        state = self._state(guild_id)
        state.bans = [b for b in state.bans if b.user.id != str(user_id)]
        self._audit(state, 23, target_id=str(user_id), reason=reason)

    def list_bans(self, guild_id: str, limit: int = 1000, after: str | None = None) -> list[Ban]:
        bans = self._state(guild_id).bans
        if after:
            bans = [b for b in bans if int(b.user.id) > int(after)]
        return bans[: max(1, min(limit, 1000))]

    # ------------------------------------------------------------------ #
    # Mensajes
    # ------------------------------------------------------------------ #
    def _channel_messages(self, channel_id: str) -> list[Message]:
        for state in self._states.values():
            if channel_id in state.messages:
                return state.messages[channel_id]
        raise DiscordError("El canal no existe.", status=404)

    def list_messages(self, channel_id: str, limit: int = 50,
                      before: str | None = None, after: str | None = None) -> list[Message]:
        messages = sorted(self._channel_messages(channel_id), key=lambda m: int(m.id), reverse=True)
        if before:
            messages = [m for m in messages if int(m.id) < int(before)]
        if after:
            messages = [m for m in messages if int(m.id) > int(after)]
        return messages[: max(1, min(limit, 100))]

    def delete_message(self, channel_id: str, message_id: str, reason: str | None = None) -> None:
        messages = self._channel_messages(channel_id)
        keep = [m for m in messages if m.id != str(message_id)]
        if len(keep) == len(messages):
            raise DiscordError("El mensaje no existe.", status=404)
        messages[:] = keep

    def bulk_delete_messages(self, channel_id: str, message_ids: Iterable[str]) -> int:
        ids = {str(m) for m in message_ids}
        messages = self._channel_messages(channel_id)
        messages[:] = [m for m in messages if m.id not in ids]
        return len(ids)

    def purge_messages(self, channel_id: str, message_ids: Iterable[str]) -> tuple[int, int]:
        return (self.bulk_delete_messages(channel_id, message_ids), 0)

    def pin_message(self, channel_id: str, message_id: str) -> None:
        for message in self._channel_messages(channel_id):
            if message.id == str(message_id):
                message.pinned = True
                return
        raise DiscordError("El mensaje no existe.", status=404)

    def unpin_message(self, channel_id: str, message_id: str) -> None:
        for message in self._channel_messages(channel_id):
            if message.id == str(message_id):
                message.pinned = False
                return
        raise DiscordError("El mensaje no existe.", status=404)

    def send_message(self, channel_id: str, content: str) -> Message:
        if not content.strip():
            raise DiscordError("El mensaje no puede estar vacío.", status=400)
        messages = self._channel_messages(channel_id)
        message = Message(id=self._id(), content=content, author=self.me,
                          timestamp=datetime.now(timezone.utc))
        messages.append(message)
        return message

    def create_dm(self, user_id: str) -> str:
        channel_id = f"dm-{user_id}"
        for state in self._states.values():
            state.messages.setdefault(channel_id, [])
        return channel_id

    # ------------------------------------------------------------------ #
    # Invitaciones
    # ------------------------------------------------------------------ #
    def list_guild_invites(self, guild_id: str) -> list[Invite]:
        return list(self._state(guild_id).invites)

    def create_invite(self, channel_id: str, max_age: int = 86400, max_uses: int = 0,
                      temporary: bool = False, reason: str | None = None) -> Invite:
        for state in self._states.values():
            channel = next((c for c in state.channels if c.id == str(channel_id)), None)
            if channel is not None:
                invite = Invite(code=f"demo-{self._id()[-6:]}", max_uses=max_uses, max_age=max_age,
                                temporary=temporary, created_at=datetime.now(timezone.utc),
                                inviter=self.me, channel_id=channel.id, channel_name=channel.display_name)
                state.invites.append(invite)
                self._audit(state, 40, target_id=invite.code)
                return invite
        raise DiscordError("El canal no existe.", status=404)

    def delete_invite(self, code: str, reason: str | None = None) -> None:
        for state in self._states.values():
            for invite in list(state.invites):
                if invite.code == code:
                    state.invites.remove(invite)
                    self._audit(state, 42, target_id=code, reason=reason)
                    return
        raise DiscordError("La invitación no existe.", status=404)

    def list_channel_followers(self, channel_id: str) -> list[dict]:
        return []

    # ------------------------------------------------------------------ #
    # Auditoría
    # ------------------------------------------------------------------ #
    def list_audit_logs(self, guild_id: str, limit: int = 50, before: str | None = None,
                        action_type: int | None = None,
                        user_id: str | None = None) -> list[AuditEntry]:
        entries = list(self._state(guild_id).audit)
        if before:
            entries = [e for e in entries if int(e.id) < int(before)]
        if action_type:
            entries = [e for e in entries if e.action_type == int(action_type)]
        if user_id:
            entries = [e for e in entries if str(e.user_id) == str(user_id)]
        return entries[: max(1, min(limit, 100))]

    # ------------------------------------------------------------------ #
    # Emojis, webhooks, automod
    # ------------------------------------------------------------------ #
    def list_emojis(self, guild_id: str) -> list[Emoji]:
        return list(self._state(guild_id).emojis)

    def list_active_threads(self, channel_id: str) -> list[Channel]:
        return []

    def create_emoji(self, guild_id: str, name: str, image_data_uri: str,
                     roles: list[str] | None = None, reason: str | None = None) -> Emoji:
        state = self._state(guild_id)
        emoji = Emoji(id=self._id(), name=name, roles=roles or [])
        state.emojis.append(emoji)
        self._audit(state, 60, target_id=emoji.id)
        return emoji

    def update_emoji(self, guild_id: str, emoji_id: str, fields: dict,
                     reason: str | None = None) -> Emoji:
        state = self._state(guild_id)
        emoji = next((item for item in state.emojis if item.id == str(emoji_id)), None)
        if emoji is None:
            from .errors import DiscordError
            raise DiscordError("El emoji no existe.", status=404)
        if "name" in fields:
            emoji.name = str(fields["name"])
        if "roles" in fields:
            emoji.roles = [str(role) for role in (fields.get("roles") or [])]
        self._audit(state, 61, target_id=emoji.id, reason=reason)
        return emoji

    def delete_emoji(self, guild_id: str, emoji_id: str, reason: str | None = None) -> None:
        state = self._state(guild_id)
        state.emojis = [e for e in state.emojis if e.id != str(emoji_id)]
        self._audit(state, 62, target_id=str(emoji_id), reason=reason)

    def list_webhooks(self, guild_id: str) -> list[Webhook]:
        return list(self._state(guild_id).webhooks)

    def get_webhook(self, webhook_id: str) -> Webhook:
        for state in self._states.values():
            for webhook in state.webhooks:
                if webhook.id == str(webhook_id):
                    return webhook
        raise DiscordError("El webhook no existe.", status=404)

    def create_webhook(self, channel_id: str, name: str, reason: str | None = None) -> Webhook:
        for state in self._states.values():
            if any(c.id == str(channel_id) for c in state.channels):
                webhook = Webhook(id=self._id(), name=name, channel_id=str(channel_id),
                                  token=f"demo-{self._id()}")
                state.webhooks.append(webhook)
                self._audit(state, 50, target_id=webhook.id)
                return webhook
        raise DiscordError("El canal no existe.", status=404)

    def delete_webhook(self, webhook_id: str, reason: str | None = None) -> None:
        for state in self._states.values():
            for webhook in list(state.webhooks):
                if webhook.id == str(webhook_id):
                    state.webhooks.remove(webhook)
                    self._audit(state, 52, target_id=webhook_id, reason=reason)
                    return
        raise DiscordError("El webhook no existe.", status=404)

    def list_automod_rules(self, guild_id: str) -> list[AutoModRule]:
        return list(self._state(guild_id).rules)

    def create_automod_rule(self, guild_id: str, body: dict,
                            reason: str | None = None) -> AutoModRule:
        state = self._state(guild_id)
        rule = AutoModRule(
            id=self._id(), name=str(body.get("name") or "Regla"),
            event_type=int(body.get("event_type") or 1),
            trigger_type=int(body.get("trigger_type") or 1),
            trigger_metadata=dict(body.get("trigger_metadata") or {}),
            actions=list(body.get("actions") or []),
            enabled=bool(body.get("enabled", True)),
            exempt_roles=list(body.get("exempt_roles") or []),
            exempt_channels=list(body.get("exempt_channels") or []),
        )
        state.rules.append(rule)
        self._audit(state, 140, target_id=rule.id)
        return rule

    def update_automod_rule(self, guild_id: str, rule_id: str, body: dict,
                            reason: str | None = None) -> AutoModRule:
        state = self._state(guild_id)
        for rule in state.rules:
            if rule.id == str(rule_id):
                for key, value in body.items():
                    if hasattr(rule, key):
                        setattr(rule, key, value)
                self._audit(state, 141, target_id=rule.id, reason=reason)
                return rule
        raise DiscordError("La regla no existe.", status=404)

    def delete_automod_rule(self, guild_id: str, rule_id: str, reason: str | None = None) -> None:
        state = self._state(guild_id)
        state.rules = [r for r in state.rules if r.id != str(rule_id)]
        self._audit(state, 142, target_id=str(rule_id), reason=reason)
