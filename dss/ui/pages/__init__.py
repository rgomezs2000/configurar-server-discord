"""Páginas del panel y orden de navegación."""
from __future__ import annotations

from .automod import AutomodPage
from .base import Page
from .channels import ChannelsPage
from .dashboard import DashboardPage
from .emojis import EmojisPage
from .invites import InvitesPage
from .members import MembersPage
from .moderation import ModerationPage
from .roles import RolesPage
from .settings import SettingsPage
from .webhooks import WebhooksPage

PAGE_CLASSES = [
    DashboardPage, ChannelsPage, RolesPage, MembersPage,
    ModerationPage, AutomodPage, InvitesPage,
    EmojisPage, WebhooksPage, SettingsPage,
]

PAGE_BY_KEY = {page.key: page for page in PAGE_CLASSES}

NAV_GROUPS = [
    ("Gestión", ["dashboard", "channels", "roles", "members"]),
    ("Moderación", ["moderation", "automod", "invites"]),
    ("Configuración", ["emojis", "webhooks", "settings"]),
]

__all__ = ["Page", "PAGE_CLASSES", "PAGE_BY_KEY", "NAV_GROUPS"]
