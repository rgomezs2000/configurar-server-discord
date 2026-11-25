"""Control del proceso de voz separado de la interfaz Tk."""
from __future__ import annotations

import importlib.util
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any


def voice_missing_dependencies() -> list[str]:
    missing: list[str] = []
    for module, package in (("discord", "discord.py"),
                            ("discord.ext.voice_recv", "discord-ext-voice-recv"),
                            ("nacl", "PyNaCl")):
        try:
            if importlib.util.find_spec(module) is None:
                missing.append(package)
        except (ModuleNotFoundError, ValueError):
            missing.append(package)
    return missing


def voice_dependencies_available() -> bool:
    return not voice_missing_dependencies()


class VoiceProcess:
    def __init__(self) -> None:
        self.events: queue.Queue[dict] = queue.Queue()
        self.process: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, token: str) -> None:
        if self.running:
            return
        env = dict(os.environ)
        env["DSS_BOT_TOKEN"] = token
        env["DSS_HOME"] = env.get("DSS_HOME", str(Path.home()))
        self.process = subprocess.Popen(
            [sys.executable, "-m", "dss.voicebot"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, env=env,
            cwd=str(Path(__file__).resolve().parents[2]))
        self._reader = threading.Thread(target=self._read, name="dss-voicebot",
                                        daemon=True)
        self._reader.start()

    def send(self, command: dict) -> None:
        if not self.running or self.process is None or self.process.stdin is None:
            return
        try:
            self.process.stdin.write(json.dumps(command) + "\n")
            self.process.stdin.flush()
        except (OSError, ValueError):
            pass

    def stop(self) -> None:
        self.send({"cmd": "leave"})
        if self.process is not None:
            try:
                self.process.terminate()
            except OSError:
                pass
        self.process = None

    def _read(self) -> None:
        assert self.process is not None
        if self.process.stdout is not None:
            for line in self.process.stdout:
                try:
                    self.events.put(json.loads(line))
                except json.JSONDecodeError:
                    continue
        if self.process.stderr is not None:
            for line in self.process.stderr:
                if line.strip():
                    self.events.put({"event": "log", "message": line.strip()})
        self.events.put({"event": "exit"})
