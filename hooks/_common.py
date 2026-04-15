"""Shared helpers for the human-review-skill hooks.

All three hook scripts (snapshot, track_edits, review_gate) coordinate through a
session-scoped state directory rooted at the project's current working directory:

    <cwd>/.claude/human-review/<session_id>/
        snapshots/<sha1-of-abs-path>.json
        edit_log.jsonl
        review_shown.flag

Snapshots are the only reliable way to undo edits in arbitrary directories
(the target project may not be a git repo).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

# 1 MiB cap: above this, a file is considered too large to snapshot cheaply.
MAX_SNAPSHOT_BYTES = 1_048_576

# Purge session state dirs older than this many seconds (30 days).
STATE_TTL_SECONDS = 30 * 24 * 60 * 60

# Sentinel written instead of file content when snapshot is skipped.
SKIP_BINARY_OR_LARGE = "binary-or-large"


def review_root() -> Path:
    """Root dir holding all per-session state, anchored at the current project."""
    return Path.cwd() / ".claude" / "human-review"


def state_dir(session_id: str, create: bool = True) -> Path:
    """Return the per-session state directory. Creates it (and `snapshots/`) if requested."""
    d = review_root() / session_id
    if create:
        (d / "snapshots").mkdir(parents=True, exist_ok=True)
    return d


def snapshot_file(session_id: str, file_path: str) -> Path:
    """Stable, collision-safe snapshot filename for a given absolute path."""
    abs_path = os.path.abspath(file_path)
    h = hashlib.sha1(abs_path.encode("utf-8")).hexdigest()
    return state_dir(session_id) / "snapshots" / f"{h}.json"


def edit_log(session_id: str) -> Path:
    return state_dir(session_id) / "edit_log.jsonl"


def review_flag(session_id: str) -> Path:
    return state_dir(session_id) / "review_shown.flag"


def append_log(session_id: str, entry: dict[str, Any]) -> None:
    with edit_log(session_id).open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def read_log(session_id: str) -> list[dict[str, Any]]:
    p = edit_log(session_id)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                # Skip malformed lines rather than crash the hook.
                continue
    return out


def is_snapshotable(path: str) -> tuple[bool, str | None]:
    """Return (ok, reason_if_not). Binary or too-large files get skipped."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return True, None  # Treat unreadable-stat as OK; caller will handle missing file.
    if size > MAX_SNAPSHOT_BYTES:
        return False, SKIP_BINARY_OR_LARGE
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
    except OSError:
        return True, None
    # Simple binary heuristic: NUL byte presence.
    if b"\x00" in chunk:
        return False, SKIP_BINARY_OR_LARGE
    return True, None


def read_text_best_effort(path: str) -> str:
    """Read a file as text. Falls back to latin-1 so any byte sequence round-trips."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin-1") as f:
            return f.read()


def cleanup_stale_sessions() -> None:
    """Delete state dirs older than STATE_TTL_SECONDS. Best-effort; never raises."""
    root = review_root()
    if not root.exists():
        return
    cutoff = time.time() - STATE_TTL_SECONDS
    try:
        for child in root.iterdir():
            if not child.is_dir():
                continue
            try:
                if child.stat().st_mtime < cutoff:
                    _rmtree(child)
            except OSError:
                pass
    except OSError:
        pass


def _rmtree(path: Path) -> None:
    """Minimal rmtree so we avoid importing shutil in a hot hook path."""
    for sub in path.rglob("*"):
        if sub.is_file() or sub.is_symlink():
            try:
                sub.unlink()
            except OSError:
                pass
    # Remove directories depth-first.
    for sub in sorted((p for p in path.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        try:
            sub.rmdir()
        except OSError:
            pass
    try:
        path.rmdir()
    except OSError:
        pass


def load_hook_stdin() -> dict[str, Any]:
    """Parse the hook JSON envelope from stdin. Returns {} on any failure."""
    import sys
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        return json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return {}


def clear_session_state(session_id: str) -> None:
    """Wipe a session's state directory. Used by implicit-approval cleanup."""
    d = state_dir(session_id, create=False)
    if d.exists():
        _rmtree(d)
