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


__all__ = [
    "PROJECT_ROOT",
    "application_dir",
    "data_dir",
    "is_frozen",
    "key_dir",
    "resource_path",
    "user_data_dir",
]
