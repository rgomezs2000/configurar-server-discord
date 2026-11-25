"""OAuth2 de Discord con callback local (PKCE, sin client secret).

Flujo:
1. Se abre el navegador en la pantalla de autorización de Discord.
2. Discord redirige a ``http://127.0.0.1:PUERTO/callback`` con un ``code``.
3. La app canjea el código por un access token (PKCE) y lee el usuario y sus
   servidores con los scopes ``identify guilds``.

El token obtenido solo sirve para identidad y lista de servidores; las acciones
de administración las ejecuta el bot con su propio token (ver ``api.py``).
"""
from __future__ import annotations

import base64
import hashlib
import json
import queue
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from .constants import USER_AGENT
from .models import GuildSummary, User

API_BASE = "https://discord.com/api/v10"
AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
TOKEN_URL = "https://discord.com/api/v10/oauth2/token"
DEFAULT_CLIENT_ID = "1574502573577343058"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:5000/callback"
DEFAULT_SCOPES = "identify guilds"
BOT_PERMISSIONS = 8  # Administrador; el bot necesita permisos para moderar.


class OAuthError(Exception):
    pass


class OAuthCancelled(OAuthError):
    pass


@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: str = ""
    expires_at: float = 0.0
    scope: str = ""

    @property
    def expired(self) -> bool:
        return bool(self.expires_at) and time.time() >= self.expires_at - 60

    def to_dict(self) -> dict:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "scope": self.scope,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OAuthTokens":
        return cls(
            access_token=str(data.get("access_token") or ""),
            refresh_token=str(data.get("refresh_token") or ""),
            expires_at=float(data.get("expires_at") or 0.0),
            scope=str(data.get("scope") or ""),
        )


@dataclass
class OAuthResult:
    tokens: OAuthTokens
    user: User
    guilds: list[GuildSummary]


def pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode("ascii").rstrip("=")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def parse_redirect_uri(uri: str) -> tuple[str, int, str]:
    parsed = urllib.parse.urlparse((uri or "").strip())
    if parsed.scheme not in ("http", "https"):
        raise OAuthError("El redirect URI debe empezar por http:// o https://.")
    host = (parsed.hostname or "").lower()
    if host not in ("127.0.0.1", "localhost"):
        raise OAuthError("El redirect URI debe apuntar a 127.0.0.1 o localhost.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    return host, port, path


def build_authorize_url(client_id: str, redirect_uri: str, state: str,
                        challenge: str, scopes: str = DEFAULT_SCOPES) -> str:
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "consent",
    }
    return AUTHORIZE_URL + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def _request_json(url: str, *, data: dict | None = None,
                  headers: dict[str, str] | None = None,
                  timeout: float = 25.0) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8") if data is not None else None
    request = urllib.request.Request(url, data=body, headers=headers or {},
                                     method="POST" if body is not None else "GET")
    request.add_header("User-Agent", USER_AGENT)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as error:
        try:
            payload = json.loads(error.read().decode("utf-8", "replace"))
        except (ValueError, OSError):
            payload = {}
        detail = payload.get("error_description") or payload.get("message") or ""
        if error.code == 401:
            raise OAuthError(
                "Discord rechazó la autorización (401). Revisa que el redirect URI "
                "coincida exactamente con el registrado en el portal.") from None
        raise OAuthError(f"Discord devolvió {error.code}: {detail or 'error'}") from None
    except (urllib.error.URLError, TimeoutError) as error:
        raise OAuthError(f"No se pudo conectar con Discord: {error}") from None


