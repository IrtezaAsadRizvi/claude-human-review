#!/usr/bin/env python3
"""PostToolUse hook: append one log line per successful file edit.

The edit log is consumed by:
- `review_gate.py` to decide whether a review is needed at end-of-turn
- `scripts/undo.sh` to know which files to restore and whether each was a
  pre-existing modification or a fresh creation

Failed tool calls produce no log entry — the PreToolUse snapshot for that call
becomes an orphan and is cleaned up on approve/undo or TTL.
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import append_log, load_hook_stdin, snapshot_file  # noqa: E402


def _was_successful(tool_response: object) -> bool:
    """Best-effort success check across the variants Claude Code emits."""
    if isinstance(tool_response, dict):
        # Explicit failure signal wins.
        if tool_response.get("success") is False:
            return False
        if tool_response.get("error"):
            return False
        return True
    # Non-dict responses (strings, etc.) — assume success if we got anything.
    return tool_response is not None


def main() -> int:
    data = load_hook_stdin()
    session_id = data.get("session_id") or "default"
    tool_name = data.get("tool_name") or ""
    tool_input = data.get("tool_input") or {}
    tool_response = data.get("tool_response")

    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not file_path:
        return 0

    if not _was_successful(tool_response):
        return 0

    abs_path = os.path.abspath(file_path)

    # Determine whether this was a creation (snapshot marked `existed: False`).
    # If the snapshot is missing (unexpected), default to "modify" so undo at
    # least has a record that something was touched.
    action = "modify"
    snap = snapshot_file(session_id, abs_path)
    if snap.exists():
        try:
            meta = json.loads(snap.read_text(encoding="utf-8"))
            if meta.get("existed") is False:
                action = "create"
        except (OSError, json.JSONDecodeError):
            pass

    try:
        append_log(session_id, {
            "ts": time.time(),
            "tool": tool_name,
            "path": abs_path,
            "action": action,
        })
    except OSError:
        pass

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
