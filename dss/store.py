"""Persistencia local: ajustes y token cifrado con el almacén del sistema.

Windows usa DPAPI, macOS el Llavero y Linux ``secret-tool``. Si ninguno está
disponible se guarda un archivo con permisos restringidos y el aviso en la UI.
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SERVICE_NAME = "DiscordServerStudio"
ACCOUNT_NAME = "discord-token"


def app_data_dir() -> Path:
    """Carpeta de datos. ``DSS_HOME`` permite un modo portable."""
    override = os.environ.get("DSS_HOME")
    if override:
        directory = Path(override).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    for candidate in (Path(base) / SERVICE_NAME, Path.home() / f".{SERVICE_NAME.lower()}"):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            continue
    import tempfile
    fallback = Path(tempfile.gettempdir()) / SERVICE_NAME
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


# --------------------------------------------------------------------------- #
# Ajustes
# --------------------------------------------------------------------------- #

class Settings:
    """Ajustes de la aplicación en un JSON sencillo."""

    DEFAULTS: dict[str, Any] = {
        "remember_token": False,
        "last_guild_id": "",
        "window_geometry": "",
        "token_kind": "user",
        "account_risk_accepted": False,
        "recent_emojis": [],
        "live_sync": False,
        "live_sync_v2": False,
        "live_sync_v3": False,
        "last_page": "dashboard",
        "show_ids": False,
        "confirm_destructive": True,
    }

    def __init__(self) -> None:
        self.path = app_data_dir() / "settings.json"
        self.data: dict[str, Any] = dict(self.DEFAULTS)
        try:
            if self.path.exists():
                loaded = json.loads(self.path.read_text("utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass
        # La actualización manual es la opción por defecto. Esta migración apaga
        # una sola vez el sondeo automático de instalaciones anteriores.
        if not self.data.get("live_sync_v3"):
            self.data["live_sync"] = False
            self.data["live_sync_v3"] = True

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, self.DEFAULTS.get(key, default))

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def save(self) -> None:
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), "utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# Cifrado del sistema
# --------------------------------------------------------------------------- #

class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _win_protect(data: bytes) -> bytes | None:
    if sys.platform != "win32":
        return None
    try:
        buffer = ctypes.create_string_buffer(data, len(data))
        blob_in = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
        blob_out = _Blob()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
        if not ok:
            return None
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    except Exception:  # noqa: BLE001 - sin DPAPI disponible
        return None


def _win_unprotect(data: bytes) -> bytes | None:
    if sys.platform != "win32":
        return None
    try:
        buffer = ctypes.create_string_buffer(data, len(data))
        blob_in = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
        blob_out = _Blob()
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
        if not ok:
            return None
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    except Exception:  # noqa: BLE001
        return None


def _run(cmd: list[str], stdin: str | None = None) -> tuple[int, str]:
    try:
        result = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=12)
        return result.returncode, (result.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return 1, ""


class TokenStore:
    """Guarda el token de sesión con el mejor cifrado disponible."""

    def __init__(self, path: Path | None = None, account: str = ACCOUNT_NAME) -> None:
        self.path = path or app_data_dir() / "session.dat"
        self.account = account

    @classmethod
    def for_bot(cls) -> "TokenStore":
        """Almacén independiente para el token fijo del bot."""
        return cls(app_data_dir() / "bot_token.dat", "discord-bot-token")

    # -- capacidad ---------------------------------------------------------- #
    def method(self) -> str:
        if sys.platform == "win32":
            return "dpapi" if _win_protect(b"test") else "plain"
        if sys.platform == "darwin":
            return "keychain" if self._keychain_available() else "plain"
        return "libsecret" if self._libsecret_available() else "plain"

    def method_label(self) -> str:
        return {
            "dpapi": "DPAPI del sistema (Windows)",
            "keychain": "Llavero de macOS",
            "libsecret": "libsecret / GNOME Keyring",
            "plain": "archivo local con permisos restringidos (sin cifrado)",
        }.get(self.method(), "archivo local")

    def is_secure(self) -> bool:
        return self.method() != "plain"

    def _keychain_available(self) -> bool:
        code, _ = _run(["security", "find-generic-password", "-s", SERVICE_NAME,
                        "-a", self.account, "-w"])
        return code == 0

    def _libsecret_available(self) -> bool:
        code, _ = _run(["secret-tool", "lookup", "service", SERVICE_NAME])
        return code == 0

    # -- API ---------------------------------------------------------------- #
    def _store_blob(self, text: str) -> bool:
        method = self.method()
        try:
            if method == "dpapi":
                blob = _win_protect(text.encode("utf-8"))
                if blob is None:
                    return False
                payload = {"method": "dpapi", "blob": base64.b64encode(blob).decode("ascii")}
            elif method == "keychain":
                _run(["security", "delete-generic-password", "-s", SERVICE_NAME,
                      "-a", self.account])
                code, _ = _run(["security", "add-generic-password", "-U", "-s", SERVICE_NAME,
                                "-a", self.account, "-w", text])
                if code != 0:
                    return False
                payload = {"method": "keychain"}
            elif method == "libsecret":
                code, _ = _run(["secret-tool", "store", "--label", "Discord Server Studio",
                                "service", SERVICE_NAME, "account", self.account], stdin=text)
                if code != 0:
                    return False
                payload = {"method": "libsecret"}
            else:
                payload = {"method": "plain", "data": text}

            payload["saved_at"] = datetime.now(timezone.utc).isoformat()
            self.path.write_text(json.dumps(payload), "utf-8")
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
            return True
        except (OSError, ValueError):
            return False

    def _read_blob(self) -> str | None:
        try:
            if not self.path.exists():
                return None
            payload = json.loads(self.path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        method = payload.get("method")
        try:
            if method == "dpapi":
                raw = _win_unprotect(base64.b64decode(payload.get("blob") or ""))
                return raw.decode("utf-8") if raw else None
            if method == "keychain":
                code, text = _run(["security", "find-generic-password", "-s", SERVICE_NAME,
                                   "-a", self.account, "-w"])
                return text if code == 0 and text else None
            if method == "libsecret":
                code, text = _run(["secret-tool", "lookup", "service", SERVICE_NAME,
                                   "account", self.account])
                return text if code == 0 and text else None
            if payload.get("data") is not None:
                return str(payload["data"])
            if payload.get("token") is not None:
                # Formato antiguo (token + kind sueltos).
                return json.dumps({"token": payload.get("token", ""),
                                   "kind": payload.get("kind", "bot")})
        except (OSError, ValueError, KeyError):
            return None
        return None

    def save(self, token: str, kind: str) -> bool:
        return self._store_blob(json.dumps({"token": token, "kind": kind}))

    def load(self) -> tuple[str, str] | None:
        text = self._read_blob()
        if not text:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        token = str(data.get("token") or "")
        return (token, str(data.get("kind") or "bot")) if token else None

    def save_session(self, payload: dict) -> bool:
        return self._store_blob(json.dumps(payload, ensure_ascii=False))

    def load_session(self) -> dict | None:
        text = self._read_blob()
        if not text:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def clear(self) -> None:
        try:
            if self.path.exists():
                self.path.unlink()
        except OSError:
            pass
        if sys.platform == "darwin":
            _run(["security", "delete-generic-password", "-s", SERVICE_NAME,
                  "-a", self.account])
        elif sys.platform not in ("win32",):
            _run(["secret-tool", "clear", "service", SERVICE_NAME, "account", self.account])
