"""Interfaz de línea de comandos (punto de entrada único)."""
from __future__ import annotations

import os
import sys


def run() -> None:
    """Arranca la aplicación. Opciones: --version, --demo."""
    if "--version" in sys.argv:
        from . import __version__

        print(f"Discord Server Studio {__version__}")
        return
    if "--demo" in sys.argv:
        os.environ["DSS_DEMO"] = "1"
    from .ui.app import main

    main()
