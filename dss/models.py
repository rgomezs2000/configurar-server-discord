"""Modelos ligeros sobre las respuestas de la API de Discord.

Se usan dataclasses simples (sin dependencias) para que las vistas trabajen con
atributos legibles en lugar de diccionarios anidados.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .constants import (CHANNEL_GLYPHS, CHANNEL_TYPES, CATEGORY_TYPE,
                        TEXT_CHANNEL_TYPES, THREAD_TYPES, VOICE_CHANNEL_TYPES)

DISCORD_EPOCH_MS = 1420070400000


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #

def parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone()
    except (ValueError, TypeError):
        return None


def fmt_date(value: Any) -> str:
    dt = value if isinstance(value, datetime) else parse_ts(value)
    if dt is not None and dt.tzinfo is not None:
        dt = dt.astimezone()
    return dt.strftime("%d/%m/%Y") if dt else "—"


def fmt_datetime(value: Any) -> str:
    dt = value if isinstance(value, datetime) else parse_ts(value)
    if dt is not None and dt.tzinfo is not None:
        dt = dt.astimezone()
    return dt.strftime("%d/%m/%Y %H:%M") if dt else "—"


def fmt_relative(value: Any) -> str:
    dt = value if isinstance(value, datetime) else parse_ts(value)
    if not dt:
        return "—"
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    delta = datetime.now(timezone.utc) - dt
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return fmt_datetime(dt)
    if seconds < 60:
        return "hace unos segundos"
    if seconds < 3600:
        return f"hace {seconds // 60} min"
    if seconds < 86400:
        return f"hace {seconds // 3600} h"
    if seconds < 2592000:
        return f"hace {seconds // 86400} días"
    return fmt_date(dt)


def snowflake_time(snowflake: str | int | None) -> datetime | None:
    try:
        value = int(snowflake or 0)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return datetime.fromtimestamp(((value >> 22) + DISCORD_EPOCH_MS) / 1000, tz=timezone.utc).astimezone()


def bits(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value), 10)
    except (TypeError, ValueError):
        return 0


def color_to_hex(color: int | None, default: str = "#99aab5") -> str:
    if not color:
        return default
    return f"#{color:06x}"


def duration_label(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    if seconds < 86400:
        return f"{seconds // 3600} h"
    return f"{seconds // 86400} d"


# --------------------------------------------------------------------------- #
# Modelos
# --------------------------------------------------------------------------- #

@dataclass(slots=True)
class User:
    id: str
    username: str = ""
    discriminator: str = "0"
    global_name: str | None = None
    avatar: str | None = None
    bot: bool = False
    system: bool = False
    premium_type: int = 0
    created_at: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> "User":
        data = data or {}
        return cls(
            id=str(data.get("id", "")),
            username=str(data.get("username", "")),
            discriminator=str(data.get("discriminator", "0")),
            global_name=data.get("global_name"),
            avatar=data.get("avatar"),
            bot=bool(data.get("bot")),
            system=bool(data.get("system")),
            premium_type=int(data.get("premium_type") or 0),
            created_at=parse_ts(data.get("created_at")),
        )

    @property
    def display_name(self) -> str:
        return self.global_name or self.username or "Desconocido"

    @property
    def has_nitro(self) -> bool:
        return not self.bot and self.premium_type > 0

    @property
    def nitro_label(self) -> str:
        return {1: "Nitro Classic", 2: "Nitro", 3: "Nitro Basic"}.get(
            self.premium_type, "Sin Nitro")

    @property
    def tag(self) -> str:
        if self.discriminator and self.discriminator != "0":
            return f"{self.username}#{self.discriminator}"
        return f"@{self.username}"

    @property
    def initials(self) -> str:
        source = (self.display_name or "?").strip()
        parts = [p for p in source.replace("_", " ").replace(".", " ").split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[1][0]).upper()

    @property
    def avatar_url(self) -> str:
        if self.avatar:
            ext = "gif" if self.avatar.startswith("a_") else "png"
            return f"https://cdn.discordapp.com/avatars/{self.id}/{self.avatar}.{ext}?size=128"
        if self.discriminator and self.discriminator != "0":
            index = int(self.discriminator) % 5
        else:
            index = (int(self.id or 0) >> 22) % 6 if self.id else 0
        return f"https://cdn.discordapp.com/embed/avatars/{index}.png"


@dataclass(slots=True)
class GuildSummary:
    id: str
    name: str = "Servidor"
    icon: str | None = None
    owner: bool = False
    permissions: int = 0
    features: list[str] = field(default_factory=list)
    member_count: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "GuildSummary":
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name") or "Servidor"),
            icon=data.get("icon"),
            owner=bool(data.get("owner")),
            permissions=bits(data.get("permissions")),
            features=list(data.get("features") or []),
            member_count=int(data.get("approximate_member_count") or data.get("member_count") or 0),
        )

    @property
    def is_admin(self) -> bool:
        return bool(self.permissions & (1 << 3))

    @property
    def can_manage(self) -> bool:
        """True si la cuenta es propietaria o tiene permisos de administración."""
        return (self.owner or self.permissions == -1
                or bool(self.permissions & ((1 << 3) | (1 << 5))))

    @property
    def is_community(self) -> bool:
        return "COMMUNITY" in self.features

    @property
    def access_label(self) -> str:
        """Nivel de acceso de la cuenta en este servidor, para mostrarlo en la UI."""
        if self.owner:
            return "Propietario"
        permissions = self.permissions
        if permissions == -1 or permissions & (1 << 3):
            return "Administrador"
        if permissions & (1 << 5):
            return "Gestiona el servidor"
        if permissions & ((1 << 1) | (1 << 2) | (1 << 7) | (1 << 13) | (1 << 40)):
            return "Moderador"
        return "Miembro"

    @property
    def icon_url(self) -> str | None:
        if not self.icon:
            return None
        ext = "gif" if str(self.icon).startswith("a_") else "png"
        return f"https://cdn.discordapp.com/icons/{self.id}/{self.icon}.{ext}?size=128"

    @property
    def initials(self) -> str:
        parts = [p for p in (self.name or "?").split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[1][0]).upper()


@dataclass(slots=True)
class Role:
    id: str
    name: str = "rol"
    color: int = 0
    hoist: bool = False
    position: int = 0
    permissions: int = 0
    managed: bool = False
    mentionable: bool = False
    icon: str | None = None
    unicode_emoji: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "Role":
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "rol")),
            color=int(data.get("color") or 0),
            hoist=bool(data.get("hoist")),
            position=int(data.get("position") or 0),
            permissions=bits(data.get("permissions")),
            managed=bool(data.get("managed")),
            mentionable=bool(data.get("mentionable")),
            icon=data.get("icon"),
            unicode_emoji=data.get("unicode_emoji"),
        )

    @property
    def is_everyone(self) -> bool:
        return self.id == "@everyone" or self.name == "@everyone"

    @property
    def color_hex(self) -> str:
        return color_to_hex(self.color)

    @property
    def is_admin(self) -> bool:
        return bool(self.permissions & (1 << 3))


@dataclass(slots=True)
class Guild:
    id: str
    name: str = "Servidor"
    icon: str | None = None
    banner: str | None = None
    description: str | None = None
    owner_id: str = ""
    member_count: int = 0
    presence_count: int = 0
    verification_level: int = 0
    explicit_content_filter: int = 0
    afk_channel_id: str | None = None
    afk_timeout: int = 300
    system_channel_id: str | None = None
    rules_channel_id: str | None = None
    public_updates_channel_id: str | None = None
    preferred_locale: str = "es-ES"
    premium_tier: int = 0
    premium_subscription_count: int = 0
    nsfw_level: int = 0
    mfa_level: int = 0
    default_message_notifications: int = 1
    features: list[str] = field(default_factory=list)
    roles: list[Role] = field(default_factory=list)
    emoji_count: int = 0
    sticker_count: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "Guild":
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name") or "Servidor"),
            icon=data.get("icon"),
            banner=data.get("banner"),
            description=data.get("description"),
            owner_id=str(data.get("owner_id") or ""),
            member_count=int(data.get("approximate_member_count") or data.get("member_count") or 0),
            presence_count=int(data.get("approximate_presence_count") or data.get("presence_count") or 0),
            verification_level=int(data.get("verification_level") or 0),
            explicit_content_filter=int(data.get("explicit_content_filter") or 0),
            afk_channel_id=data.get("afk_channel_id"),
            afk_timeout=int(data.get("afk_timeout") or 300),
            system_channel_id=data.get("system_channel_id"),
            rules_channel_id=data.get("rules_channel_id"),
            public_updates_channel_id=data.get("public_updates_channel_id"),
            preferred_locale=str(data.get("preferred_locale") or "es-ES"),
            premium_tier=int(data.get("premium_tier") or 0),
            premium_subscription_count=int(data.get("premium_subscription_count") or 0),
            nsfw_level=int(data.get("nsfw_level") or 0),
            mfa_level=int(data.get("mfa_level") or 0),
            default_message_notifications=int(data.get("default_message_notifications") or 0),
            features=list(data.get("features") or []),
            roles=[Role.from_dict(r) for r in (data.get("roles") or [])],
            emoji_count=len(data.get("emojis") or []),
            sticker_count=len(data.get("stickers") or []),
        )

    @property
    def icon_url(self) -> str | None:
        if not self.icon:
            return None
        ext = "gif" if str(self.icon).startswith("a_") else "png"
        return f"https://cdn.discordapp.com/icons/{self.id}/{self.icon}.{ext}?size=256"

    @property
    def banner_url(self) -> str | None:
        if not self.banner:
            return None
        ext = "gif" if str(self.banner).startswith("a_") else "png"
        return f"https://cdn.discordapp.com/banners/{self.id}/{self.banner}.{ext}?size=600"

    @property
    def initials(self) -> str:
        parts = [p for p in (self.name or "?").split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[1][0]).upper()

    def sorted_roles(self) -> list[Role]:
        return sorted(self.roles, key=lambda r: r.position, reverse=True)

    def role_by_id(self, role_id: str) -> Role | None:
        return next((r for r in self.roles if r.id == role_id), None)

    @property
    def everyone_role(self) -> Role | None:
        return next((r for r in self.roles if r.is_everyone), None)

    # -- comunidad y mejoras ------------------------------------------------ #
    @property
    def is_community(self) -> bool:
        return "COMMUNITY" in self.features

    @property
    def boost_level(self) -> int:
        return max(0, min(3, self.premium_tier))

    @property
    def max_emoji_slots(self) -> int:
        return {0: 50, 1: 100, 2: 150, 3: 250}[self.boost_level]

    @property
    def max_sticker_slots(self) -> int:
        return {0: 5, 1: 15, 2: 30, 3: 60}[self.boost_level]

    @property
    def max_voice_bitrate(self) -> int:
        return {0: 96000, 1: 128000, 2: 256000, 3: 384000}[self.boost_level]

    @property
    def max_upload_mb(self) -> int:
        return {0: 25, 1: 25, 2: 50, 3: 100}[self.boost_level]

    @property
    def can_use_animated_icon(self) -> bool:
        return self.boost_level >= 1

    @property
    def can_use_banner(self) -> bool:
        return self.boost_level >= 2

    @property
    def can_use_vanity_url(self) -> bool:
        return self.boost_level >= 3

    @property
    def boosts_to_next_level(self) -> int:
        requirements = {1: 2, 2: 7, 3: 14}
        if self.boost_level >= 3:
            return 0
        target = requirements[self.boost_level + 1]
        return max(0, target - max(0, self.premium_subscription_count))


@dataclass(slots=True)
class PermissionOverwrite:
    id: str
    type: int = 0  # 0 rol, 1 miembro
    allow: int = 0
    deny: int = 0


@dataclass(slots=True)
class Channel:
    id: str
    type: int = 0
    name: str | None = ""
    topic: str | None = None
    position: int = 0
    parent_id: str | None = None
    nsfw: bool = False
    rate_limit_per_user: int = 0
    bitrate: int = 64000
    user_limit: int = 0
    guild_id: str | None = None
    last_message_id: str | None = None
    permission_overwrites: list[PermissionOverwrite] = field(default_factory=list)
    flags: int = 0
    default_auto_archive_duration: int = 1440

    @classmethod
    def from_dict(cls, data: dict) -> "Channel":
        return cls(
            id=str(data.get("id", "")),
            type=int(data.get("type") or 0),
            name=data.get("name"),
            topic=data.get("topic"),
            position=int(data.get("position") or 0),
            parent_id=data.get("parent_id"),
            nsfw=bool(data.get("nsfw")),
            rate_limit_per_user=int(data.get("rate_limit_per_user") or 0),
            bitrate=int(data.get("bitrate") or 64000),
            user_limit=int(data.get("user_limit") or 0),
            guild_id=data.get("guild_id"),
            last_message_id=data.get("last_message_id"),
            permission_overwrites=[
                PermissionOverwrite(id=str(o.get("id", "")), type=int(o.get("type") or 0),
                                   allow=bits(o.get("allow")), deny=bits(o.get("deny")))
                for o in (data.get("permission_overwrites") or [])
            ],
            flags=int(data.get("flags") or 0),
            default_auto_archive_duration=int(
                data.get("default_auto_archive_duration") or 1440),
        )

    @property
    def kind_label(self) -> str:
        return CHANNEL_TYPES.get(self.type, f"Tipo {self.type}")

    @property
    def glyph(self) -> str:
        return CHANNEL_GLYPHS.get(self.type, "#")

    @property
    def is_text(self) -> bool:
        return self.type in TEXT_CHANNEL_TYPES

    @property
    def is_voice(self) -> bool:
        return self.type in VOICE_CHANNEL_TYPES

    @property
    def is_category(self) -> bool:
        return self.type == CATEGORY_TYPE

    @property
    def is_thread(self) -> bool:
        return self.type in THREAD_TYPES

    @property
    def display_name(self) -> str:
        return self.name or "sin-nombre"


@dataclass(slots=True)
class Member:
    user: User
    nick: str | None = None
    roles: list[str] = field(default_factory=list)
    joined_at: datetime | None = None
    communication_disabled_until: datetime | None = None
    premium_since: datetime | None = None
    pending: bool = False
    mute: bool = False
    deaf: bool = False
    flags: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "Member":
        return cls(
            user=User.from_dict(data.get("user")),
            nick=data.get("nick"),
            roles=[str(r) for r in (data.get("roles") or [])],
            joined_at=parse_ts(data.get("joined_at")),
            communication_disabled_until=parse_ts(data.get("communication_disabled_until")),
            premium_since=parse_ts(data.get("premium_since")),
            pending=bool(data.get("pending")),
            mute=bool(data.get("mute")),
            deaf=bool(data.get("deaf")),
            flags=int(data.get("flags") or 0),
        )

    @property
    def display_name(self) -> str:
        return self.nick or self.user.display_name

    @property
    def is_timed_out(self) -> bool:
        if not self.communication_disabled_until:
            return False
        return self.communication_disabled_until > datetime.now(timezone.utc)

    @property
    def timeout_label(self) -> str:
        if not self.is_timed_out or not self.communication_disabled_until:
            return ""
        remaining = self.communication_disabled_until - datetime.now(timezone.utc)
        return f"Aislado {duration_label(remaining.total_seconds())} restantes"


@dataclass(slots=True)
class Ban:
    user: User
    reason: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "Ban":
        return cls(user=User.from_dict(data.get("user")), reason=data.get("reason"))


@dataclass(slots=True)
class Invite:
    code: str
    uses: int = 0
    max_uses: int = 0
    max_age: int = 0
    temporary: bool = False
    created_at: datetime | None = None
    expires_at: datetime | None = None
    inviter: User | None = None
    channel_id: str = ""
    channel_name: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Invite":
        channel = data.get("channel") or {}
        return cls(
            code=str(data.get("code", "")),
            uses=int(data.get("uses") or 0),
            max_uses=int(data.get("max_uses") or 0),
            max_age=int(data.get("max_age") or 0),
            temporary=bool(data.get("temporary")),
            created_at=parse_ts(data.get("created_at")),
            expires_at=parse_ts(data.get("expires_at")),
            inviter=User.from_dict(data.get("inviter")) if data.get("inviter") else None,
            channel_id=str(channel.get("id") or data.get("channel_id") or ""),
            channel_name=str(channel.get("name") or ""),
        )

    @property
    def uses_label(self) -> str:
        return f"{self.uses}/{self.max_uses}" if self.max_uses else f"{self.uses}/∞"

    @property
    def expires_label(self) -> str:
        if not self.expires_at:
            return "Nunca"
        return fmt_datetime(self.expires_at)


@dataclass(slots=True)
class Webhook:
    id: str
    name: str = ""
    channel_id: str = ""
    avatar: str | None = None
    token: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "Webhook":
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name") or ""),
            channel_id=str(data.get("channel_id") or ""),
            avatar=data.get("avatar"),
            token=data.get("token"),
        )

    @property
    def url(self) -> str:
        return f"https://discord.com/api/webhooks/{self.id}/{self.token}" if self.token else ""


@dataclass(slots=True)
class Emoji:
    id: str
    name: str = ""
    animated: bool = False
    available: bool = True
    roles: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "Emoji":
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name") or ""),
            animated=bool(data.get("animated")),
            available=bool(data.get("available", True)),
            roles=[str(r) for r in (data.get("roles") or [])],
        )

    @property
    def image_url(self) -> str:
        ext = "gif" if self.animated else "png"
        return f"https://cdn.discordapp.com/emojis/{self.id}.{ext}?size=64&quality=lossless"


@dataclass(slots=True)
class AuditEntry:
    id: str
    action_type: int = 0
    user_id: str | None = None
    target_id: str | None = None
    reason: str | None = None
    changes: list[dict] = field(default_factory=list)
    options: dict | None = None
    channel_id: str | None = None
    created_at: datetime | None = None
    actor: User | None = None
    target: User | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "AuditEntry":
        return cls(
            id=str(data.get("id", "")),
            action_type=int(data.get("action_type") or 0),
            user_id=data.get("user_id"),
            target_id=data.get("target_id"),
            reason=data.get("reason"),
            changes=list(data.get("changes") or []),
            options=data.get("options"),
            channel_id=data.get("channel_id"),
            created_at=parse_ts(data.get("created_at")),
            actor=User.from_dict(data["user"]) if data.get("user") else None,
            target=User.from_dict(data["target"]) if isinstance(data.get("target"), dict) else None,
        )

    @property
    def action_label(self) -> str:
        from .constants import audit_action_label
        return audit_action_label(self.action_type)


@dataclass(slots=True)
class AutoModRule:
    id: str
    name: str = ""
    event_type: int = 1
    trigger_type: int = 1
    trigger_metadata: dict = field(default_factory=dict)
    actions: list[dict] = field(default_factory=list)
    enabled: bool = True
    exempt_roles: list[str] = field(default_factory=list)
    exempt_channels: list[str] = field(default_factory=list)
    creator_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "AutoModRule":
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name") or ""),
            event_type=int(data.get("event_type") or 1),
            trigger_type=int(data.get("trigger_type") or 1),
            trigger_metadata=dict(data.get("trigger_metadata") or {}),
            actions=list(data.get("actions") or []),
            enabled=bool(data.get("enabled", True)),
            exempt_roles=[str(r) for r in (data.get("exempt_roles") or [])],
            exempt_channels=[str(c) for c in (data.get("exempt_channels") or [])],
            creator_id=data.get("creator_id"),
        )

    @property
    def trigger_label(self) -> str:
        from .constants import AUTOMOD_TRIGGERS
        return next((label for value, label, _ in AUTOMOD_TRIGGERS if value == self.trigger_type),
                    f"Tipo {self.trigger_type}")

    @property
    def actions_label(self) -> str:
        from .constants import AUTOMOD_ACTION_TYPES
        labels = []
        for action in self.actions:
            action_type = int(action.get("type") or 0)
            label = next((text for value, text in AUTOMOD_ACTION_TYPES if value == action_type),
                         f"Acción {action_type}")
            labels.append(label)
        return " + ".join(labels) if labels else "—"

    @property
    def keywords(self) -> list[str]:
        return list(self.trigger_metadata.get("keyword_filter") or [])

    @property
    def presets(self) -> list[str]:
        return list(self.trigger_metadata.get("presets") or [])

    @property
    def mention_limit(self) -> int:
        return int(self.trigger_metadata.get("mention_total_limit") or 0)


@dataclass(slots=True)
class Attachment:
    id: str = ""
    filename: str = ""
    size: int = 0
    url: str = ""
    content_type: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "Attachment":
        return cls(
            id=str(data.get("id", "")),
            filename=str(data.get("filename") or ""),
            size=int(data.get("size") or 0),
            url=str(data.get("url") or ""),
            content_type=data.get("content_type"),
        )


@dataclass(slots=True)
class Message:
    id: str
    content: str = ""
    author: User = field(default_factory=lambda: User(id=""))
    timestamp: datetime | None = None
    edited_timestamp: datetime | None = None
    pinned: bool = False
    type: int = 0
    attachments: list[Attachment] = field(default_factory=list)
    embeds: list[dict] = field(default_factory=list)
    mentions: list[User] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(
            id=str(data.get("id", "")),
            content=str(data.get("content") or ""),
            author=User.from_dict(data.get("author")),
            timestamp=parse_ts(data.get("timestamp")),
            edited_timestamp=parse_ts(data.get("edited_timestamp")),
            pinned=bool(data.get("pinned")),
            type=int(data.get("type") or 0),
            attachments=[Attachment.from_dict(a) for a in (data.get("attachments") or [])],
            embeds=list(data.get("embeds") or []),
            mentions=[User.from_dict(u) for u in (data.get("mentions") or [])],
        )

    @property
    def preview(self) -> str:
        text = " ".join((self.content or "").split())
        if len(text) > 160:
            text = text[:157] + "…"
        if not text and self.attachments:
            text = "📎 " + ", ".join(a.filename for a in self.attachments[:3])
        if not text and self.embeds:
            text = "🧩 Embed"
        return text or "(sin contenido)"


# --------------------------------------------------------------------------- #
# Permisos
# --------------------------------------------------------------------------- #

def effective_permissions(guild: Guild, member: Member | None, user_id: str,
                          administrator: bool = False) -> int:
    """Calcula los permisos del usuario en el servidor (sin overwrites de canal)."""
    if administrator or (guild.owner_id and guild.owner_id == user_id):
        return -1
    role_ids = set(member.roles if member else [])
    everyone = guild.everyone_role
    result = everyone.permissions if everyone else 0
    for role in guild.roles:
        if role.id in role_ids:
            result |= role.permissions
    return result


def permissions_from_guild_summary(summary: GuildSummary, guild: Guild | None,
                                   member: Member | None, user_id: str) -> int:
    if summary.is_admin or summary.owner:
        return -1
    if guild is not None:
        return effective_permissions(guild, member, user_id)
    return summary.permissions


def has_permission(bits_value: int, bit: int) -> bool:
    return bits_value == -1 or bool(bits_value & (1 << bit))


def permission_names(bits_value: int) -> list[str]:
    from .constants import PERMISSIONS
    return [label for key, bit, _cat, label, _desc in PERMISSIONS
            if bits_value == -1 or bits_value & (1 << bit)]


def channel_permissions(guild: Guild, channel: Channel, member: Member | None,
                        base_permissions: int) -> int:
    """Permisos efectivos en un canal concreto aplicando los overwrites."""
    if base_permissions == -1:
        return -1
    overwrites = {o.id: o for o in channel.permission_overwrites}
    everyone = guild.everyone_role
    if everyone and everyone.id in overwrites:
        ow = overwrites[everyone.id]
        base_permissions = (base_permissions & ~ow.deny) | ow.allow
    allow = deny = 0
    role_ids = set(member.roles if member else [])
    for role in guild.roles:
        if role.id in role_ids and role.id in overwrites:
            allow |= overwrites[role.id].allow
            deny |= overwrites[role.id].deny
    base_permissions = (base_permissions & ~deny) | allow
    if member and member.user.id in overwrites:
        ow = overwrites[member.user.id]
        base_permissions = (base_permissions & ~ow.deny) | ow.allow
    return base_permissions
