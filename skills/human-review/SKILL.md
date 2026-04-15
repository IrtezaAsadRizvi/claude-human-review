---
name: human-review
description: Produce a plain-English review of the files you just edited and gate the changes behind an explicit Approve/Undo choice. Use when the Stop hook from the human-review-skill plugin asks for a review (you'll see a prompt referencing an edit log), OR when the developer's most recent message is "1", "2", "approve", or "undo" in reply to a previous review.
---

# Human Review

You are the last line of defense between Claude-generated code and a codebase the human will have to own and debug. Your job is to translate what Claude did into plain English so the developer — who may not have been watching — can make an informed Approve / Undo decision.

## When to run

Run this skill in exactly two situations:

1. **Review trigger.** The Stop hook injected a prompt telling you to invoke `human-review`. The prompt includes a path to `edit_log.jsonl` and a `session_id`. You must produce a review before stopping.
2. **Reply handling.** On the very next user turn after you produced a review, the developer's message is `1`, `2`, `approve`, `undo`, `yes`, or `no`. You must run the appropriate helper script. Do not do anything else that turn — no extra edits, no follow-up suggestions — until the developer sends a fresh prompt.

If neither condition applies, don't invoke this skill.

## Writing the review

Read `edit_log.jsonl` to get the list of files that were touched this turn. For each file, recall from your own turn history *what* you changed and *why*. Then produce a review with this exact structure:

```markdown
## Review: what I just did

**What changed**
- `path/to/file1.py` — <one plain-English sentence about the edit>
- `path/to/file2.ts` — <one plain-English sentence about the edit>

**Why**
<1–3 sentences explaining the intent behind these changes, tied back to the developer's prompt. Call out any domain assumptions you made — especially assumptions a non-expert might not spot.>

**Worth a second look**
- <anything risk-adjacent: new deps, config/secrets changes, deletions, auth/permissions/crypto code, SQL, shell exec, network calls, schema migrations, files that couldn't be snapshotted>
- <omit this section entirely if there's nothing noteworthy — don't pad>

---
**1. Approve** — accept these changes.
**2. Undo** — revert all files this turn.
```

### Writing rules

- **Explain the why, not the what.** The developer can read the diff. What they can't read is your reasoning, the tradeoffs you considered, and the domain assumptions baked in. Lead with that.
- **One line per file.** If a file has multiple changes, summarize the *goal*, not each chunk. "Refactored auth middleware to extract the JWT validation helper" beats "Moved lines 40–55 to a new function and updated the import at line 3."
- **Flag invisible risks.** A rename in a dynamically-loaded module, a new dependency, a loosened permission check, a silently caught exception — these belong in "Worth a second look" even if they look trivial in the diff.
- **Don't re-list the obvious.** If the developer asked "add a print statement to foo.py", the Why section doesn't need to justify the print statement. The review exists to surface what isn't obvious from the prompt.
- **Keep it scannable.** 150–400 words total is the sweet spot for most turns. Longer is only justified when you did something substantive.
- **Never skip the closing block.** The `1. Approve / 2. Undo` lines must appear verbatim at the end, or the developer loses the call-to-action.

### Example review

```markdown
## Review: what I just did

**What changed**
- `src/auth/session.py` — switched the session cookie from SameSite=Lax to SameSite=Strict and added the Secure flag.
- `tests/test_auth.py` — added two test cases covering the new cookie flags; updated the fixture to expect `secure=True`.

**Why**
You asked to "tighten up cookie handling." I interpreted that as defense-in-depth against CSRF and mixed-content leakage. SameSite=Strict blocks cookies on cross-site requests entirely, which is stricter than your current Lax but will break any cross-site embeds — I assumed you don't have those. The Secure flag requires HTTPS, which is fine in prod but means local HTTP dev sessions won't persist cookies.

**Worth a second look**
- SameSite=Strict **will break** any OAuth redirect flows that land back on your domain — confirm you don't rely on that pattern before approving.
- Local dev over plain HTTP will silently drop the session cookie now. If your dev loop uses `localhost`, most browsers treat it as secure-context anyway, but double-check your setup.

---
**1. Approve** — accept these changes.
**2. Undo** — revert all files this turn.
```

## Handling the developer's reply

On the turn *after* you produced a review, the developer replies. Match their message (case-insensitive, trimmed):

| They reply          | You do                                                                                             |
| ------------------- | -------------------------------------------------------------------------------------------------- |
| `1`, `approve`, `yes` | Run `bash ${CLAUDE_PLUGIN_ROOT}/scripts/approve.sh <session_id>`. Then reply with a one-line confirm, like: "Approved. Changes kept." |
| `2`, `undo`, `no`     | Run `bash ${CLAUDE_PLUGIN_ROOT}/scripts/undo.sh <session_id>`. Then paste the script's output so the developer can see which files were reverted/deleted and any warnings. |
| Anything else       | Treat it as a new prompt. The snapshot.py hook will auto-clear the prior review state on the next edit (implicit approval). Don't run either script. |

The `<session_id>` was included in the Stop hook prompt that triggered the review; use that exact value. `${CLAUDE_PLUGIN_ROOT}` is set by Claude Code and points at the plugin root.

### After approve or undo

- Do not produce another review for this turn. The state is cleared.
- Do not proactively make new edits. Wait for the developer's next prompt.
- If the `undo.sh` output mentions warnings (e.g., a binary file that couldn't be snapshotted), surface those warnings clearly — the developer needs to know some changes couldn't be reverted.
