from __future__ import annotations

import threading
import time

from services.session_manager import SessionManager


def test_keepalive_has_single_owner_and_runs_only_for_active_work():
    manager = SessionManager()
    active = False
    callback_called = threading.Event()

    assert manager.start_keepalive(
        callback_called.set,
        lambda: active,
        interval_seconds=1,
    )
    assert manager.keepalive_running is True
    assert (
        manager.start_keepalive(
            callback_called.set,
            lambda: True,
            interval_seconds=1,
        )
        is False
    )
    try:
        time.sleep(1.1)
        assert callback_called.is_set() is False
        active = True
        assert callback_called.wait(timeout=1.5)
    finally:
        manager.stop_keepalive()
    assert manager.keepalive_running is False


def test_recovery_guard_serializes_automatic_login_owners():
    manager = SessionManager()
    first_entered = threading.Event()
    release_first = threading.Event()
    order = []

    def first():
        with manager.recovery_guard():
            order.append("first-enter")
            first_entered.set()
            assert release_first.wait(timeout=2)
            order.append("first-exit")

    def second():
        assert first_entered.wait(timeout=2)
        with manager.recovery_guard():
            order.append("second-enter")

    first_thread = threading.Thread(target=first)
    second_thread = threading.Thread(target=second)
    first_thread.start()
    second_thread.start()
    assert first_entered.wait(timeout=2)
    time.sleep(0.05)
    assert order == ["first-enter"]
    assert manager.recovery_in_progress is True
    release_first.set()
    first_thread.join(timeout=2)
    second_thread.join(timeout=2)

    assert order == ["first-enter", "first-exit", "second-enter"]
    assert manager.recovery_in_progress is False


def test_keepalive_cannot_restart_while_stopped_callback_is_still_running():
    manager = SessionManager()
    callback_entered = threading.Event()
    release_callback = threading.Event()

    def blocking_callback():
        callback_entered.set()
        assert release_callback.wait(timeout=3)

    assert manager.start_keepalive(
        blocking_callback,
        lambda: True,
        interval_seconds=1,
    )
    assert callback_entered.wait(timeout=1.5)

    manager.stop_keepalive(timeout=0)
    assert manager.start_keepalive(lambda: None, lambda: True, interval_seconds=1) is False

    release_callback.set()
    manager.stop_keepalive(timeout=2)
    assert manager.start_keepalive(lambda: None, lambda: True, interval_seconds=1)
    manager.stop_keepalive()
