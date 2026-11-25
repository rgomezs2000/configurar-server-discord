"""Comprueba la descarga y el dibujado de avatares/iconos en Tk (herramienta dev)."""
from __future__ import annotations

import base64
import os
import sys
import time
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dss.tasks import TaskRunner  # noqa: E402
from dss.ui.images import ImageCache  # noqa: E402
from dss.ui.picker import GuildCard  # noqa: E402
from dss.ui.theme import Theme  # noqa: E402
from dss.ui.widgets import Avatar, GuildTile  # noqa: E402

URL = os.environ.get("DSS_TEST_IMAGE", "https://cdn.discordapp.com/embed/avatars/0.png")
RESULTS: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("OK    " if condition else "FALLO ") + name + (f"  {detail}" if detail else ""))
    if not condition:
        RESULTS.append(name)


class _FakeApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.tasks = TaskRunner(root)


def pump(root: tk.Tk, seconds: float = 15.0, done: Any = None) -> None:
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        if done is not None and done():
            return
        time.sleep(0.03)


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    app = _FakeApp(root)
    cache = ImageCache(app)  # type: ignore[arg-type]
    holder: dict[str, Any] = {}

    def callback(photo: tk.PhotoImage | None) -> None:
        holder["photo"] = photo

    cache.get(URL, 48, callback)
    pump(root, 15, lambda: "photo" in holder)
    photo = holder.get("photo")
    check("descarga y decodifica la imagen", photo is not None,
          f"width={photo.width() if photo else 0}")
    check("la imagen tiene tamaño", bool(photo and photo.width() > 0))

    avatar = Avatar(root, "Prueba", 40, theme=None)
    avatar.set_photo(photo)
    check("avatar muestra la imagen", avatar._photo is photo)
    avatar.set_photo(None)
    check("avatar vuelve al respaldo", avatar._photo is None)

    tile = GuildTile(root, "Servidor", 48, bg="#000000")
    tile.set_photo(photo)
    check("icono muestra la imagen", tile._photo is photo)
    tile.set_photo(None)
    check("icono vuelve al respaldo", tile._photo is None)

    # La URL vacía no debe romper: se queda el respaldo.
    cache.apply(avatar, None, 40)
    check("URL vacía usa respaldo", avatar._photo is None)

    wired = Avatar(root, "Wired", 40, theme=None)
    cache.apply(wired, URL, 40)
    pump(root, 5, lambda: wired._photo is not None)
    check("apply conecta la imagen al avatar", wired._photo is not None)

    # Dos widgets que piden la misma URL mientras descarga deben recibirla ambos.
    duplicate_url = "https://cdn.discordapp.com/embed/avatars/1.png"
    received: list[tk.PhotoImage | None] = []
    cache.get(duplicate_url, 32, lambda photo: received.append(photo))
    cache.get(duplicate_url, 32, lambda photo: received.append(photo))
    pump(root, 15, lambda: len(received) >= 2)
    check("dos widgets reciben la misma imagen",
          len(received) == 2 and all(photo is not None for photo in received),
          f"{len(received)} avisos")

    app.theme = Theme(root)
    app.images = cache
    app.bot_guild_ids = set()
    app.bot_guild_ids_known = False
    summary = SimpleNamespace(id="1", name="Servidor de prueba", icon_url=URL,
                              member_count=10, access_label="Propietario",
                              features=[], owner=True)
    card = GuildCard(root, summary, app, lambda: None)
    card.pack()
    pump(root, 5, lambda: card.tile._photo is not None)
    check("tarjeta del selector muestra el icono", card.tile._photo is not None)

    gif = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==")
    check("decodifica iconos GIF", ImageCache._to_photo(gif, 30) is not None)

    root.destroy()
    total = 11
    print(f"\nRESULTADO: {total - len(RESULTS)}/{total} correctas")
    if RESULTS:
        print("FALLOS:", RESULTS)
        sys.exit(1)


if __name__ == "__main__":
    main()
