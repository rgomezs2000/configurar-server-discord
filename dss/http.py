"""Cliente HTTP para la API de Discord: rate limits, reintentos y errores."""
from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .constants import API_BASE, USER_AGENT
from .errors import DiscordError, from_http_error

TRANSIENT_STATUS = {500, 502, 503, 504}


@dataclass
class _Bucket:
    remaining: int = 5
    reset_at: float = 0.0


def route_template(path: str) -> str:
    """Agrupa rutas por plantilla: /channels/123/messages -> /channels/:id/messages."""
    clean = path.split("?")[0].strip("/")
    parts = clean.split("/")
    return "/".join(":id" if part.isdigit() else part for part in parts)


class DiscordHTTP:
    """Transporte con control de rate limit por bucket y reintentos moderados."""

    def __init__(self, token: str, kind: str = "bot", timeout: float = 25.0):
        self.token = (token or "").strip()
        self.kind = kind if kind in ("bot", "user") else "bot"
        self.timeout = timeout
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, str], _Bucket] = {}
        self._global_until = 0.0
        self.request_count = 0

    # -- cabeceras ---------------------------------------------------------- #
    def _headers(self, has_body: bool, reason: str | None) -> dict[str, str]:
        auth = f"Bot {self.token}" if self.kind == "bot" else self.token
        headers = {
            "Authorization": auth,
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        if has_body:
            headers["Content-Type"] = "application/json"
        if reason:
            headers["X-Audit-Log-Reason"] = urllib.parse.quote(reason[:512], safe="")
        return headers

    # -- rate limit --------------------------------------------------------- #
    def _wait_for_bucket(self, key: tuple[str, str]) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                bucket = self._buckets.get(key)
                wait = 0.0
                if now < self._global_until:
                    wait = self._global_until - now
                elif bucket and bucket.remaining <= 0 and bucket.reset_at > now:
                    wait = bucket.reset_at - now
            if wait <= 0:
                return
            time.sleep(min(wait + 0.05, 30.0))

    def _update_bucket(self, key: tuple[str, str], headers: Any) -> None:
        if headers is None:
            return
        try:
            remaining = headers.get("X-RateLimit-Remaining")
            reset_after = headers.get("X-RateLimit-Reset-After")
            if remaining is None:
                return
            with self._lock:
                bucket = self._buckets.setdefault(key, _Bucket())
                bucket.remaining = int(float(remaining))
                if reset_after is not None:
                    bucket.reset_at = time.monotonic() + float(reset_after) + 0.02
        except (TypeError, ValueError):
            return

    def _apply_global(self, headers: Any, payload: Any) -> None:
        global_flag = str((headers or {}).get("X-RateLimit-Global", "")).lower() == "true"
        if not global_flag and isinstance(payload, dict):
            global_flag = bool(payload.get("global"))
        if not global_flag:
            return
        retry = payload.get("retry_after") if isinstance(payload, dict) else None
        seconds = float(retry) if isinstance(retry, (int, float)) else 1.0
        with self._lock:
            self._global_until = max(self._global_until, time.monotonic() + seconds + 0.05)

    # -- petición ----------------------------------------------------------- #
    def request(self, method: str, path: str, *, body: Any = None,
                params: dict[str, Any] | None = None, reason: str | None = None,
                timeout: float | None = None, retries: int = 2) -> Any:
        method = method.upper()
        route = path if path.startswith("/") else f"/{path}"
        key = (method, route_template(route))

        query = {k: v for k, v in (params or {}).items() if v is not None}
        url = API_BASE + route
        if query:
            url += "?" + urllib.parse.urlencode(query)

        data: bytes | None = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        attempt = 0
        while True:
            self._wait_for_bucket(key)
            request = urllib.request.Request(
                url, data=data, headers=self._headers(data is not None, reason),
                method=method,
            )
            with self._lock:
                self.request_count += 1
            try:
                with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                    self._update_bucket(key, response.headers)
                    raw = response.read()
                    return json.loads(raw.decode("utf-8")) if raw else None
            except urllib.error.HTTPError as error:
                payload = self._read_payload(error)
                self._update_bucket(key, error.headers)
                if error.code == 429:
                    self._apply_global(error.headers, payload)
                    if attempt < retries:
                        retry_after = payload.get("retry_after") if isinstance(payload, dict) else None
                        wait = float(retry_after) if isinstance(retry_after, (int, float)) else 1.0
                        time.sleep(min(max(wait, 0.5), 30.0))
                        attempt += 1
                        continue
                if error.code in TRANSIENT_STATUS and attempt < retries:
                    time.sleep(0.8 * (attempt + 1))
                    attempt += 1
                    continue
                raise from_http_error(error.code, payload) from None
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as error:
                reason_text = getattr(error, "reason", error)
                if attempt < retries:
                    time.sleep(0.6 * (attempt + 1))
                    attempt += 1
                    continue
                raise DiscordError(
                    f"No se pudo conectar con Discord: {reason_text}. "
                    "Comprueba tu conexión a internet o el proxy."
                ) from None
            except json.JSONDecodeError:
                raise DiscordError("Discord devolvió una respuesta ilegible.") from None

    @staticmethod
    def _read_payload(error: urllib.error.HTTPError) -> Any:
        try:
            raw = error.read()
        except Exception:  # noqa: BLE001 - cuerpo no disponible
            return {}
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            return {"message": raw.decode("utf-8", "replace")[:300]}

    # -- atajos ------------------------------------------------------------- #
    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Any:
        return self.request("PATCH", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.request("DELETE", path, **kwargs)
