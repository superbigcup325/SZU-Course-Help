"""One-time migration of legacy release data into the stable user data directory."""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import sys
import tempfile
import time
from collections.abc import Callable
from contextlib import closing, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from Crypto.PublicKey import ECC

from project_paths import application_dir, data_dir, is_frozen, key_dir

logger = logging.getLogger(__name__)

PRIVATE_KEY_NAME = "card_signing_private.pem"
PUBLIC_KEY_NAME = "card_signing_public.pem"
DATABASE_NAME = "course_enroll.db"
CACHE_NAME = "course_catalog_cache_v2.json"
KNOWN_ARTIFACTS = (DATABASE_NAME, PRIVATE_KEY_NAME, PUBLIC_KEY_NAME, CACHE_NAME)
MAX_CACHE_MIGRATION_BYTES = 32 * 1024 * 1024


@dataclass(slots=True)
class MigrationResult:
    """Describe a migration without exposing credential or key contents."""

    source: Path | None = None
    migrated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.migrated)


class MigrationLock:
    """Small cross-platform advisory file lock for concurrent first starts."""

    def __init__(self, path: Path, timeout: float = 10.0) -> None:
        self.path = path
        self.timeout = max(0.0, float(timeout))
        self._handle: BinaryIO | None = None

    def __enter__(self) -> MigrationLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self._lock(handle)
                self._handle = handle
                return self
            except OSError:
                if time.monotonic() >= deadline:
                    handle.close()
                    raise TimeoutError("等待旧版数据迁移锁超时") from None
                time.sleep(0.05)

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._handle is None:
            return
        with suppress(OSError):
            self._unlock(self._handle)
        self._handle.close()
        self._handle = None

    @staticmethod
    def _lock(handle: BinaryIO) -> None:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock(handle: BinaryIO) -> None:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _contains_legacy_data(path: Path) -> bool:
    return path.is_dir() and any((path / name).is_file() for name in KNOWN_ARTIFACTS)


def discover_legacy_data_dirs() -> list[Path]:
    """Return conservative legacy candidates in deterministic priority order."""
    target = data_dir().resolve()
    candidates: list[Path] = []

    configured = os.getenv("COURSE_SELECT_LEGACY_DATA_DIR", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser().resolve())

    install = application_dir().resolve()
    if install != target:
        candidates.append(install)

    if is_frozen():
        with suppress(OSError):
            for sibling in sorted(install.parent.iterdir(), key=lambda item: item.name.lower()):
                if not sibling.is_dir() or sibling.resolve() in {install, target}:
                    continue
                lowered = sibling.name.lower()
                if lowered.startswith("szu-course-help") or lowered.startswith("courseenroll"):
                    candidates.append(sibling.resolve())

    unique: list[Path] = []
    for candidate in candidates:
        if candidate != target and candidate not in unique and _contains_legacy_data(candidate):
            unique.append(candidate)
    return unique


def choose_legacy_data_dir(
    candidates: list[Path],
    *,
    interactive: bool,
    input_fn: Callable[[str], str] = input,
) -> Path | None:
    """Choose a candidate, refusing to guess when several old releases exist."""
    if not candidates:
        return None
    configured = os.getenv("COURSE_SELECT_LEGACY_DATA_DIR", "").strip()
    if configured:
        explicit = Path(configured).expanduser().resolve()
        return explicit if explicit in candidates else None
    if len(candidates) == 1:
        return candidates[0]
    if not interactive:
        logger.warning(
            "Found multiple legacy data directories; set COURSE_SELECT_LEGACY_DATA_DIR to choose one"
        )
        return None

    print("\n检测到多个旧版数据目录，请选择需要迁移的一项：")
    for index, candidate in enumerate(candidates, start=1):
        print(f"  {index}. {candidate}")
    print("  0. 不迁移")
    try:
        choice = str(input_fn("请选择序号: ")).strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not choice.isdigit():
        return None
    index = int(choice)
    return candidates[index - 1] if 1 <= index <= len(candidates) else None


def _target_database_path() -> Path:
    configured = os.getenv("COURSE_SELECT_DB_PATH", "").strip()
    return (
        Path(configured).expanduser().resolve()
        if configured
        else (data_dir() / DATABASE_NAME).resolve()
    )


def _sqlite_backup(source: Path, target: Path) -> None:
    """Copy a SQLite database through its backup API so WAL content is included."""
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    with suppress(FileNotFoundError):
        temporary.unlink()
    try:
        source_uri = f"file:{source.as_posix()}?mode=ro"
        with (
            closing(sqlite3.connect(source_uri, uri=True)) as source_db,
            closing(sqlite3.connect(temporary)) as target_db,
        ):
            source_db.backup(target_db)
            integrity = target_db.execute("PRAGMA integrity_check").fetchone()
            if integrity != ("ok",):
                raise sqlite3.DatabaseError("迁移后的数据库完整性检查失败")
        os.replace(temporary, target)
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()


def _validated_key_pair(source: Path) -> tuple[bytes, bytes] | None:
    private_path = source / PRIVATE_KEY_NAME
    public_path = source / PUBLIC_KEY_NAME
    if not private_path.is_file() and not public_path.is_file():
        return None
    if not private_path.is_file() or not public_path.is_file():
        raise ValueError("旧版卡密公私钥不完整，已跳过迁移")
    private_bytes = private_path.read_bytes()
    public_bytes = public_path.read_bytes()
    passphrase = os.getenv("COURSE_SELECT_KEY_PASSPHRASE", "") or None
    private_key = ECC.import_key(private_bytes, passphrase=passphrase)
    public_key = ECC.import_key(public_bytes)
    if not private_key.has_private() or private_key.curve != "Ed25519":
        raise ValueError("旧版卡密私钥格式不正确，已跳过迁移")
    if public_key.curve != "Ed25519":
        raise ValueError("旧版卡密公钥格式不正确，已跳过迁移")
    if private_key.public_key().export_key(format="DER") != public_key.public_key().export_key(
        format="DER"
    ):
        raise ValueError("旧版卡密公私钥不匹配，已跳过迁移")
    return private_bytes, public_bytes


