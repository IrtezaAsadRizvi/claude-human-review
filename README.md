# claude-human-review

> A human-in-the-loop code review gate for Claude Code. Every turn Claude edits your files, it stops and explains **what** it changed and **why** — then waits for you to **Approve** or **Undo**.

**Keywords:** claude code review · claude code approval · approve claude changes · undo claude changes · AI code review · human-in-the-loop · claude code plugin · claude code hooks

---

## The problem this solves

Claude Code writes code faster than you can read it. If you're not watching every edit — and nobody is, not really — you end up with a codebase you own but don't understand. That's a correctness problem, a security problem, and a long-term maintenance problem. The cost shows up later: in the bug you can't explain, the migration that breaks in production, the auth bypass nobody noticed.

**`claude-human-review` forces a short review gate at the end of every turn where Claude touched the filesystem.** No silent accepts. No changes stick until you explicitly approve them. If the review surfaces something you don't like — one word, `undo`, reverts everything from that turn.

The goal isn't to slow you down. The goal is to make the 10 seconds you *should* have been reading happen whether you remembered to or not.

---

## What the review looks like

After Claude finishes a turn that edited files, your terminal shows something like this:

```markdown
## Review: what I just did

**What changed**
- `src/auth/session.py` — switched the session cookie from SameSite=Lax to
  SameSite=Strict and added the Secure flag.
- `tests/test_auth.py` — added two test cases covering the new cookie flags.

**Why**
You asked to "tighten up cookie handling." I read that as defense-in-depth
against CSRF. SameSite=Strict is stricter than your current Lax but will
break any cross-site embeds — I assumed you don't have those. The Secure
flag requires HTTPS, so local HTTP dev sessions won't persist cookies.

**Worth a second look**
- SameSite=Strict will break OAuth redirect flows — confirm you don't
  rely on that pattern.
- Local HTTP dev will silently drop cookies now.

---
**1. Approve** — accept these changes.
**2. Undo** — revert all files this turn.
```

You reply `1` to keep the changes or `2` to roll them back. That's the whole loop.

---

## Install

### Option A — Local symlink (recommended during dev)

```bash
git clone https://github.com/<you>/claude-human-review.git
mkdir -p ~/.claude/plugins/local
ln -s "$(pwd)/claude-human-review" ~/.claude/plugins/local/claude-human-review
```

Then enable the plugin in your Claude Code settings and restart Claude Code. The hooks take effect on your next prompt.

### Option B — Claude Code plugin marketplace

*(Coming once published.)*

```bash
claude plugin install claude-human-review
```

### Requirements

- Claude Code (any version with plugin + hooks support)
- Python 3.9+ on PATH (the hooks are pure-Python, no third-party deps)
- Bash (the approve/undo helper scripts)

---

## How to use it

There's nothing to *do* — once installed, the plugin runs automatically. The flow from your perspective:

1. **You prompt Claude** as normal: *"refactor the auth middleware to use JWT."*
2. **Claude edits files** as normal — you don't see anything different during the work.
3. **At end of turn, Claude pauses** and writes a plain-English review (the example above).
4. **You reply:**
   - `1` or `approve` → changes stick, session state cleared, you're done.
   - `2` or `undo` → every file edited this turn is reverted; newly-created files are deleted.
   - Anything else → treated as a fresh prompt. The prior turn's changes are implicitly accepted and the plugin starts tracking the new turn.

### What triggers a review

| Claude tool used               | Triggers review? |
| ------------------------------ | :--------------: |
| `Edit`, `Write`, `NotebookEdit` | ✅ yes            |
| `Read`, `Bash`, `Grep`, `Glob`  | ❌ no             |

Read-only exploration turns never interrupt you. Only turns that actually changed your files.

### Disable temporarily

Set an environment variable before launching Claude Code:

```bash
HUMAN_REVIEW_DISABLED=1 claude
```

The Stop hook honors this flag and lets Claude stop silently. Snapshots and logs are still written harmlessly — so you can flip the flag on mid-session if you change your mind.

---

## How it works (under the hood)

Three Claude Code hooks coordinate through a per-session state directory:

```
PreToolUse   (Edit|Write|NotebookEdit) → snapshot.py    → copies original file
PostToolUse  (Edit|Write|NotebookEdit) → track_edits.py → logs the edit
Stop         (end of turn)             → review_gate.py → blocks stop, injects review prompt
```

When the Stop hook fires with a non-empty edit log, it blocks Claude from stopping and injects a prompt telling Claude to load the `human-review` skill. That skill contains the template, tone rules, and example Claude uses to write the review. Your `1` / `2` reply routes to two small Bash helpers (`scripts/approve.sh` / `scripts/undo.sh`) that do the actual state mutation.

**Undo uses filesystem snapshots**, not git, so it works identically in any directory — git repo, non-repo, or a mess of untracked files.

---

## State & storage

Each Claude Code session gets its own state dir, rooted at the project where you ran Claude:

```
<cwd>/.claude/human-review/<session_id>/
├── snapshots/            # one JSON per edited file, holding original contents
├── edit_log.jsonl        # one line per successful edit
└── review_shown.flag     # prevents the Stop hook from looping
```

Add `.claude/human-review/` to your `.gitignore` — it's ephemeral turn-by-turn state, not source of truth. Dead sessions are auto-purged after 30 days.

---

## Repository layout

```
claude-human-review/
├── .claude-plugin/plugin.json     # plugin manifest
├── hooks/
│   ├── hooks.json                 # Pre/Post/Stop hook wiring
│   ├── _common.py                 # shared state-dir + snapshot helpers
│   ├── snapshot.py                # PreToolUse:  snapshot original file
│   ├── track_edits.py             # PostToolUse: log successful edits
│   └── review_gate.py             # Stop:        block + inject review prompt
├── skills/
│   └── human-review/SKILL.md      # how Claude writes the review & handles 1/2
├── scripts/
│   ├── approve.sh                 # clear session state
│   └── undo.sh                    # restore snapshots / delete created files
└── README.md
```

---

## Behavior details (edge cases)

- **Multiple edits to one file per turn.** Snapshots are first-edit-wins, so undo always restores the true pre-turn baseline.
- **New-file creation.** If Claude creates `foo.py`, undo deletes it.
- **Binary or >1 MB files.** Not snapshotted (storage cost). The review flags them and undo will warn those specific files can't be reverted — current contents stay in place.
- **Failed edits.** Tools that errored or were denied write no log entry. No orphan review.
- **Ignoring the review.** If you send a fresh prompt without answering, the previous turn is treated as implicitly approved, state is cleared, and the new turn gets its own review.
- **Subagent edits.** Not gated in v0.1 (we hook `Stop`, not `SubagentStop`). Edits from subagents fly under the radar.

---

## Limitations

- **Review quality depends on Claude.** If the summaries feel shallow, tune `skills/human-review/SKILL.md` — the plugin code is stable, the prompt is the knob.
- **Subagent blind spot** as noted above.
- **Large text files near the 1 MB cap** make snapshot/undo slow since snapshots are JSON-wrapped text.
- **Windows paths not tested.** Should work but unverified.

---

## Contributing

PRs welcome, especially for:

- Better review examples in `SKILL.md` (prompt-engineering, not code)
- Windows support
- `SubagentStop` coverage
- Compression for snapshots on large text files

Keep it simple — the whole point is a plugin you can read end-to-end in one sitting.

---

## License

MIT. Use it, fork it, ship it.
