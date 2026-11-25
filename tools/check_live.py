"""Prueba de la sincronización automática (herramienta de desarrollo)."""
from __future__ import annotations

import os
import shutil
import sys
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DSS_HOME"] = str(ROOT / "_testdata_live")
shutil.rmtree(os.environ["DSS_HOME"], ignore_errors=True)

import dss.ui.app as app_module  # noqa: E402
from dss.models import GuildSummary, User  # noqa: E402
from dss.oauth import OAuthTokens  # noqa: E402
from dss.ui.app import App  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("OK    " if condition else "FALLO ") + name + (f"  {detail}" if detail else ""))
    if not condition:
        FAILURES.append(name)


def pump(app: tk.Misc, seconds: float = 0.8) -> None:
    end = time.time() + seconds
    while time.time() < end:
        try:
            app.update()
        except tk.TclError:
            return
        time.sleep(0.02)


def main() -> None:
    app = App()
    app.settings.set("live_sync", True)
    app.start_demo()
    pump(app, 0.6)
    summary = next(g for g in app.guilds if g.name == "Estudio Lunar")
    app.open_guild(summary)
    pump(app, 1.2)
    app.shell.switch_page("channels")
    pump(app, 0.8)

    # Cancelar el temporizador automático para disparar los ciclos a mano.
    if app._live_after is not None:
        app.after_cancel(app._live_after)
        app._live_after = None

    guild_id = app.guild.id
    app.client.create_channel(guild_id, {"name": "canal-en-vivo", "type": 0})
    app._live_tick()
    pump(app, 1.6)
    check("canal externo aparece en los datos",
          any(c.name == "canal-en-vivo" for c in app.channels))
    page = app.shell._pages["channels"]
    check("canal externo aparece en la lista visible",
          any(c.name == "canal-en-vivo" for c in page._channels))
    check("estado en vivo", app.live_status == "live", app.live_status)

    # Los cambios sin guardar no deben pisarse.
    app.shell.switch_page("settings")
    pump(app, 0.9)
    settings_page = app.shell._pages["settings"]
    settings_page.name_var.set("Nombre sin guardar")
    check("detecta cambios sin guardar", settings_page.is_dirty())
    app._live_tick()
    pump(app, 1.6)
    check("no pisa cambios sin guardar",
          settings_page.name_var.get() == "Nombre sin guardar",
          settings_page.name_var.get())
    check("estado en pausa por edición", app.live_status == "editing", app.live_status)

    # Desactivar la sincronización.
    app.toggle_live()
    pump(app, 0.3)
    check("sincronización desactivada", app.live_status == "off"
          and not app.settings.get("live_sync"))
    app.on_close()

    # Modo OAuth real: sin bot, solo lista de servidores. La lista debe refrescarse
    # periódicamente y actualizar las tarjetas si cambian nombre/icono/permisos.
    app2 = App()
    app2.settings.set("live_sync", True)
    app2.start_demo()
    pump(app2, 0.5)
    if app2._live_after is not None:
        app2.after_cancel(app2._live_after)
        app2._live_after = None
    app2.client = None
    app2.session_kind = "oauth"
    app2.oauth_tokens = OAuthTokens("token-de-prueba", expires_at=time.time() + 3600)
    fake_user = User(id="42", username="luna", global_name="Luna")
    fake_guilds = [GuildSummary(id="10", name="Servidor externo", owner=True,
                                permissions=-1, member_count=5)]
    original = app_module.fetch_identity
    app_module.fetch_identity = lambda _token: (fake_user, fake_guilds)
    app2._live_tick()
    pump(app2, 1.5)
    check("lista OAuth se refresca", any(g.name == "Servidor externo" for g in app2.guilds))
    cards = app2._view._cards
    check("tarjeta OAuth se actualiza", any(card.summary.name == "Servidor externo"
                                            for card in cards))
    check("estado en vivo OAuth", app2.live_status == "live", app2.live_status)
    app_module.fetch_identity = original
    app2.toggle_live()
    check("OAuth se puede pausar", app2.live_status == "off")
    app2.on_close()

    total = 11
    print(f"\nRESULTADO: {total - len(FAILURES)}/{total} correctas")
    if FAILURES:
        print("FALLOS:", FAILURES)
        sys.exit(1)


if __name__ == "__main__":
    main()