def exchange_code(client_id: str, redirect_uri: str, code: str, verifier: str,
                  *, token_url: str = TOKEN_URL) -> OAuthTokens:
    payload = _request_json(
        token_url,
        data={
            "client_id": client_id,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = str(payload.get("access_token") or "")
    if not token:
        raise OAuthError("Discord no devolvió un access token.")
    expires_in = float(payload.get("expires_in") or 604800)
    return OAuthTokens(
        access_token=token,
        refresh_token=str(payload.get("refresh_token") or ""),
        expires_at=time.time() + expires_in,
        scope=str(payload.get("scope") or ""),
    )


def refresh_tokens(client_id: str, refresh_token: str,
                   *, token_url: str = TOKEN_URL) -> OAuthTokens:
    payload = _request_json(
        token_url,
        data={
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = str(payload.get("access_token") or "")
    if not token:
        raise OAuthError("No se pudo renovar la sesión de Discord.")
    expires_in = float(payload.get("expires_in") or 604800)
    return OAuthTokens(
        access_token=token,
        refresh_token=str(payload.get("refresh_token") or refresh_token),
        expires_at=time.time() + expires_in,
        scope=str(payload.get("scope") or ""),
    )


def fetch_identity(access_token: str) -> tuple[User, list[GuildSummary]]:
    headers = {"Authorization": f"Bearer {access_token}"}
    me = _request_json(f"{API_BASE}/users/@me", headers=headers)
    raw_guilds = _request_json(
        f"{API_BASE}/users/@me/guilds?limit=200&with_counts=true", headers=headers)
    guilds = [GuildSummary.from_dict(item) for item in (raw_guilds or [])
              if isinstance(item, dict)]
    return User.from_dict(me), guilds


def bot_invite_url(client_id: str, guild_id: str | None = None,
                   permissions: int = BOT_PERMISSIONS) -> str:
    url = (f"https://discord.com/oauth2/authorize?client_id={client_id}"
           f"&permissions={permissions}&scope=bot%20applications.commands")
    if guild_id:
        url += f"&guild_id={guild_id}&disable_guild_select=true"
    return url


class _CallbackServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - API de http.server
        parsed = urllib.parse.urlparse(self.path)
        server: Any = self.server
        if parsed.path != server.expected_path:
            self.send_response(404)
            self.end_headers()
            return
        params = urllib.parse.parse_qs(parsed.query)
        state = (params.get("state") or [""])[0]
        code = (params.get("code") or [""])[0]
        error = (params.get("error") or [""])[0]
        if error:
            server.oauth_error = "Autorización cancelada en Discord."
        elif state != server.expected_state:
            server.oauth_error = "El estado de OAuth no coincide (posible CSRF)."
        elif not code:
            server.oauth_error = "Discord no devolvió el código de autorización."
        else:
            server.oauth_code = code
        server.event.set()
        self._respond(server.oauth_error)

    def _respond(self, error: str) -> None:
        title = "Autorización completada" if not error else "No se pudo completar"
        message = ("Ya puedes volver a Discord Server Studio."
                   if not error else error)
        html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>{title}</title><style>
body{{background:#1e1f22;color:#f2f3f5;font-family:Segoe UI,Arial,sans-serif;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
.card{{background:#313338;border:1px solid #3f4147;border-radius:12px;padding:32px 40px;
max-width:460px;text-align:center}} h1{{font-size:20px;margin:0 0 10px}}
p{{color:#b5bac1;font-size:14px;margin:0}} .ok{{color:#23a55a}}</style></head>
<body><div class="card"><h1 class="{'ok' if not error else ''}">{title}</h1>
<p>{message}</p></div></body></html>"""
        encoded = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args: Any) -> None:
        return


class OAuthFlow:
    """Flujo OAuth en segundo plano con servidor de callback local."""

    def __init__(self, client_id: str, redirect_uri: str, *, timeout: float = 180.0,
                 exchanger: Callable[..., OAuthTokens] = exchange_code,
                 identity: Callable[[str], tuple[User, list[GuildSummary]]] = fetch_identity):
        self.client_id = client_id.strip()
        self.redirect_uri = redirect_uri.strip()
        self.timeout = timeout
        self._exchanger = exchanger
        self._identity = identity
        self.state = secrets.token_urlsafe(24)
        self.verifier, self.challenge = pkce_pair()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._queue: "queue.Queue[tuple[str, Any]]" = queue.Queue()
        self._cancelled = False

    def start(self) -> str:
        host, port, path = parse_redirect_uri(self.redirect_uri)
        try:
            server = _CallbackServer((host, port), _CallbackHandler)
        except OSError as error:
            raise OAuthError(
                f"No se pudo abrir el puerto {port} para el callback: {error}. "
                "Cierra el programa que lo esté usando o cambia el redirect URI.") from None
        server.expected_state = self.state  # type: ignore[attr-defined]
        server.expected_path = path  # type: ignore[attr-defined]
        server.oauth_code = ""  # type: ignore[attr-defined]
        server.oauth_error = ""  # type: ignore[attr-defined]
        server.event = threading.Event()  # type: ignore[attr-defined]
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()
        threading.Thread(target=self._run, daemon=True).start()
        return build_authorize_url(self.client_id, self.redirect_uri, self.state,
                                   self.challenge)

    def _run(self) -> None:
        server = self._server
        if server is None:
            return
        try:
            received = server.event.wait(self.timeout)  # type: ignore[attr-defined]
            if self._cancelled:
                self._queue.put(("error", OAuthCancelled("Autorización cancelada.")))
                return
            if not received:
                self._queue.put(("error", OAuthError(
                    "Se agotó el tiempo de espera. Vuelve a intentarlo.")))
                return
            error = server.oauth_error  # type: ignore[attr-defined]
            if error:
                self._queue.put(("error", OAuthError(error)))
                return
            code = server.oauth_code  # type: ignore[attr-defined]
            tokens = self._exchanger(self.client_id, self.redirect_uri, code, self.verifier)
            user, guilds = self._identity(tokens.access_token)
            self._queue.put(("ok", OAuthResult(tokens, user, guilds)))
        except OAuthError as error:
            self._queue.put(("error", error))
        except Exception as error:  # noqa: BLE001
            self._queue.put(("error", OAuthError(f"Error inesperado en OAuth: {error}")))
        finally:
            try:
                server.shutdown()
                server.server_close()
            except Exception:  # noqa: BLE001
                pass
            self._server = None

    def poll(self) -> OAuthResult | None:
        try:
            kind, payload = self._queue.get_nowait()
        except queue.Empty:
            return None
        if kind == "error":
            raise payload
        return payload

    def cancel(self) -> None:
        self._cancelled = True
        server = self._server
        if server is not None:
            try:
                server.event.set()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
