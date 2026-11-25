"""Pruebas del flujo OAuth2 (PKCE, callback local y almacenamiento de sesión)."""
from __future__ import annotations

import os
import shutil
import socket
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DSS_HOME"] = str(ROOT / "_testdata_oauth")
shutil.rmtree(os.environ["DSS_HOME"], ignore_errors=True)

from dss.models import GuildSummary, User  # noqa: E402
from dss.oauth import (OAuthError, OAuthFlow, OAuthTokens, build_authorize_url,  # noqa: E402
                       bot_invite_url, parse_redirect_uri, pkce_pair)
from dss.store import TokenStore  # noqa: E402

RESULTS: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("OK    " if condition else "FALLO ") + name + (f"  {detail}" if detail else ""))
    if not condition:
        RESULTS.append(name)


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def fake_exchange(client_id, redirect_uri, code, verifier) -> OAuthTokens:
    assert code == "code-123", code
    return OAuthTokens("access-token", "refresh-token", time.time() + 3600, "identify guilds")


def fake_identity(access_token) -> tuple[User, list[GuildSummary]]:
    assert access_token == "access-token"
    return (User(id="42", username="luna", global_name="Luna"),
            [GuildSummary(id="7", name="Estudio", owner=True, permissions=-1)])


def wait_result(flow: OAuthFlow, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = flow.poll()
        if result is not None:
            return result
        time.sleep(0.05)
    raise AssertionError("sin resultado OAuth")


def main() -> None:
    verifier, challenge = pkce_pair()
    check("PKCE genera verifier", 43 <= len(verifier) <= 128, str(len(verifier)))
    check("PKCE challenge distinto", challenge != verifier and len(challenge) >= 43)

    host, port, path = parse_redirect_uri("http://127.0.0.1:5000/callback")
    check("parse redirect", (host, port, path) == ("127.0.0.1", 5000, "/callback"))
    try:
        parse_redirect_uri("https://evil.example/callback")
        check("rechaza host externo", False)
    except OAuthError:
        check("rechaza host externo", True)

    url = build_authorize_url("123", "http://127.0.0.1:5000/callback", "state-1", challenge)
    for fragment in ("client_id=123", "code_challenge=", "state=state-1",
                     "scope=identify%20guilds", "redirect_uri=", "S256"):
        check(f"URL contiene {fragment}", fragment in url)
    invite = bot_invite_url("123", "999")
    check("invitación por servidor", "guild_id=999" in invite
          and "disable_guild_select=true" in invite and "scope=bot" in invite)

    # Flujo completo con callback simulado.
    callback_port = free_port()
    redirect = f"http://127.0.0.1:{callback_port}/callback"
    flow = OAuthFlow("123", redirect, timeout=10, exchanger=fake_exchange,
                     identity=fake_identity)
    flow.start()
    with urllib.request.urlopen(
            f"{redirect}?code=code-123&state={flow.state}", timeout=5) as response:
        check("callback responde HTML", b"Discord Server Studio" in response.read())
    result = wait_result(flow)
    check("OAuth devuelve usuario", result.user.id == "42" and result.user.display_name == "Luna")
    check("OAuth devuelve servidores", len(result.guilds) == 1
          and result.guilds[0].name == "Estudio")
    check("OAuth devuelve tokens", result.tokens.access_token == "access-token"
          and result.tokens.refresh_token == "refresh-token")

    # Estado incorrecto (CSRF).
    bad_port = free_port()
    bad_redirect = f"http://127.0.0.1:{bad_port}/callback"
    bad_flow = OAuthFlow("123", bad_redirect, timeout=10, exchanger=fake_exchange,
                         identity=fake_identity)
    bad_flow.start()
    try:
        urllib.request.urlopen(f"{bad_redirect}?code=code-123&state=otro", timeout=5)
    except Exception:  # noqa: BLE001
        pass
    try:
        wait_result(bad_flow)
        check("rechaza state incorrecto", False)
    except OAuthError:
        check("rechaza state incorrecto", True)

    # Sesión cifrada.
    store = TokenStore()
    payload = {"oauth": {"access_token": "a", "refresh_token": "r"},
               "bot_token": "b", "client_id": "123",
               "redirect_uri": redirect}
    check("guarda sesión", store.save_session(payload))
    loaded = store.load_session()
    check("recupera sesión", loaded is not None
          and loaded.get("bot_token") == "b"
          and loaded.get("oauth", {}).get("access_token") == "a")
    store.clear()
    check("borra sesión", store.load_session() is None)

    total = 19
    print(f"\nRESULTADO: {total - len(RESULTS)}/{total} correctas")
    if RESULTS:
        print("FALLOS:", RESULTS)
        sys.exit(1)


if __name__ == "__main__":
    main()