def _atomic_copy_bytes(target: Path, content: bytes, mode: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        with suppress(OSError):
            os.chmod(temporary, mode)
        os.replace(temporary, target)
        with suppress(OSError):
            os.chmod(target, mode)
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()


def _validated_cache_bytes(source: Path) -> bytes:
    """Accept only the account-scoped v2 cache, never PR7's unscoped format."""
    if source.stat().st_size > MAX_CACHE_MIGRATION_BYTES:
        raise ValueError("旧版课程缓存过大，已跳过迁移")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("旧版课程缓存格式无效，已跳过迁移") from exc
    entries = value.get("entries") if isinstance(value, dict) else None
    if not isinstance(value, dict) or value.get("schema") != 2 or not isinstance(entries, dict):
        raise ValueError("旧版课程缓存不是安全的账号隔离格式，已跳过迁移")
    forbidden_fields = {"student_id", "password", "token", "cookie", "card_key"}

    def contains_sensitive_field(item: object) -> bool:
        if isinstance(item, dict):
            return any(
                str(name).strip().lower() in forbidden_fields or contains_sensitive_field(child)
                for name, child in item.items()
            )
        if isinstance(item, list):
            return any(contains_sensitive_field(child) for child in item)
        return False

    for key, entry in entries.items():
        if not isinstance(key, str) or not isinstance(entry, dict):
            raise ValueError("旧版课程缓存条目无效，已跳过迁移")
        scope_digest = str(entry.get("scope_digest") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", scope_digest):
            raise ValueError("旧版课程缓存缺少账号隔离范围，已跳过迁移")
        if not key.startswith(f"{scope_digest}:"):
            raise ValueError("旧版课程缓存键与账号隔离范围不匹配，已跳过迁移")
        if contains_sensitive_field(entry):
            raise ValueError("旧版课程缓存包含敏感字段，已跳过迁移")
        payload = entry.get("payload")
        courses = payload.get("courses") if isinstance(payload, dict) else None
        if not isinstance(courses, list) or not all(isinstance(item, dict) for item in courses):
            raise ValueError("旧版课程缓存课程数据无效，已跳过迁移")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _migrate_key_pair(source: Path, result: MigrationResult) -> None:
    pair = _validated_key_pair(source)
    if pair is None:
        return
    private_bytes, public_bytes = pair
    private_target = key_dir() / PRIVATE_KEY_NAME
    public_target = key_dir() / PUBLIC_KEY_NAME

    if private_target.exists() and private_target.read_bytes() != private_bytes:
        result.skipped.append("Card Key identity (target private key already exists)")
        return
    if public_target.exists() and public_target.read_bytes() != public_bytes:
        result.skipped.append("Card Key identity (target public key already exists)")
        return

    # Public-first ordering lets an interrupted copy resume safely. KeyManager
    # refuses to generate a new private key while only the public half exists.
    if not public_target.exists():
        _atomic_copy_bytes(public_target, public_bytes, 0o644)
    if not private_target.exists():
        _atomic_copy_bytes(private_target, private_bytes, 0o600)
    result.migrated.append("Card Key identity")


def migrate_legacy_runtime_data(
    *, interactive: bool | None = None, input_fn: Callable[[str], str] = input
) -> MigrationResult:
    """Migrate one selected legacy directory before runtime services import the DB."""
    result = MigrationResult()
    candidates = discover_legacy_data_dirs()
    source = choose_legacy_data_dir(
        candidates,
        interactive=bool(sys.stdin.isatty()) if interactive is None else interactive,
        input_fn=input_fn,
    )
    if source is None:
        return result
    result.source = source

    target_root = data_dir()
    with MigrationLock(target_root / ".migration.lock"):
        database_source = source / DATABASE_NAME
        database_target = _target_database_path()
        if database_source.is_file():
            if database_target.exists():
                result.skipped.append(DATABASE_NAME)
            else:
                _sqlite_backup(database_source, database_target)
                result.migrated.append(DATABASE_NAME)

        try:
            _migrate_key_pair(source, result)
        except (OSError, ValueError, IndexError, TypeError) as exc:
            result.warnings.append(str(exc))

        cache_source = source / CACHE_NAME
        cache_target = target_root / CACHE_NAME
        if cache_source.is_file():
            if cache_target.exists():
                result.skipped.append(CACHE_NAME)
            else:
                try:
                    cache_bytes = _validated_cache_bytes(cache_source)
                except (OSError, ValueError) as exc:
                    result.warnings.append(str(exc))
                else:
                    _atomic_copy_bytes(cache_target, cache_bytes, 0o600)
                    result.migrated.append(CACHE_NAME)

    if result.changed:
        logger.info("Migrated legacy runtime data from %s: %s", source, ", ".join(result.migrated))
    for warning in result.warnings:
        logger.warning("Legacy data migration warning: %s", warning)
    return result


__all__ = [
    "CACHE_NAME",
    "DATABASE_NAME",
    "MigrationLock",
    "MigrationResult",
    "PRIVATE_KEY_NAME",
    "PUBLIC_KEY_NAME",
    "choose_legacy_data_dir",
    "discover_legacy_data_dirs",
    "migrate_legacy_runtime_data",
]
