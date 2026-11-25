"""Cliente mínimo del Gateway de Discord (solo biblioteca estándar).

Entrega eventos a la UI mediante una cola; no usa self-bot y no graba audio.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import queue
import socket
import ssl
import struct
import threading
import time
from typing import Any, Callable
from urllib.parse import urlparse

GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"
INTENTS = (1 << 0) | (1 << 7)  # GUILDS | GUILD_VOICE_STATES


class DiscordGateway:
    def __init__(self, token: str) -> None:
        self.token = token
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.status = "off"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sock: socket.socket | None = None
        self._buffer = b""
        self._sequence: int | None = None
        self._heartbeat_interval = 0.0
        self._heartbeat_thread: threading.Thread | None = None
        self._send_lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="dss-gateway",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._sock is not None:
                self._sock.close()
        except OSError:
            pass
        if self._thread:
            self._thread.join(timeout=2)

    def _put(self, event: str, data: Any = None) -> None:
        self.events.put((event, data))

    def _run(self) -> None:
        delay = 2
        while not self._stop.is_set():
            try:
                self._connect()
                delay = 2
            except Exception as error:  # noqa: BLE001 - el gateway reintenta
                self.status = "error"
                self._put("status", f"Gateway: {error}")
            if self._stop.is_set():
                break
            time.sleep(delay)
            delay = min(30, delay * 2)
        self.status = "off"

    def _connect(self) -> None:
        parsed = urlparse(GATEWAY_URL)
        raw = socket.create_connection((parsed.hostname, 443), timeout=20)
        context = ssl.create_default_context()
        sock = context.wrap_socket(raw, server_hostname=parsed.hostname)
        self._sock = sock
        self._buffer = b""
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path or "/"
        request = (
            f"GET {path}?{parsed.query} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
            "User-Agent: DiscordServerStudio/1.0\r\n\r\n"
        )
        sock.sendall(request.encode("ascii"))
        header = b""
        while b"\r\n\r\n" not in header:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("El Gateway cerró el handshake.")
            header += chunk
        head, _, rest = header.partition(b"\r\n\r\n")
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError("El Gateway rechazó la conexión WebSocket.")
        expected = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
        ).decode("ascii")
        if expected.encode() not in head:
            raise ConnectionError("Firma WebSocket inválida.")
        self._buffer = rest
        sock.settimeout(None)
        self.status = "connected"
        self._put("status", "Conectado al Gateway")
        while not self._stop.is_set():
            opcode, payload = self._read_frame()
            if opcode == 1:
                self._dispatch(payload)
            elif opcode == 8:
                raise ConnectionError("Gateway cerró la conexión.")
            elif opcode == 9:
                self._send_frame(10, payload)

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        with self._send_lock:
            if self._sock is None:
                return
            header = bytearray([0x80 | opcode])
            length = len(payload)
            if length < 126:
                header.append(0x80 | length)
            elif length < 65536:
                header.append(0x80 | 126)
                header.extend(struct.pack("!H", length))
            else:
                header.append(0x80 | 127)
                header.extend(struct.pack("!Q", length))
            mask = os.urandom(4)
            header.extend(mask)
            masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
            self._sock.sendall(bytes(header) + masked)

    def _recv_exact(self, count: int) -> bytes:
        while len(self._buffer) < count:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise ConnectionError("Gateway desconectado.")
            self._buffer += chunk
        data, self._buffer = self._buffer[:count], self._buffer[count:]
        return data

    def _read_frame(self) -> tuple[int, bytes]:
        first, second = self._recv_exact(2)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else b""
        payload = self._recv_exact(length)
        if masked:
            payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        return opcode, payload

    def _dispatch(self, payload: bytes) -> None:
        try:
            message = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        op = message.get("op")
        data = message.get("d")
        if op == 10:
            self._heartbeat_interval = float(data.get("heartbeat_interval", 41250)) / 1000
            self._start_heartbeat()
            self._identify()
            return
        if op == 11:
            return
        if op == 1:
            self._heartbeat()
            return
        if op == 0:
            self._sequence = message.get("s", self._sequence)
            self._dispatch_event(str(message.get("t") or ""), data)
            return
        if op in (7, 9):
            raise ConnectionError("Gateway solicita reconexión.")

    def _identify(self) -> None:
        self._send_json({
            "op": 2,
            "d": {
                "token": self.token,
                "intents": INTENTS,
                "properties": {"os": os.name, "browser": "DiscordServerStudio",
                               "device": "DiscordServerStudio"},
            },
        })

    def _start_heartbeat(self) -> None:
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return

        def beat() -> None:
            while not self._stop.is_set():
                time.sleep(self._heartbeat_interval)
                if self._stop.is_set():
                    return
                try:
                    self._heartbeat()
                except Exception:  # noqa: BLE001
                    return

        self._heartbeat_thread = threading.Thread(target=beat, name="dss-heartbeat",
                                                  daemon=True)
        self._heartbeat_thread.start()

    def _heartbeat(self) -> None:
        self._send_json({"op": 1, "d": self._sequence})

    def _send_json(self, payload: dict) -> None:
        self._send_frame(1, json.dumps(payload).encode("utf-8"))

    def _dispatch_event(self, name: str, data: Any) -> None:
        if name == "READY":
            self.status = "ready"
            self._put("status", "Gateway listo")
        self._put(name, data)
