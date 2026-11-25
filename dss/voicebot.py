"""Proceso de voz visible para Discord Server Studio.

Se ejecuta aparte de Tkinter. Recibe comandos JSON por stdin y responde por stdout.
Requiere las dependencias opcionales de voz:
    pip install "discord.py[voice]" discord-ext-voice-recv PyNaCl
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import discord
    from discord.ext import voice_recv
except ImportError as error:  # pragma: no cover - depende del entorno
    print(json.dumps({"event": "error", "message":
                      "Faltan dependencias de voz: instala discord.py[voice], "
                      f"discord-ext-voice-recv y PyNaCl ({error})."}), flush=True)
    raise SystemExit(2) from error


def emit(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False), flush=True)


class VoiceBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.voice_states = True
        super().__init__(intents=intents)
        self.voice: Any = None
        self.recording_path: Path | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._sink: Any = None

    async def on_ready(self) -> None:
        self._loop = asyncio.get_running_loop()
        emit("ready", user=str(self.user), user_id=str(self.user.id))
        threading.Thread(target=self._read_commands, daemon=True).start()

    def _read_commands(self) -> None:
        for line in sys.stdin:
            try:
                command = json.loads(line)
            except json.JSONDecodeError:
                emit("error", message="Comando IPC inválido.")
                continue
            if self._loop is not None:
                asyncio.run_coroutine_threadsafe(self._handle(command), self._loop)

    async def _handle(self, command: dict) -> None:
        name = str(command.get("cmd") or "")
        try:
            if name == "join":
                await self._join(str(command.get("guild_id")), str(command.get("channel_id")))
            elif name == "leave":
                await self._leave()
            elif name == "record_start":
                await self._record_start()
            elif name == "record_stop":
                await self._record_stop()
            elif name == "ping":
                emit("pong")
            else:
                emit("error", message=f"Comando desconocido: {name}")
        except Exception as error:  # noqa: BLE001 - se informa a la UI
            emit("error", message=str(error))

    async def _join(self, guild_id: str, channel_id: str) -> None:
        guild = self.get_guild(int(guild_id))
        if guild is None:
            raise RuntimeError("El bot no está en ese servidor.")
        channel = guild.get_channel(int(channel_id))
        if channel is None:
            raise RuntimeError("No se encontró el canal de voz.")
        if self.voice is not None:
            await self._leave()
        self.voice = await channel.connect(cls=voice_recv.VoiceRecvClient,
                                           self_deaf=False, self_mute=False)
        await channel.send(
            "🔴 **Aviso de grabación**: si se activa la grabación en esta sala, "
            "se avisará aquí. Si no estás de acuerdo, sal de la sala. "
            "La grabación solo se inicia con el botón de la app.")
        emit("joined", channel_id=str(channel.id), channel=channel.name)

    async def _leave(self) -> None:
        await self._record_stop()
        if self.voice is not None:
            await self.voice.disconnect(force=True)
            self.voice = None
            emit("left")

    async def _record_start(self) -> None:
        if self.voice is None:
            raise RuntimeError("Primero entra a una sala de voz.")
        if self.recording_path is not None:
            raise RuntimeError("Ya hay una grabación en curso.")
        root = Path(os.environ.get("DSS_HOME", ".")) / "grabaciones"
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.recording_path = root / f"llamada-{stamp}.wav"
        self._sink = voice_recv.WaveSink(str(self.recording_path))
        self.voice.listen(self._sink)
        emit("recording", file=str(self.recording_path))

    async def _record_stop(self) -> None:
        if self.voice is not None and self.recording_path is not None:
            self.voice.stop_listening()
        if self.recording_path is None:
            return
        path = self.recording_path
        self.recording_path = None
        self._sink = None
        final = _to_ogg(path)
        emit("recorded", file=str(final))

    async def close(self) -> None:
        if self.voice is not None:
            await self._record_stop()
            await self.voice.disconnect(force=True)
            self.voice = None
        await super().close()


def _to_ogg(path: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return path
    target = path.with_suffix(".ogg")
    result = subprocess.run(
        [ffmpeg, "-y", "-i", str(path), "-c:a", "libopus", "-b:a", "48k", str(target)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if result.returncode == 0 and target.exists():
        try:
            path.unlink()
        except OSError:
            pass
        return target
    return path


def main() -> None:
    token = os.environ.get("DSS_BOT_TOKEN", "").strip()
    if not token:
        emit("error", message="Falta el token del bot.")
        raise SystemExit(2)
    bot = VoiceBot()
    try:
        bot.run(token, log_handler=None)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
