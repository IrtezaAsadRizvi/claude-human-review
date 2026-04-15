#!/usr/bin/env python3
"""Stop hook: if any edits occurred this turn, block the stop and inject a
prompt telling Claude to load the human-review skill and produce a review.

Contract:
- Exit 0 with no stdout → Claude stops normally (no edits this turn, or review
  already shown).
- Exit 0 with a JSON `{"decision": "block", "reason": "..."}` on stdout →
  Claude cannot stop yet; the `reason` is injected as a continuation prompt.

The flag file `review_shown.flag` prevents an infinite loop: once we've
injected the review prompt, we won't inject again this session until
approve/undo clears state (or the dev sends a fresh prompt, which triggers
implicit-approval cleanup in snapshot.py).
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import edit_log, load_hook_stdin, review_flag, state_dir  # noqa: E402


REVIEW_PROMPT_TEMPLATE = (
    "You just edited files this turn. Before stopping, invoke the "
    "**human-review** skill and produce a review for the developer, "
    "following that skill's instructions exactly.\n\n"
    "Edit log (one JSON object per line) is at:\n"
    "    {log_path}\n\n"
    "Session state root (for approve/undo helpers):\n"
    "    {state_root}\n"
    "Session id: {session_id}\n\n"
    "Your review MUST end with the two numbered options "
    "`**1. Approve**` and `**2. Undo**` exactly as the skill specifies. "
    "The developer will reply with 1/approve or 2/undo on their next turn."
)


def main() -> int:
    # Allow a disable escape hatch for advanced users.
    if os.environ.get("HUMAN_REVIEW_DISABLED") == "1":
        return 0

    data = load_hook_stdin()
    session_id = data.get("session_id") or "default"

    log_path = edit_log(session_id)
    if not log_path.exists() or log_path.stat().st_size == 0:
        return 0  # No edits happened; let Claude stop.

    flag = review_flag(session_id)
    if flag.exists():
        return 0  # Review already shown; don't loop.

    # Mark shown *before* emitting, so even if Claude is interrupted we won't
    # re-trigger on the next Stop until approve/undo clears state.
    try:
        state_dir(session_id).mkdir(parents=True, exist_ok=True)
        flag.write_text("1", encoding="utf-8")
    except OSError:
        # If we can't persist the flag, still block once — better a duplicate
        # review than no review at all.
        pass

    reason = REVIEW_PROMPT_TEMPLATE.format(
        log_path=str(log_path),
        state_root=str(state_dir(session_id, create=False)),
        session_id=session_id,
    )
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Never crash Claude's stop path.
        sys.exit(0)
