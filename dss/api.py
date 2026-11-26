"""Cliente de la API de Discord: una función por operación de administración."""
from __future__ import annotations

from typing import Any, Iterable

from .constants import BOT_RECOMMENDED_PERMISSIONS, BULK_DELETE_MAX
from .errors import DiscordError
from .http import DiscordHTTP
from .models import (AuditEntry, AutoModRule, Ban, Channel, Emoji, Guild,
                     GuildSummary, Invite, Member, Message, Role, User,
                     Webhook, parse_ts)

TOKEN_KINDS = ("bot", "user")


class DiscordClient:
    """Sesión autenticada contra un servidor (o varios) de Discord.

    ``kind`` es ``bot`` (recomendado, cumple los Términos de Servicio) o
    ``user`` (token de cuenta: uso bajo tu responsabilidad).
    """

    def __init__(self, token: str, kind: str = "bot"):
        self.token = token.strip()
        self.kind = kind if kind in TOKEN_KINDS else "bot"
        self.http = DiscordHTTP(self.token, self.kind)
        self.me: User | None = None
        self.application: dict | None = None

    # ------------------------------------------------------------------ #
    # Sesión
    # ------------------------------------------------------------------ #
    def login(self) -> User:
        raw = self.http.get("/users/@me")
        self.me = User.from_dict(raw)
        if self.kind == "bot":
            try:
                self.application = self.http.get("/oauth2/applications/@me")
            except DiscordError:
                self.application = None
        return self.me

    @property
    def bot_invite_url(self) -> str | None:
        return self.invite_url_for_guild()

    def invite_url_for_guild(self, guild_id: str | None = None,
                             permissions: int = BOT_RECOMMENDED_PERMISSIONS) -> str | None:
        if self.kind != "bot" or not self.application:
            return None
        app_id = self.application.get("id")
        if not app_id:
            return None
        url = (f"https://discord.com/oauth2/authorize?client_id={app_id}"
               f"&permissions={permissions}&scope=bot%20applications.commands")
        if guild_id:
            url += f"&guild_id={guild_id}&disable_guild_select=true"
        return url

    def list_guilds(self) -> list[GuildSummary]:
        guilds: list[GuildSummary] = []
        seen: set[str] = set()
        after: str | None = None
        while True:
            params = {"limit": 200, "with_counts": "true"}
            if after:
                params["after"] = after
            batch = self.http.get("/users/@me/guilds", params=params) or []
            fresh = [item for item in batch if str(item.get("id")) not in seen]
            for item in fresh:
                seen.add(str(item.get("id")))
                guilds.append(GuildSummary.from_dict(item))
            # Paginación solo fiable con tokens de bot; se corta si no hay novedades.
            if len(batch) < 200 or not fresh or self.kind == "user":
                break
            after = str(batch[-1].get("id"))
        guilds.sort(key=lambda g: g.name.lower())
        return guilds

    def get_guild(self, guild_id: str) -> Guild:
        raw = self.http.get(f"/guilds/{guild_id}", params={"with_counts": "true"})
        return Guild.from_dict(raw or {})

    def update_guild(self, guild_id: str, fields: dict, reason: str | None = None) -> Guild:
        raw = self.http.patch(f"/guilds/{guild_id}", body=fields, reason=reason)
        return Guild.from_dict(raw or {})

    def leave_guild(self, guild_id: str) -> None:
        self.http.delete(f"/users/@me/guilds/{guild_id}")

    def get_member(self, guild_id: str, user_id: str) -> Member:
        raw = self.http.get(f"/guilds/{guild_id}/members/{user_id}")
        return Member.from_dict(raw or {})

    def get_my_member(self, guild_id: str) -> Member:
        if not self.me:
            self.login()
        return self.get_member(guild_id, self.me.id)  # type: ignore[union-attr]

    # ------------------------------------------------------------------ #
    # Canales
    # ------------------------------------------------------------------ #
    def list_channels(self, guild_id: str) -> list[Channel]:
        raw = self.http.get(f"/guilds/{guild_id}/channels") or []
        channels = [Channel.from_dict(item) for item in raw]
        channels.sort(key=lambda c: (c.position, int(c.id)))
        return channels

    def create_channel(self, guild_id: str, fields: dict, reason: str | None = None) -> Channel:
        raw = self.http.post(f"/guilds/{guild_id}/channels", body=fields, reason=reason)
        return Channel.from_dict(raw or {})

    def update_channel(self, channel_id: str, fields: dict, reason: str | None = None) -> Channel:
        raw = self.http.patch(f"/channels/{channel_id}", body=fields, reason=reason)
        return Channel.from_dict(raw or {})

    def delete_channel(self, channel_id: str, reason: str | None = None) -> None:
        self.http.delete(f"/channels/{channel_id}", reason=reason)

    def reorder_channels(self, guild_id: str, positions: list[dict]) -> None:
        self.http.patch(f"/guilds/{guild_id}/channels", body=positions)

    # ------------------------------------------------------------------ #
    # Roles
    # ------------------------------------------------------------------ #
    def list_roles(self, guild_id: str) -> list[Role]:
        raw = self.http.get(f"/guilds/{guild_id}/roles") or []
        return sorted((Role.from_dict(item) for item in raw),
                      key=lambda r: r.position, reverse=True)

    def create_role(self, guild_id: str, fields: dict, reason: str | None = None) -> Role:
        raw = self.http.post(f"/guilds/{guild_id}/roles", body=fields, reason=reason)
        return Role.from_dict(raw or {})

    def update_role(self, guild_id: str, role_id: str, fields: dict,
                    reason: str | None = None) -> Role:
        raw = self.http.patch(f"/guilds/{guild_id}/roles/{role_id}", body=fields, reason=reason)
        return Role.from_dict(raw or {})

    def delete_role(self, guild_id: str, role_id: str, reason: str | None = None) -> None:
        self.http.delete(f"/guilds/{guild_id}/roles/{role_id}", reason=reason)

    def reorder_roles(self, guild_id: str, positions: list[dict]) -> None:
        self.http.patch(f"/guilds/{guild_id}/roles", body=positions)

    # ------------------------------------------------------------------ #
    # Miembros
    # ------------------------------------------------------------------ #
    def list_members(self, guild_id: str, limit: int = 100, after: str | None = None) -> list[Member]:
        params: dict[str, Any] = {"limit": max(1, min(limit, 1000))}
        if after:
            params["after"] = after
        raw = self.http.get(f"/guilds/{guild_id}/members", params=params) or []
        return [Member.from_dict(item) for item in raw]

    def search_members(self, guild_id: str, query: str, limit: int = 100) -> list[Member]:
        raw = self.http.get(f"/guilds/{guild_id}/members/search",
                            params={"query": query, "limit": min(limit, 1000)}) or []
        return [Member.from_dict(item) for item in raw]

    def update_member(self, guild_id: str, user_id: str, fields: dict,
                      reason: str | None = None) -> None:
        self.http.patch(f"/guilds/{guild_id}/members/{user_id}", body=fields, reason=reason)

    def modify_voice_state(self, guild_id: str, user_id: str,
                           channel_id: str | None = None,
                           suppress: bool | None = None,
                           disconnect: bool = False) -> None:
        body: dict[str, Any] = {}
        if disconnect:
            body["channel_id"] = None
        elif channel_id is not None:
            body["channel_id"] = channel_id
        if suppress is not None:
            body["suppress"] = suppress
        self.http.patch(f"/guilds/{guild_id}/voice-states/{user_id}", body=body)

    def kick_member(self, guild_id: str, user_id: str, reason: str | None = None) -> None:
        self.http.delete(f"/guilds/{guild_id}/members/{user_id}", reason=reason)

    def ban_member(self, guild_id: str, user_id: str, delete_message_seconds: int = 0,
                   reason: str | None = None) -> None:
        body = {"delete_message_seconds": int(delete_message_seconds)}
        self.http.put(f"/guilds/{guild_id}/bans/{user_id}", body=body, reason=reason)

    def unban_member(self, guild_id: str, user_id: str, reason: str | None = None) -> None:
        self.http.delete(f"/guilds/{guild_id}/bans/{user_id}", reason=reason)

    def list_bans(self, guild_id: str, limit: int = 1000, after: str | None = None) -> list[Ban]:
        params: dict[str, Any] = {"limit": max(1, min(limit, 1000))}
        if after:
            params["after"] = after
        raw = self.http.get(f"/guilds/{guild_id}/bans", params=params) or []
        return [Ban.from_dict(item) for item in raw]

    # ------------------------------------------------------------------ #
    # Mensajes
    # ------------------------------------------------------------------ #
    def list_messages(self, channel_id: str, limit: int = 50,
                      before: str | None = None, after: str | None = None) -> list[Message]:
        params: dict[str, Any] = {"limit": max(1, min(limit, 100))}
        if before:
            params["before"] = before
        if after:
            params["after"] = after
        raw = self.http.get(f"/channels/{channel_id}/messages", params=params) or []
        return [Message.from_dict(item) for item in raw]

    def delete_message(self, channel_id: str, message_id: str, reason: str | None = None) -> None:
        self.http.delete(f"/channels/{channel_id}/messages/{message_id}", reason=reason)

    def bulk_delete_messages(self, channel_id: str, message_ids: Iterable[str]) -> int:
        ids = [str(m) for m in message_ids]
        if not ids:
            return 0
        if len(ids) > BULK_DELETE_MAX:
            raise DiscordError(f"Discord solo permite borrar {BULK_DELETE_MAX} mensajes a la vez.")
        self.http.post(f"/channels/{channel_id}/messages/bulk-delete",
                       body={"messages": ids})
        return len(ids)

    def purge_messages(self, channel_id: str, message_ids: Iterable[str]) -> tuple[int, int]:
        """Borra en lote; si Discord rechaza alguno (más de 14 días), borra uno a uno."""
        ids = [str(m) for m in message_ids]
        if not ids:
            return (0, 0)
        if len(ids) <= BULK_DELETE_MAX:
            try:
                self.bulk_delete_messages(channel_id, ids)
                return (len(ids), 0)
            except DiscordError:
                pass
        deleted = failed = 0
        for message_id in ids:
            try:
                self.delete_message(channel_id, message_id)
                deleted += 1
            except DiscordError:
                failed += 1
        return (deleted, failed)

    def pin_message(self, channel_id: str, message_id: str) -> None:
        self.http.put(f"/channels/{channel_id}/pins/{message_id}")

    def unpin_message(self, channel_id: str, message_id: str) -> None:
        self.http.delete(f"/channels/{channel_id}/pins/{message_id}")

    def send_message(self, channel_id: str, content: str) -> Message:
        raw = self.http.post(f"/channels/{channel_id}/messages",
                             body={"content": content, "allowed_mentions": {"parse": []}})
        return Message.from_dict(raw or {})

    def create_dm(self, user_id: str) -> str:
        raw = self.http.post("/users/@me/channels", body={"recipient_id": user_id})
        return str((raw or {}).get("id", ""))

    # ------------------------------------------------------------------ #
    # Invitaciones
    # ------------------------------------------------------------------ #
    def list_guild_invites(self, guild_id: str) -> list[Invite]:
        raw = self.http.get(f"/guilds/{guild_id}/invites") or []
        return [Invite.from_dict(item) for item in raw]

    def create_invite(self, channel_id: str, max_age: int = 86400, max_uses: int = 0,
                      temporary: bool = False, reason: str | None = None) -> Invite:
        body = {"max_age": int(max_age), "max_uses": int(max_uses), "temporary": bool(temporary)}
        raw = self.http.post(f"/channels/{channel_id}/invites", body=body, reason=reason)
        return Invite.from_dict(raw or {})

    def delete_invite(self, code: str, reason: str | None = None) -> None:
        self.http.delete(f"/invites/{code}", reason=reason)

    def list_channel_followers(self, channel_id: str) -> list[dict]:
        raw = self.http.get(f"/channels/{channel_id}/followers") or []
        return list(raw) if isinstance(raw, list) else []

    # ------------------------------------------------------------------ #
    # Auditoría
    # ------------------------------------------------------------------ #
    def list_audit_logs(self, guild_id: str, limit: int = 50, before: str | None = None,
                        action_type: int | None = None,
                        user_id: str | None = None) -> list[AuditEntry]:
        params: dict[str, Any] = {"limit": max(1, min(limit, 100))}
        if before:
            params["before"] = before
        if action_type:
            params["action_type"] = int(action_type)
        if user_id:
            params["user_id"] = user_id
        raw = self.http.get(f"/guilds/{guild_id}/audit-logs", params=params) or {}
        users = {str(user.get("id")): User.from_dict(user)
                 for user in (raw.get("users") or []) if isinstance(user, dict)}
        entries: list[AuditEntry] = []
        for item in raw.get("audit_log_entries") or []:
            entry = AuditEntry.from_dict(item)
            entry.actor = users.get(str(entry.user_id)) if entry.user_id else None
            entry.target = users.get(str(entry.target_id)) if entry.target_id else None
            entries.append(entry)
        return entries

    # ------------------------------------------------------------------ #
    # Emojis
    # ------------------------------------------------------------------ #
    def list_emojis(self, guild_id: str) -> list[Emoji]:
        raw = self.http.get(f"/guilds/{guild_id}/emojis") or []
        return [Emoji.from_dict(item) for item in raw]

    def list_active_threads(self, channel_id: str) -> list[Channel]:
        raw = self.http.get(f"/channels/{channel_id}/threads/active") or {}
        return [Channel.from_dict(item) for item in (raw.get("threads") or [])]

    def create_emoji(self, guild_id: str, name: str, image_data_uri: str,
                     roles: list[str] | None = None, reason: str | None = None) -> Emoji:
        body: dict[str, Any] = {"name": name, "image": image_data_uri}
        if roles:
            body["roles"] = roles
        raw = self.http.post(f"/guilds/{guild_id}/emojis", body=body, reason=reason)
        return Emoji.from_dict(raw or {})

    def update_emoji(self, guild_id: str, emoji_id: str, fields: dict,
                     reason: str | None = None) -> Emoji:
        raw = self.http.patch(f"/guilds/{guild_id}/emojis/{emoji_id}",
                              body=fields, reason=reason)
        return Emoji.from_dict(raw or {})

    def delete_emoji(self, guild_id: str, emoji_id: str, reason: str | None = None) -> None:
        self.http.delete(f"/guilds/{guild_id}/emojis/{emoji_id}", reason=reason)

    # ------------------------------------------------------------------ #
    # Webhooks
    # ------------------------------------------------------------------ #
    def list_webhooks(self, guild_id: str) -> list[Webhook]:
        raw = self.http.get(f"/guilds/{guild_id}/webhooks") or []
        return [Webhook.from_dict(item) for item in raw]

    def get_webhook(self, webhook_id: str) -> Webhook:
        raw = self.http.get(f"/webhooks/{webhook_id}")
        return Webhook.from_dict(raw or {})

    def create_webhook(self, channel_id: str, name: str, reason: str | None = None) -> Webhook:
        raw = self.http.post(f"/channels/{channel_id}/webhooks", body={"name": name}, reason=reason)
        return Webhook.from_dict(raw or {})

    def delete_webhook(self, webhook_id: str, reason: str | None = None) -> None:
        self.http.delete(f"/webhooks/{webhook_id}", reason=reason)

    # ------------------------------------------------------------------ #
    # Automod
    # ------------------------------------------------------------------ #
    def list_automod_rules(self, guild_id: str) -> list[AutoModRule]:
        raw = self.http.get(f"/guilds/{guild_id}/auto-moderation/rules") or []
        return [AutoModRule.from_dict(item) for item in raw]

    def create_automod_rule(self, guild_id: str, body: dict,
                            reason: str | None = None) -> AutoModRule:
        raw = self.http.post(f"/guilds/{guild_id}/auto-moderation/rules", body=body, reason=reason)
        return AutoModRule.from_dict(raw or {})

    def update_automod_rule(self, guild_id: str, rule_id: str, body: dict,
                            reason: str | None = None) -> AutoModRule:
        raw = self.http.patch(f"/guilds/{guild_id}/auto-moderation/rules/{rule_id}",
                              body=body, reason=reason)
        return AutoModRule.from_dict(raw or {})

    def delete_automod_rule(self, guild_id: str, rule_id: str, reason: str | None = None) -> None:
        self.http.delete(f"/guilds/{guild_id}/auto-moderation/rules/{rule_id}", reason=reason)

    # ------------------------------------------------------------------ #
    # Ayudas
    # ------------------------------------------------------------------ #
    def validate_token(self) -> User:
        return self.login()

    def ping(self) -> float:
        import time
        start = time.perf_counter()
        self.http.get("/gateway")
        return (time.perf_counter() - start) * 1000.0
