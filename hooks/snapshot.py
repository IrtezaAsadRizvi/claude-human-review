#!/usr/bin/env python3
"""PreToolUse hook: snapshot a file's original contents before Edit/Write/NotebookEdit.

The snapshot lets `scripts/undo.sh` restore the file exactly as it was at the
start of the current Claude turn, even when the project is not a git repo.

Design notes:
- Only the *first* edit of a file per session is snapshotted. Subsequent edits
  are relative to an already-captured baseline, so undo restores the true
  pre-turn state.
- Binary and >1MB files are marked as skipped rather than stored; the review
  flags this and undo emits a warning.
- Implicit-approval cleanup: if a prior turn left `review_shown.flag` behind
  (dev ignored the review and moved on), we treat that turn as approved,
  wipe its snapshots/log, then start fresh for this turn.
- This hook must never block Claude; all errors fall through to exit 0.
"""

from __future__ import annotations

import json
import os
import sys

# Allow running both as `python3 hooks/snapshot.py` and when CLAUDE_PLUGIN_ROOT
# places this directory on the path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import (  # noqa: E402
    SKIP_BINARY_OR_LARGE,
    clear_session_state,
    cleanup_stale_sessions,
    is_snapshotable,
    load_hook_stdin,
    read_text_best_effort,
    review_flag,
    snapshot_file,
    state_dir,
)


def main() -> int:
    data = load_hook_stdin()
    session_id = data.get("session_id") or "default"
    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not file_path:
        return 0  # Nothing to snapshot.

    # Implicit-approval cleanup: a previous turn's review was never answered.
    # Treat it as approved and wipe its state before snapshotting this turn's edits.
    if review_flag(session_id).exists():
        clear_session_state(session_id)

    # Occasional housekeeping (very cheap when root is empty).
    cleanup_stale_sessions()

    state_dir(session_id)  # ensure directory tree exists
    snap = snapshot_file(session_id, file_path)
    if snap.exists():
        return 0  # First-edit-wins: preserve the true pre-turn baseline.

    abs_path = os.path.abspath(file_path)

    if not os.path.exists(abs_path):
        # File doesn't exist yet → this edit is a create. Mark it so undo can delete.
        payload = {"path": abs_path, "existed": False}
    else:
        ok, reason = is_snapshotable(abs_path)
        if not ok:
            payload = {"path": abs_path, "existed": True, "skipped": reason or SKIP_BINARY_OR_LARGE}
        else:
            try:
                content = read_text_best_effort(abs_path)
                payload = {"path": abs_path, "existed": True, "content": content}
            except OSError:
                # Couldn't read for some reason; record path so undo can warn.
                payload = {"path": abs_path, "existed": True, "skipped": "unreadable"}

    try:
        snap.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass  # Never block the tool on snapshot failure.

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Defensive: hooks must never crash Claude's tool flow.
        sys.exit(0)
