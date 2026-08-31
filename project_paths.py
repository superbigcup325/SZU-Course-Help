"""Resolve source, bundled-resource, and writable runtime paths.

Source checkouts intentionally keep their historical project-local layout.
Frozen releases use a stable per-user directory so upgrades do not lose the
database, catalog cache, or Card Key signing identity.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def application_dir() -> Path:
    """Return the directory that owns runtime data for this installation."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PROJECT_ROOT


def is_frozen() -> bool:
    """Return whether the process is running from a packaged executable."""
    return bool(getattr(sys, "frozen", False))


def user_data_dir() -> Path:
    """Return the platform-native data directory for packaged releases."""
    if sys.platform == "win32":
        root = os.getenv("APPDATA", "").strip()
        base = Path(root).expanduser() if root else Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        root = os.getenv("XDG_DATA_HOME", "").strip()
        base = Path(root).expanduser() if root else Path.home() / ".local" / "share"
    return (base / "SZU-Course-Help").resolve()


def resource_path(relative_path: str | Path) -> Path:
    """Resolve a read-only resource in source and frozen application modes."""
    bundled_root = getattr(sys, "_MEIPASS", None)
    base = Path(bundled_root).resolve() if bundled_root else application_dir()
    return (base / relative_path).resolve()


def data_dir() -> Path:
    """Return the writable data directory, optionally overridden by the user."""
    configured = os.getenv("COURSE_SELECT_DATA_DIR", "").strip()
    if configured:
        directory = Path(configured).expanduser().resolve()
    elif is_frozen():
        directory = user_data_dir()
    else:
        directory = application_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def key_dir() -> Path:
    """Return the Card Key identity directory without changing source-mode keys."""
    configured = os.getenv("COURSE_SELECT_KEY_DIR", "").strip()
    if configured:
        directory = Path(configured).expanduser().resolve()
    elif is_frozen():
        directory = data_dir() / "keys"
    else:
        directory = PROJECT_ROOT
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def external_process_env() -> dict[str, str]:
    """Return a child-process environment copy that cannot shadow system libraries.

    Nuitka standalone exports ``LD_LIBRARY_PATH`` (observed value ``":"`` on
    CI builds). glibc resolves empty entries against the current working
    directory, which the Linux launcher sets to the release folder holding
    bundled ``libssl.so.3``/``libcrypto.so.3``; any child that loads system
    OpenSSL/Qt/KIO libraries then aborts with missing ``OPENSSL_3.x``
    version symbols. Only Linux packaged runs are affected — other platforms
    and source checkouts get an untouched copy.

    Entries are filtered with ``os.pathsep``: empty items, ``.``, and paths
    resolving into the application directory are dropped; everything else
    the user configured (vendor runtime dirs, preload helpers) is kept. The
    variable is removed entirely when nothing survives. The function is
    pure and idempotent, and never mutates the caller's mapping.
    """
    env = dict(os.environ)
    if not (sys.platform.startswith("linux") and is_frozen()):
        return env
    application = Path(application_dir()).resolve()
    for name in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
        raw = env.get(name)
        if raw is None:
            continue
        kept = []
        for entry in raw.split(os.pathsep):
            if not entry or entry == ".":
                continue
            try:
                resolved = Path(entry).resolve()
            except OSError:
                continue
            if resolved == application or application in resolved.parents:
                continue
            kept.append(entry)
        if kept:
            env[name] = os.pathsep.join(kept)
        else:
            env.pop(name, None)
    return env


__all__ = [
    "PROJECT_ROOT",
    "application_dir",
    "data_dir",
    "external_process_env",
    "is_frozen",
    "key_dir",
    "resource_path",
    "user_data_dir",
]
