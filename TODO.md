# TODO: Improvement Ideas

A running list of improvements for `claude-human-review`. Grouped by category. Not in priority order, but the ones marked **(top pick)** are the highest cost-to-value.

---

## Coverage gaps

- [ ] **SubagentStop hook (top pick).** README admits subagent edits slip through in v0.1. Add a parallel `SubagentStop` hook that flushes subagent edits into the parent's edit log, or shows a mini-review at subagent end. Closes the biggest correctness hole.
- [ ] **Defensive PostToolUse filter.** If Claude Code adds new edit-type tools, the hook list in `hooks.json` goes stale silently. Hook every PostToolUse and filter by whether the tool actually wrote to disk (mtime/inode delta) instead of a tool-name allowlist.
- [ ] **Tools that mutate via Bash.** `sed -i`, `mv`, `>` redirects, `git checkout <file>`, `npm install` (touches lockfile). Today these escape the gate. PreToolUse on Bash could scan the command for write patterns and snapshot any clearly-named target files. Imperfect, but catches the common cases.

## Review quality

- [ ] **Partial approve / per-file Undo.** Today it's all or nothing. Reply `2 src/auth/session.py` to undo a single file, or `2 except tests/` to keep the new tests. Big UX win for bigger turns.
- [ ] **Show a real diff on demand (top pick).** Add option `3. Diff` that prints snapshot-vs-current unified diff and re-prompts. Cheap to implement (snapshots already exist) and removes "I trust the prose but want to see it" friction.
- [ ] **Severity-tagged risks.** "Worth a second look" is a flat list. Tag each line `[auth]`, `[deps]`, `[migration]` so a 5-second skim tells you whether to read carefully. Categories are already in the skill.

## Token cost

- [ ] **Mini-review for trivial edits.** If total changed lines under N (say 5) and no risk patterns matched, emit a one-line review (`Tiny edit: <file>:<line> <what>. 1.Approve / 2.Undo`) instead of the full template. The hook can pre-compute this and pass a `mode=mini` hint to the skill.
- [ ] **Move risk detection into the hook, not the model (top pick).** The "auth, SQL, crypto, migrations, new deps, unsnapshotted" list is regex-detectable from the diff. If the hook precomputes hits and injects them as a fixed list, the model just narrates. Cuts variance and tokens at the same time.

## Trust and learning

- [ ] **Per-project history of approve/undo decisions.** A `.claude/human-review/history.jsonl` outside the per-session dir, recording (timestamp, files, risk tags, user choice). Two payoffs: (a) `/review-stats` command showing approve rate, (b) feed the last few decisions back into the skill prompt so Claude learns "this user always undoes raw SQL changes, flag harder."
- [ ] **"Why did I undo last time?" prompt.** On undo, optionally collect a one-line reason. Over time this becomes a private style guide for Claude.

## Robustness

- [ ] **Atomic snapshot writes.** Write to `<name>.tmp` then rename, so an interrupted hook can't leave a half-written snapshot that undo later trusts.
- [ ] **Lockfile on `edit_log.jsonl`.** PostToolUse hooks can run concurrently if Claude parallelizes tool calls. A `fcntl.flock` around the append avoids interleaved JSON lines.
- [ ] **Snapshot on first observation, not first Edit.** Edge case: Claude reads file A, runs Bash that touches A, then Edits A. PreToolUse on Edit snapshots the post-Bash version, not the true pre-turn baseline. Fix by snapshotting the first time a file is touched in the session.

## Polish

- [ ] **`/review-on` and `/review-off` slash commands** alongside the env var. Easier to toggle mid-session.
- [ ] **Windows path support and CI.** Listed as a known gap. A `windows-latest` CI job catches obvious breaks.
- [ ] **Compression for snapshots on large text files.** Already mentioned in the README's Contributing section. Gzip wrapping the JSON payload would push the 1 MB cap higher without a memory penalty.

---

## Notes on prioritization

If shipping in waves, suggested order:

1. **SubagentStop hook** (closes a known correctness gap)
2. **Diff option (`3. Diff`)** (high UX value, low complexity)
3. **Precompute risks in the hook** (cuts tokens and improves consistency)

Everything else is incremental polish on top of those three.
