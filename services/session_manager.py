"""Coordinate keep-alive and OCR recovery for the single school session."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class SessionManager:
    """Own the process-wide recovery lock and optional keep-alive worker."""

    def __init__(self) -> None:
        self._recovery_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._keepalive_thread: threading.Thread | None = None

    @contextmanager
    def recovery_guard(self) -> Iterator[None]:
        """Serialize every OCR recovery caller behind one ownership lock."""
        with self._recovery_lock:
            yield

    @property
    def recovery_in_progress(self) -> bool:
        return self._recovery_lock.locked()

    @property
    def keepalive_running(self) -> bool:
        """Return whether the single keep-alive owner is still alive."""
        with self._lifecycle_lock:
            return bool(self._keepalive_thread and self._keepalive_thread.is_alive())

    def start_keepalive(
        self,
        callback: Callable[[], None],
        should_run: Callable[[], bool],
        *,
        interval_seconds: float,
    ) -> bool:
        """Start one daemon that runs only while authenticated work is active."""
        interval = max(1.0, float(interval_seconds))
        with self._lifecycle_lock:
            if self._keepalive_thread and self._keepalive_thread.is_alive():
                return False
            self._stop_event.clear()

            def loop() -> None:
                while not self._stop_event.wait(interval):
                    if not should_run():
                        continue
                    try:
                        callback()
                    except Exception:
                        logger.exception("Session keep-alive callback failed")

            self._keepalive_thread = threading.Thread(
                target=loop,
                name="school-session-keep-alive",
                daemon=True,
            )
            self._keepalive_thread.start()
            return True

    def stop_keepalive(self, timeout: float = 2.0) -> None:
        """Stop the keep-alive worker without touching the school session."""
        with self._lifecycle_lock:
            thread = self._keepalive_thread
            self._stop_event.set()
        if thread and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, timeout))
        with self._lifecycle_lock:
            if self._keepalive_thread is thread and (thread is None or not thread.is_alive()):
                self._keepalive_thread = None


session_manager = SessionManager()

__all__ = ["SessionManager", "session_manager"]
