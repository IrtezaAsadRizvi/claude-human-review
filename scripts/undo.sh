#!/usr/bin/env bash
# undo.sh <session_id>
#
# Revert every edit logged for <session_id>:
#   - modify action → restore the snapshot content
#   - create action → delete the file (it didn't exist before)
#   - skipped snapshot (binary/large/unreadable) → leave file alone, emit warning
#
# After reverting, wipes the session state dir.
set -euo pipefail

session_id="${1:?usage: undo.sh <session_id>}"
state_dir="$(pwd)/.claude/human-review/${session_id}"

if [ ! -d "$state_dir" ]; then
    echo "Nothing to undo (no pending review for session ${session_id})."
    exit 0
fi

python3 - "$state_dir" <<'PY'
import json
import os
import sys
import hashlib
from pathlib import Path

state_dir = Path(sys.argv[1])
log_path = state_dir / "edit_log.jsonl"
snap_dir = state_dir / "snapshots"

restored = 0
deleted = 0
warnings = []

# Dedupe by absolute path — a file may have been edited multiple times this turn.
seen: set[str] = set()

if log_path.exists():
    entries = []
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    for entry in entries:
        path = entry.get("path")
        if not path or path in seen:
            continue
        seen.add(path)

        h = hashlib.sha1(path.encode("utf-8")).hexdigest()
        snap_path = snap_dir / f"{h}.json"
        if not snap_path.exists():
            warnings.append(f"no snapshot for {path} (skipping)")
            continue

        try:
            meta = json.loads(snap_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            warnings.append(f"corrupt snapshot for {path}: {e}")
            continue

        existed = meta.get("existed", True)
        skipped = meta.get("skipped")

        if skipped:
            warnings.append(
                f"{path}: was not snapshotted ({skipped}); current contents left in place"
            )
            continue

        if not existed:
            # File was created this turn → delete it.
            try:
                if os.path.exists(path):
                    os.remove(path)
                    deleted += 1
            except OSError as e:
                warnings.append(f"could not delete {path}: {e}")
            continue

        # File existed → restore original content.
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(meta.get("content", ""))
            restored += 1
        except OSError as e:
            warnings.append(f"could not restore {path}: {e}")

# Wipe the session state dir last.
def rmtree(p: Path):
    for sub in sorted(p.rglob("*"), key=lambda x: -len(x.parts)):
        try:
            sub.unlink() if sub.is_file() or sub.is_symlink() else sub.rmdir()
        except OSError:
            pass
    try:
        p.rmdir()
    except OSError:
        pass

rmtree(state_dir)

print(f"Undone: {restored} file(s) restored, {deleted} file(s) deleted, {len(warnings)} warning(s).")
for w in warnings:
    print(f"  ! {w}")
PY
