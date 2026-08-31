from __future__ import annotations

import os
import subprocess
import sys

import pytest

import project_paths
from project_paths import external_process_env


@pytest.fixture
def frozen_linux(monkeypatch):
    """Simulate a Nuitka standalone Linux run rooted at tmp_path."""
    monkeypatch.setattr(project_paths, "is_frozen", lambda: True)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(project_paths.os, "pathsep", ":")
    monkeypatch.setattr(
        project_paths, "application_dir", lambda: project_paths.Path("/release/dir")
    )
    return monkeypatch


def test_is_frozen_recognizes_pyinstaller_marker(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delitem(project_paths.__dict__, "__compiled__", raising=False)

    assert project_paths.is_frozen() is True


def test_is_frozen_recognizes_nuitka_compiled_marker(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setitem(project_paths.__dict__, "__compiled__", object())

    assert project_paths.is_frozen() is True


def test_is_frozen_is_false_in_source_mode(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delitem(project_paths.__dict__, "__compiled__", raising=False)

    assert project_paths.is_frozen() is False


def test_nuitka_marker_activates_cv2_library_path_cleanup(monkeypatch, tmp_path):
    release_dir = tmp_path / "release"
    release_dir.mkdir()
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setitem(project_paths.__dict__, "__compiled__", object())
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "executable", str(release_dir / "SZU-Course-Help"))
    monkeypatch.setattr(project_paths.os, "pathsep", ":")
    monkeypatch.setenv("LD_LIBRARY_PATH", ":/opt/hosted-python/lib")

    env = external_process_env()

    assert project_paths.application_dir() == release_dir.resolve()
    assert env["LD_LIBRARY_PATH"] == "/opt/hosted-python/lib"


def test_non_frozen_environment_returned_unchanged(monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/vendor::/usr/local/lib")
    monkeypatch.setattr(project_paths, "is_frozen", lambda: False)
    monkeypatch.setattr(sys, "platform", "linux")

    env = external_process_env()

    assert env["LD_LIBRARY_PATH"] == "/opt/vendor::/usr/local/lib"


def test_non_linux_frozen_environment_returned_unchanged(monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", ":")
    monkeypatch.setattr(project_paths, "is_frozen", lambda: True)
    monkeypatch.setattr(sys, "platform", "darwin")

    env = external_process_env()

    assert env["LD_LIBRARY_PATH"] == ":"


def test_frozen_linux_drops_colon_only_search_path(frozen_linux, monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", ":")

    env = external_process_env()

    assert "LD_LIBRARY_PATH" not in env


def test_frozen_linux_keeps_user_paths_and_drops_release_dir(frozen_linux, monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/vendor::/release/dir:/usr/local/lib")

    env = external_process_env()

    assert env["LD_LIBRARY_PATH"] == "/opt/vendor:/usr/local/lib"


def test_external_process_env_is_idempotent(frozen_linux, monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/vendor::/release/dir")
    once = external_process_env()
    monkeypatch.setenv("LD_LIBRARY_PATH", once["LD_LIBRARY_PATH"])

    twice = external_process_env()

    assert twice["LD_LIBRARY_PATH"] == once["LD_LIBRARY_PATH"]


def test_external_process_env_does_not_mutate_caller_mapping(frozen_linux, monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", ":")
    before = dict(os.environ)

    external_process_env()

    assert os.environ["LD_LIBRARY_PATH"] == ":"  # type: ignore[index]
    assert dict(os.environ) == before


def test_user_preload_helpers_are_preserved(frozen_linux, monkeypatch):
    monkeypatch.setenv("LD_PRELOAD", "/usr/lib/libgpu-compat.so")

    env = external_process_env()

    assert env["LD_PRELOAD"] == "/usr/lib/libgpu-compat.so"


def test_preload_entries_pointing_into_release_dir_are_dropped(frozen_linux, monkeypatch):
    monkeypatch.setenv("LD_PRELOAD", "/release/dir/helper.so::/usr/lib/debug.so")

    env = external_process_env()

    assert env["LD_PRELOAD"] == "/usr/lib/debug.so"


def test_open_external_url_uses_argv_and_sanitized_env(monkeypatch):
    import app

    seen: dict[str, object] = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(app.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(app.subprocess, "run", fake_run)
    monkeypatch.setattr(app, "external_process_env", lambda: {"PATH": "/usr/bin", "HOME": "/root"})
    monkeypatch.setattr(app.sys, "platform", "linux")

    assert app.open_external_url("http://example.com/page") is True
    assert seen["argv"] == ["/usr/bin/xdg-open", "http://example.com/page"]
    kwargs = seen["kwargs"]
    assert "shell" not in kwargs
    assert kwargs["env"] == {"PATH": "/usr/bin", "HOME": "/root"}


def test_open_external_url_falls_back_to_gio(monkeypatch):
    import app

    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1 if argv[0] == "/usr/bin/xdg-open" else 0)

    monkeypatch.setattr(app.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(app.subprocess, "run", fake_run)
    monkeypatch.setattr(app, "external_process_env", dict)
    monkeypatch.setattr(app.sys, "platform", "linux")

    assert app.open_external_url("http://example.com/page") is True
    assert [argv[0] for argv in calls] == ["/usr/bin/xdg-open", "/usr/bin/gio"]
    assert calls[1][1:3] == ["open", "http://example.com/page"]


def test_webvpn_browser_receives_sanitized_env(monkeypatch, tmp_path):
    from services import webvpn_auth_service

    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 4321

        def poll(self) -> int | None:
            return None

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        return FakeProcess()

    monkeypatch.setattr(webvpn_auth_service, "find_browser", lambda: "/usr/bin/chromium")
    monkeypatch.setattr(webvpn_auth_service, "_free_local_port", lambda: 9223)
    monkeypatch.setattr(webvpn_auth_service.tempfile, "mkdtemp", lambda prefix="": str(tmp_path))
    monkeypatch.setattr(webvpn_auth_service.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        webvpn_auth_service,
        "external_process_env",
        lambda: {"PATH": "/usr/bin", "HOME": "/root"},
    )
    monkeypatch.setattr(
        webvpn_auth_service,
        "_open_devtools_page",
        lambda port, url: None,
    )
    manager = webvpn_auth_service.ControlledBrowserManager()
    monkeypatch.setattr(manager, "_browser_alive", lambda: False)
    monkeypatch.setattr(manager, "_start_watcher", lambda: None)

    status = manager.start("http://127.0.0.1:1/auth")

    assert status["state"] == "starting"
    assert captured["env"] == {"PATH": "/usr/bin", "HOME": "/root"}
    argv = captured["argv"]
    assert any(part == "--remote-debugging-port=9223" for part in argv)  # type: ignore[union-attr]
    assert str(argv[-1]).startswith("https://")  # type: ignore[union-attr]
