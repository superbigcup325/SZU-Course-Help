from __future__ import annotations

import subprocess
from pathlib import Path

from scripts import package_source


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_source_files_only_returns_git_tracked_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")

    tracked = repo / "README.md"
    tracked.write_text("tracked\n", encoding="utf-8")
    (repo / "debug.txt").write_text("must not ship\n", encoding="utf-8")
    _git(repo, "add", "README.md")

    assert package_source.source_files(repo) == [tracked]


def test_source_files_rejects_missing_tracked_entry(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")

    tracked = repo / "README.md"
    tracked.write_text("tracked\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    tracked.unlink()

    try:
        package_source.source_files(repo)
    except RuntimeError as exc:
        assert "README.md" in str(exc)
    else:
        raise AssertionError("missing tracked files must fail source packaging")
