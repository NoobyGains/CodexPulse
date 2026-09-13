---
name: codexpulse
description: Configure the installed CodexPulse usage companion, preview or change themes and widgets, set focus timers, inspect usage, or configure the native Codex CLI footer. Use for CodexPulse requests; not for generic Codex configuration.
---

Find the installed project from `CODEXPULSE_HOME/installation.json`, defaulting to
`~/.codexpulse/installation.json`; its `project` field points to the checkout.
If no pointer exists, check `~/.codexpulse/project/codex_status.py` or a
CodexPulse checkout in the current workspace. Run its `codex_status.py --help`
with Python 3.11+ for the supported flags.

Use `--config` to read current display preferences. Chain compatible edits in a
single command, e.g. `--theme ocean --show cache,tokens --line2 model,effort,branch`.
`--preview` and `--show-themes` use synthetic data and do not save changes.
`--undo` restores the previous configuration; `--focus start 25` starts a timer.
Use `--doctor --cwd <project>` when quota or context is missing. `--thread <id>`
pins a session; otherwise the monitor follows the latest session in its directory.

Distinguish the two displays accurately: the native Codex footer accepts built-in
items and shows quota remaining; the companion shows quota used and supports
Pulse themes, animations, timers and extra widgets. `--install` configures the
native footer with a backup. `--launch --cwd <project>` opens Windows Terminal
with Codex above the companion; `--watch` can run in any dedicated terminal pane.
Do not write a script command into `tui.status_line` or promise to inject UI into
the Codex desktop app. Missing usage is unknown, not zero. Model buckets appear
only when Codex reports them. Cost is a Codex-provided estimate when available,
not a subscription bill. Currency conversion uses an explicitly configured rate.

Configuration changes and installing the footer should follow the user's request.
Opening a visible terminal is appropriate when they want to see or launch Pulse.
Publishing or updating repositories is separate from display configuration.
