"""Ejecución de llamadas de red fuera del hilo de la interfaz."""
from __future__ import annotations

import queue
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

Callback = Callable[[Any], None]


class TaskRunner:
    """Lanza tareas en hilos y entrega el resultado en el hilo de Tk."""

    def __init__(self, widget: Any, workers: int = 8, poll_ms: int = 25):
        self._widget = widget
        self._queue: "queue.Queue[tuple[Callback | None, Callback | None, Any, BaseException | None]]" = queue.Queue()
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="dss-net")
        self._closed = False
        self._poll_ms = poll_ms
        self._after_id: str | None = None
        self._schedule()

    # -- API ---------------------------------------------------------------- #
    def run(self, func: Callable[[], Any], on_done: Callback | None = None,
            on_error: Callable[[BaseException], None] | None = None) -> None:
        def worker() -> None:
            try:
                result = func()
            except BaseException as exc:  # noqa: BLE001 - se entrega a la UI
                self._queue.put((on_done, on_error, None, exc))
            else:
                self._queue.put((on_done, on_error, result, None))

        try:
            self._pool.submit(worker)
        except RuntimeError:
            pass

    def close(self) -> None:
        self._closed = True
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except Exception:  # noqa: BLE001
                pass
            self._after_id = None
        try:
            self._pool.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            self._pool.shutdown(wait=False)

    # -- interno ------------------------------------------------------------ #
    def _schedule(self) -> None:
        if self._closed:
            return
        try:
            self._after_id = self._widget.after(self._poll_ms, self._drain)
        except Exception:  # noqa: BLE001 - ventana destruida
            self._closed = True

    def _drain(self) -> None:
        self._after_id = None
        if self._closed:
            return
        for _ in range(40):
            try:
                on_done, on_error, result, error = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                if error is not None:
                    if on_error is not None:
                        on_error(error)
                    else:
                        traceback.print_exception(type(error), error, error.__traceback__)
                elif on_done is not None:
                    on_done(result)
            except Exception:  # noqa: BLE001 - un callback roto no debe cerrar la app
                traceback.print_exc()
        self._schedule()


class Debouncer:
    """Agrupa eventos rápidos (por ejemplo, teclear en un buscador)."""

    def __init__(self, widget: Any, delay_ms: int = 250):
        self._widget = widget
        self._delay = delay_ms
        self._after_id: str | None = None

    def call(self, func: Callable[[], None]) -> None:
        self.cancel()
        try:
            self._after_id = self._widget.after(self._delay, func)
        except Exception:  # noqa: BLE001
            self._after_id = None

    def cancel(self) -> None:
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except Exception:  # noqa: BLE001
                pass
            self._after_id = None


class Flag:
    """Bandera simple para descartar respuestas antiguas."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value = 0

    def next(self) -> int:
        with self._lock:
            self._value += 1
            return self._value

    def is_current(self, token: int) -> bool:
        with self._lock:
            return token == self._value
