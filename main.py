#!/usr/bin/env python3
"""Discord Server Studio — panel de escritorio para administrar servidores de Discord.

Ejecuta:  python main.py            (pide un token)
          python main.py --demo     (datos de demostración, sin token)
"""
from __future__ import annotations

import os
import sys


def main() -> None:
    base = os.path.dirname(os.path.abspath(__file__))
    if base not in sys.path:
        sys.path.insert(0, base)
    from dss.cli import run

    run()


if __name__ == "__main__":
    main()
