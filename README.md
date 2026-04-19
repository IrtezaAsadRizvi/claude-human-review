# claude-human-review

[![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-Plugin-D97757?logo=anthropic&logoColor=white)](https://docs.claude.com/en/docs/claude-code)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#license)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#contributing)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey)](#requirements)
[![GitHub stars](https://img.shields.io/github/stars/IrtezaAsadRizvi/claude-human-review?style=social)](https://github.com/IrtezaAsadRizvi/claude-human-review/stargazers)

A plugin that helps you actually understand the code Claude Code writes for you. After every turn that edits files, Claude pauses and explains what it changed and why in plain English. You either approve the changes or undo them.

**Keywords:** claude code review, claude code approval, approve claude changes, undo claude changes, AI code review, human-in-the-loop, claude code plugin, claude code hooks.

---

## Why this exists

Claude Code writes code fast. Faster than you can read it. If you work that way for a few weeks, you end up sitting on a codebase you kind of wrote, kind of didn't, and don't fully understand. That's painful when something breaks, when a teammate asks why a piece of code is shaped the way it is, when an auditor wants a walkthrough, or when you come back six months later to extend it.

The goal of this project is simple: make the human developer more educated about the code going into their project.

Every review is a short lesson. Here's what changed. Here's why. Here's what to watch out for. You read it, you decide, you move on. Over time that adds up, and you end up fluent in your own codebase instead of a passenger in it.

Approve keeps the change. Undo throws it out. Either way, you saw it.

---

## Heads up: token usage

This plugin makes Claude write more. Every turn that edits files ends with a plain-English review, which costs extra output tokens. If you're on a token budget or paying per-token via the API, expect a small bump in usage.

That's the tradeoff, and honestly it's worth it. You pay a bit more in output tokens for a short summary, and in exchange you actually understand what Claude just did to your code. For serious AI-human collaboration, that's vital. Silent edits are cheap in the moment, but the cost shows up later in bugs you can't explain and code you didn't read.

If you want to claw tokens back elsewhere, take a look at [caveman](https://github.com/juliusbrussee/caveman). It compresses prompts so you spend less on input tokens, which pairs well with a plugin that spends more on output tokens for review clarity.

---

## What you'll see

When Claude finishes a turn that edited files, your terminal shows something like this:

```markdown
## Review: what I just did

**What changed**
- `src/auth/session.py`: switched the session cookie from SameSite=Lax
  to SameSite=Strict and added the Secure flag.
- `tests/test_auth.py`: added two test cases covering the new cookie flags.

**Why**
You asked to "tighten up cookie handling." I read that as defense-in-depth
against CSRF. SameSite=Strict is stricter than your current Lax, so it'll
break any cross-site embeds. I assumed you don't have those. The Secure
flag requires HTTPS, which means local HTTP dev sessions won't persist
cookies.

**Worth a second look**
- SameSite=Strict will break OAuth redirect flows. Confirm you don't
  rely on that pattern.
- Local HTTP dev will silently drop cookies now.

1. Approve: accept these changes.
2. Undo: revert all files this turn.
```

You reply `1` to keep it or `2` to roll it back.

---

## Install

### Option A: local symlink (recommended while developing)

```bash
git clone https://github.com/IrtezaAsadRizvi/claude-human-review.git
mkdir -p ~/.claude/plugins/local
ln -s "$(pwd)/claude-human-review" ~/.claude/plugins/local/claude-human-review
```

Enable the plugin in your Claude Code settings and restart Claude Code. The hooks take effect on your next prompt.

### Option B: Claude Code plugin marketplace

Coming once published.

```bash
claude plugin install claude-human-review
```

### Requirements

* Claude Code (any version with plugin and hook support).
* Python 3.9 or newer on PATH. The hooks are pure Python, no third-party dependencies.
* Bash for the approve and undo helper scripts.

---

## How to use it

There's nothing to do. Once installed, the plugin runs itself. From your side it looks like this:

1. You prompt Claude as normal. Something like "refactor the auth middleware to use JWT."
2. Claude edits files as normal. You don't see anything different while it works.
3. At the end of the turn Claude pauses and writes the review shown above.
4. You reply:
   * `1` or `approve`: changes stick, session state clears, you're done.
   * `2` or `undo`: every file edited this turn gets reverted. Newly created files get deleted.
   * Anything else is treated as a fresh prompt. The previous turn is implicitly accepted and the plugin starts tracking the new one.

### What counts as a change

| Tool Claude used                | Triggers a review? |
| ------------------------------- | :----------------: |
| `Edit`, `Write`, `NotebookEdit` |         Yes        |
| `Read`, `Bash`, `Grep`, `Glob`  |         No         |

Read-only exploration turns never interrupt you. Only turns that actually changed your files do.

### Turn it off temporarily

Set an environment variable before launching Claude Code:

```bash
HUMAN_REVIEW_DISABLED=1 claude
```

The Stop hook honors this flag and lets Claude stop silently. Snapshots and edit logs still get written harmlessly, so you can flip the flag back on mid-session if you change your mind.

---

## How it works under the hood

Three Claude Code hooks coordinate through a per-session state directory.

```
PreToolUse  (Edit, Write, NotebookEdit): snapshot.py   copies the original file
PostToolUse (Edit, Write, NotebookEdit): track_edits.py logs the edit
Stop        (end of turn):               review_gate.py blocks stop, injects review prompt
```

When the Stop hook fires with a non-empty edit log, it blocks Claude from stopping and injects a prompt telling Claude to load the `human-review` skill. That skill contains the template, tone rules, and example Claude uses to write the review. Your `1` or `2` reply routes to two small Bash helpers (`scripts/approve.sh` and `scripts/undo.sh`) that do the actual state mutation.

Undo uses filesystem snapshots, not git, so it works the same way in any directory: git repo, non-repo, or a folder full of untracked files.

---

## Why not just use CLAUDE.md?

Fair question, and the obvious one. You could drop something like "after every edit, summarize what you did and ask for approve or undo" into your CLAUDE.md, and Claude would try to follow it. It works, sometimes. Here's why the plugin exists anyway.

**CLAUDE.md gets read. Hooks get executed.**

CLAUDE.md is context Claude reads, weighed against your actual prompt. If your prompt is long or urgent, Claude can deprioritize the review instruction and just stop. There's no enforcement. The Stop hook here literally prevents Claude from ending the turn until the review is out. Deterministic, not probabilistic.

**Undo needs snapshots, not memory.**

To undo a set of edits you need the pre-edit contents of each file. A CLAUDE.md approach asks Claude to remember those contents and rewrite the files back. That breaks down a lot. Claude's context gets compacted mid-session and the old contents disappear. Claude does a Write without Reading first, so there's nothing to remember. Claude's rewrite of the "original" introduces its own bugs. This plugin snapshots each file to disk before the edit happens, so undo is a deterministic file restore, not another AI rewrite.

**Compaction is the silent killer.**

Long sessions trigger context compaction. Your pre-edit state, the early part of the conversation, the file contents Claude read two hours ago, all of it gets summarized into something shorter. If your "remember and revert" policy lives in Claude's head, it doesn't survive compaction. The plugin's edit log and snapshots live on disk, so they're immune.

**The line is harness vs memory.**

The Claude Code harness runs hooks for you. They fire on tool events and can't be talked out of firing. CLAUDE.md is just context Claude reads. Anytime you want a behavior to happen reliably, at a specific event, regardless of what Claude feels like doing that turn, you need a hook. That's this plugin's whole pitch.

If you're a solo dev on low-stakes code with short sessions, CLAUDE.md alone is probably fine. For anything where the review needs to actually happen every time and undo needs to actually work, the hooks are doing real work that instructions can't.

---

## State and storage

Each Claude Code session gets its own state directory, rooted at the project where you ran Claude.

```
<cwd>/.claude/human-review/<session_id>/
├── snapshots/         one JSON per edited file, holding original contents
├── edit_log.jsonl     one line per successful edit
└── review_shown.flag  prevents the Stop hook from looping
```

Add `.claude/human-review/` to your `.gitignore`. It's ephemeral, turn-by-turn state, not source of truth. Dead sessions get auto-purged after 30 days.

---

## Repository layout

```
claude-human-review/
├── .claude-plugin/plugin.json     plugin manifest
├── hooks/
│   ├── hooks.json                 Pre/Post/Stop hook wiring
│   ├── _common.py                 shared state-dir and snapshot helpers
│   ├── snapshot.py                PreToolUse:  snapshot original file
│   ├── track_edits.py             PostToolUse: log successful edits
│   └── review_gate.py             Stop:        block and inject review prompt
├── skills/
│   └── human-review/SKILL.md      how Claude writes the review and handles 1/2
├── scripts/
│   ├── approve.sh                 clear session state
│   └── undo.sh                    restore snapshots, delete created files
└── README.md
```

---

## Behavior details and edge cases

* **Multiple edits to the same file in one turn.** Snapshots are first-edit-wins, so undo always restores the true pre-turn baseline.
* **New-file creation.** If Claude creates `foo.py`, undo deletes it.
* **Binary or large files (over 1 MB).** Not snapshotted, because it's expensive. The review flags them and undo will warn that those specific files can't be reverted. Current contents stay in place.
* **Failed edits.** Tools that errored or were denied write no log entry. No orphan review.
* **Ignoring the review.** If you send a fresh prompt without answering, the previous turn is treated as implicitly approved, state clears, and the new turn gets its own review.
* **Subagent edits.** Not gated in v0.1. We hook `Stop`, not `SubagentStop`. Edits from subagents slip through.

---

## Limitations

* Review quality depends on Claude. If the summaries feel shallow, tune `skills/human-review/SKILL.md`. The plugin code is stable. The prompt is the knob.
* Subagent blind spot as noted above.
* Large text files near the 1 MB cap make snapshot and undo slow, since snapshots are JSON-wrapped text.
* Windows paths aren't tested. Should work, but I haven't verified it.

---

## Contributing

PRs welcome, especially for:

* Better review examples in `SKILL.md` (prompt engineering, not code).
* Windows support.
* `SubagentStop` coverage.
* Compression for snapshots on large text files.

Keep it simple. The whole point is a plugin you can read end-to-end in one sitting.

---

## License

MIT. Use it, fork it, ship it.
