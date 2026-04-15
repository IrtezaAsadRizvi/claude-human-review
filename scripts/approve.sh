#!/usr/bin/env bash
# approve.sh <session_id>
#
# Accept the current turn's edits. Deletes the session state dir so the next
# turn's edits get a fresh review.
set -euo pipefail

session_id="${1:?usage: approve.sh <session_id>}"
dir="$(pwd)/.claude/human-review/${session_id}"

if [ -d "$dir" ]; then
    rm -rf "$dir"
    echo "Approved. Cleared review state for session ${session_id}."
else
    echo "Nothing to approve (no pending review for session ${session_id})."
fi
