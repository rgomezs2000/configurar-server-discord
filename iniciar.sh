#!/usr/bin/env bash
# Inicia Discord Server Studio en macOS o Linux.
set -e
cd "$(dirname "$0")"
exec python3 main.py "$@"
