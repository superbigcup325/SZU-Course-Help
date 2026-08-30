from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from Crypto.PublicKey import ECC

import project_paths
from services import data_migration


def test_source_mode_keeps_project_local_data_and_keys(monkeypatch, tmp_path):
    monkeypatch.delenv("COURSE_SELECT_DATA_DIR", raising=False)
    monkeypatch.delenv("COURSE_SELECT_KEY_DIR", raising=False)
    monkeypatch.delattr(project_paths.sys, "frozen", raising=False)
    monkeypatch.setattr(project_paths, "PROJECT_ROOT", tmp_path)

    assert project_paths.data_dir() == tmp_path
    assert project_paths.key_dir() == tmp_path


def test_environment_overrides_have_highest_priority(monkeypatch, tmp_path):
    data = tmp_path / "custom-data"
    keys = tmp_path / "custom-keys"
    monkeypatch.setenv("COURSE_SELECT_DATA_DIR", str(data))
    monkeypatch.setenv("COURSE_SELECT_KEY_DIR", str(keys))
    monkeypatch.setattr(project_paths.sys, "frozen", True, raising=False)

    assert project_paths.data_dir() == data.resolve()
    assert project_paths.key_dir() == keys.resolve()


def test_frozen_platform_data_directories(monkeypatch, tmp_path):
    monkeypatch.delenv("COURSE_SELECT_DATA_DIR", raising=False)
    monkeypatch.setattr(project_paths.sys, "frozen", True, raising=False)

    monkeypatch.setattr(project_paths.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    assert project_paths.user_data_dir() == (tmp_path / "roaming" / "SZU-Course-Help")

    monkeypatch.setattr(project_paths.sys, "platform", "darwin")
    monkeypatch.setattr(project_paths.Path, "home", lambda: tmp_path)
    assert project_paths.user_data_dir() == (
        tmp_path / "Library" / "Application Support" / "SZU-Course-Help"
    )

    monkeypatch.setattr(project_paths.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert project_paths.user_data_dir() == (tmp_path / "xdg" / "SZU-Course-Help")


def _write_key_pair(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    private = ECC.generate(curve="Ed25519")
    (directory / data_migration.PRIVATE_KEY_NAME).write_text(
        private.export_key(format="PEM"), encoding="utf-8"
    )
    (directory / data_migration.PUBLIC_KEY_NAME).write_text(
        private.public_key().export_key(format="PEM"), encoding="utf-8"
    )


def _configure_migration(monkeypatch, source: Path, target: Path) -> None:
    monkeypatch.setenv("COURSE_SELECT_LEGACY_DATA_DIR", str(source))
    monkeypatch.delenv("COURSE_SELECT_DB_PATH", raising=False)
    monkeypatch.setattr(data_migration, "data_dir", lambda: target)
    monkeypatch.setattr(data_migration, "key_dir", lambda: target / "keys")
    monkeypatch.setattr(data_migration, "application_dir", lambda: source)
    monkeypatch.setattr(data_migration, "is_frozen", lambda: True)


def test_migration_preserves_wal_rows_and_key_pair(monkeypatch, tmp_path):
    source = tmp_path / "old"
    target = tmp_path / "new"
    source.mkdir()
    _write_key_pair(source)
    database_path = source / data_migration.DATABASE_NAME
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
    connection.execute("INSERT INTO sample VALUES ('from-wal')")
    connection.commit()

    _configure_migration(monkeypatch, source, target)
    result = data_migration.migrate_legacy_runtime_data(interactive=False)
    connection.close()

    assert result.changed is True
    assert set(result.migrated) == {data_migration.DATABASE_NAME, "Card Key identity"}
    with sqlite3.connect(target / data_migration.DATABASE_NAME) as migrated:
        assert migrated.execute("SELECT value FROM sample").fetchone() == ("from-wal",)
    assert (target / "keys" / data_migration.PRIVATE_KEY_NAME).is_file()
    assert (target / "keys" / data_migration.PUBLIC_KEY_NAME).is_file()


def test_migration_never_overwrites_existing_database(monkeypatch, tmp_path):
    source = tmp_path / "old"
    target = tmp_path / "new"
    source.mkdir()
    target.mkdir()
    (source / data_migration.DATABASE_NAME).write_bytes(b"legacy")
    current = target / data_migration.DATABASE_NAME
    current.write_bytes(b"current")
    _configure_migration(monkeypatch, source, target)

    result = data_migration.migrate_legacy_runtime_data(interactive=False)

    assert current.read_bytes() == b"current"
    assert data_migration.DATABASE_NAME in result.skipped


def test_migration_accepts_only_account_scoped_v2_cache(monkeypatch, tmp_path):
    source = tmp_path / "old"
    target = tmp_path / "new"
    source.mkdir()
    scope_digest = "a" * 64
    cache = {
        "schema": 2,
        "entries": {
            f"{scope_digest}:TJKC:1:10": {
                "scope_digest": scope_digest,
                "course_type": "TJKC",
                "payload": {"total_count": 1, "courses": [{"course_name": "缓存课"}]},
            }
        },
    }
    (source / data_migration.CACHE_NAME).write_text(
        json.dumps(cache, ensure_ascii=False),
        encoding="utf-8",
    )
    _configure_migration(monkeypatch, source, target)

    result = data_migration.migrate_legacy_runtime_data(interactive=False)

    assert data_migration.CACHE_NAME in result.migrated
    migrated = json.loads((target / data_migration.CACHE_NAME).read_text(encoding="utf-8"))
    assert migrated == cache


def test_migration_rejects_unscoped_or_sensitive_cache(monkeypatch, tmp_path):
    source = tmp_path / "old"
    target = tmp_path / "new"
    source.mkdir()
    unsafe = {
        "schema": 2,
        "entries": {
            "unscoped": {
                "student_id": "2024110122",
                "payload": {"total_count": 1, "courses": [{"course_name": "泄漏课"}]},
            }
        },
    }
    (source / data_migration.CACHE_NAME).write_text(
        json.dumps(unsafe, ensure_ascii=False),
        encoding="utf-8",
    )
    _configure_migration(monkeypatch, source, target)

    result = data_migration.migrate_legacy_runtime_data(interactive=False)

    assert not (target / data_migration.CACHE_NAME).exists()
    assert any("账号隔离" in warning for warning in result.warnings)


def test_migration_rejects_nested_sensitive_cache_data(monkeypatch, tmp_path):
    source = tmp_path / "old"
    target = tmp_path / "new"
    source.mkdir()
    scope_digest = "b" * 64
    unsafe = {
        "schema": 2,
        "entries": {
            f"{scope_digest}:TJKC:1:10": {
                "scope_digest": scope_digest,
                "payload": {
                    "total_count": 1,
                    "courses": [{"course_name": "泄漏课", "token": "secret"}],
                },
            }
        },
    }
    (source / data_migration.CACHE_NAME).write_text(
        json.dumps(unsafe, ensure_ascii=False), encoding="utf-8"
    )
    _configure_migration(monkeypatch, source, target)

    result = data_migration.migrate_legacy_runtime_data(interactive=False)

    assert not (target / data_migration.CACHE_NAME).exists()
    assert any("敏感字段" in warning for warning in result.warnings)


def test_multiple_candidates_require_explicit_choice_when_noninteractive(monkeypatch, tmp_path):
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    (first / data_migration.DATABASE_NAME).touch()
    (second / data_migration.DATABASE_NAME).touch()
    monkeypatch.delenv("COURSE_SELECT_LEGACY_DATA_DIR", raising=False)

    assert data_migration.choose_legacy_data_dir([first, second], interactive=False) is None


def test_migration_lock_serializes_threads(tmp_path):
    lock_path = tmp_path / ".migration.lock"
    entered: list[int] = []
    first_inside = threading.Event()
    release_first = threading.Event()

    def worker(index: int) -> None:
        with data_migration.MigrationLock(lock_path, timeout=2):
            entered.append(index)
            if index == 1:
                first_inside.set()
                release_first.wait(timeout=1)

    first = threading.Thread(target=worker, args=(1,))
    second = threading.Thread(target=worker, args=(2,))
    first.start()
    first_inside.wait(timeout=1)
    second.start()
    release_first.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert entered == [1, 2]
