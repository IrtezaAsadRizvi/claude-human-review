---
name: human-review
description: Produce a plain-English review of the files you just edited and gate the changes behind an explicit Approve/Undo choice. Use when the Stop hook from the human-review-skill plugin asks for a review (you'll see a prompt referencing an edit log), OR when the developer's most recent message is "1", "2", "approve", or "undo" in reply to a previous review.
---

# Human Review

Translate what you just did into plain English so the developer can Approve or Undo. Be brief. Every extra sentence costs tokens.

## When to run

Exactly two situations:

1. **Review trigger.** The Stop hook injected a prompt telling you to invoke `human-review`. The prompt includes a path to `edit_log.jsonl` and a `session_id`. You must produce a review before stopping.
2. **Reply handling.** On the very next user turn after a review, the developer's message is `1`, `2`, `approve`, `undo`, `yes`, or `no`. Run the matching script and nothing else.

Otherwise, don't invoke this skill.

## Step 1: Document what you changed

Before writing the review, add brief doc comments to new or materially-changed **classes, functions, methods, exported symbols, and non-obvious config blocks** in the files listed in `edit_log.jsonl`. The goal is a glanceable note, not prose.

### Comment style by language

| Language                         | Style                                 |
| -------------------------------- | ------------------------------------- |
| TypeScript / JavaScript          | JSDoc `/** ... */` above the symbol   |
| Python                           | Triple-quoted docstring inside def/class |
| Go                               | `// FuncName ...` line above          |
| Rust                             | `/// ...` lines above                 |
| Java / Kotlin / PHP / C#         | JavaDoc-style `/** ... */`            |
| Ruby                             | `#` lines above                       |
| Shell / YAML / TOML / Dockerfile | `#` line above the block              |

### Rules

- **Keep it to 1 line** (max 2 if a non-obvious param/return matters). One short sentence on *what this is for*, not how it works.
- **Only touch symbols you added or meaningfully changed** this turn. Don't document the whole file.
- **Skip trivial helpers**, one-liners, private utility functions, test cases, getters/setters, and obviously-named things. A 3-line `formatDate` doesn't need a JSDoc.
- **Don't duplicate the signature.** "Adds two numbers" on `add(a, b)` is noise.
- **Don't overwrite existing comments** unless they're now wrong. If a symbol already has a docstring/JSDoc, leave it alone.
- **Config blocks**: add a comment only when the *purpose* of the block isn't obvious from the keys.
- **No emojis, no TODOs, no author tags, no dates.**

If a file has nothing worth documenting under these rules, skip it. Don't force comments.

## Step 2: Writing the review

Read `edit_log.jsonl` for the file list. Produce exactly this structure:

```markdown
## Review: what I just did

**What changed**
- `path/to/file1.py`: <≤12 words on the edit>
- `path/to/file2.ts`: <≤12 words on the edit>

**Why**
<1 sentence. Only add a second if a non-obvious assumption needs flagging.>

**Worth a second look**
- <one line per real risk: new dep, secret/config, deletion, auth/crypto, SQL, shell exec, network, migration, unsnapshotted file>

---
**1. Approve**: accept these changes.
**2. Undo**: revert all files this turn.
```

### Hard rules

- **Target 60–120 words total.** Hard cap 200. If you're over, cut.
- **One short line per file.** Summarize the goal, not each chunk.
- **Skip "Worth a second look" entirely if nothing is risky.** Don't pad. No "N/A", no "nothing to flag".
- **Skip "Why" if the prompt was literal** (e.g. "add a print statement", "rename X to Y"). Omit the whole section.
- **No preamble, no recap of the prompt, no closing commentary.** The template above is the whole message.
- **Never drop the 1/2 closing block.** It must appear verbatim.
- **Flag invisible risks only.** Things the diff won't show: dynamic imports, loosened checks, swallowed exceptions, new deps, binary/unsnapshotted files.

### Example (terse)

```markdown
## Review: what I just did

**What changed**
- `src/auth/session.py`: session cookie SameSite=Lax → Strict, added Secure flag.
- `tests/test_auth.py`: two cases for the new flags; fixture expects `secure=True`.

**Why**
Read "tighten cookie handling" as CSRF hardening. Strict will break cross-site embeds; I assumed you have none.

**Worth a second look**
- Strict breaks OAuth redirects landing on your domain.
- Secure drops cookies on plain-HTTP localhost dev.

---
**1. Approve**: accept these changes.
**2. Undo**: revert all files this turn.
```

## Handling the developer's reply

On the turn *after* a review, match the message (case-insensitive, trimmed):

| Reply                 | Do                                                                                                                 |
| --------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `1`, `approve`, `yes` | Run `bash ${CLAUDE_PLUGIN_ROOT}/scripts/approve.sh <session_id>`. Reply once: "Approved."                          |
| `2`, `undo`, `no`     | Run `bash ${CLAUDE_PLUGIN_ROOT}/scripts/undo.sh <session_id>`. Paste the script output. Surface any warnings.      |
| Anything else         | Treat as a new prompt. Don't run either script. The next edit auto-clears prior review state (implicit approve).   |

Use the exact `<session_id>` from the Stop hook prompt. `${CLAUDE_PLUGIN_ROOT}` is set by Claude Code.

### After approve or undo

- No second review this turn. State is cleared.
- No proactive edits. Wait for the next prompt.
- If `undo.sh` warns about unsnapshotted files, surface the warning plainly.
