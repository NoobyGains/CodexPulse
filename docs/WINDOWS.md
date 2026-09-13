# Windows Terminal and PowerShell

PowerShell Preview is supported. Pulse enables virtual terminal output before emitting color or cursor sequences and restores console settings when it exits. If VT cannot be enabled on an actual Windows console, it redraws through the Windows console API in plain ASCII. Unsupported output hosts get a one-shot suggestion instead of repeated escape codes.

## Compact Pulse row

Keep your existing palette, dots, and bar size; select only quotas and context:

```powershell
python "$HOME/.codexpulse/project/codex_status.py" --preset minimal --no-header --native-mode off --redraw changes
```

Session and Weekly show **used** percentages. Codex `/status` displays **remaining**: 45% left means 55% used. Model buckets use only identities actually reported by Codex. Selecting Astra does not manufacture an Astra-specific quota. Spark stays opt-in.

## Open Codex and Pulse together

```powershell
python "$HOME/.codexpulse/project/codex_status.py" --launch --cwd .
```

To resume and monitor an exact conversation:

```powershell
python "$HOME/.codexpulse/project/codex_status.py" --launch --thread YOUR_SESSION_ID --cwd .
```

This opens a Windows Terminal tab with Codex above Pulse. It works when invoked from a standalone PowerShell console. The separate pane is in the same window; it is not injected into Codex's native footer. Running plain `codex` still launches only Codex.

To add only Pulse to the current Windows Terminal window:

```powershell
python "$HOME/.codexpulse/project/codex_status.py" --attach --thread YOUR_SESSION_ID --cwd .
```

`--attach` uses the current `WT_SESSION` rather than guessing the most recently active window. It requires running inside Windows Terminal. Paths containing semicolons are rejected because Windows Terminal treats them as command delimiters.

Without `--thread`, `--launch` waits for a newly created session in that folder and locks onto the first match. The session may not exist until the first turn. If multiple new Codex instances start simultaneously in the same folder, use `--thread` for exact selection. `--attach` locks onto the latest existing session in the folder. A standalone `--watch` continues following the latest session unless you add `--lock-session`.

A bare `--cwd` now means the current folder, just like `--cwd .`.

The launcher resolves the installed Windows Terminal package when `wt.exe` is an execution alias and opens it visibly through Windows shell activation. For a portable installation, set `CODEXPULSE_TERMINAL` to the full path of its `WindowsTerminal.exe`. Pulse does not download or install another terminal automatically.

## Quiet refresh and optional animations

The new default `--redraw changes` skips identical rendered content. New telemetry, configuration edits, resize events, and changes in displayed countdowns can repaint. This mode freezes animation without changing the saved theme or animation preference. Existing widgets and palettes are preserved.

```powershell
python "$HOME/.codexpulse/project/codex_status.py" --redraw live --animate glow
python "$HOME/.codexpulse/project/codex_status.py" --redraw changes
python "$HOME/.codexpulse/project/codex_status.py" --ascii
python "$HOME/.codexpulse/project/codex_status.py" --no-ascii
```

`--plain` disables colors; cursor control is still used in supported terminals so the display can stay in place. The legacy console fallback uses no ANSI sequences at all. ASCII mode also substitutes portable characters for progress bars and labels.

## Optional widgets

Preview additions without changing preferences:

```powershell
python "$HOME/.codexpulse/project/codex_status.py" --preview --show tasks,active_tools,git_status,stash,project --line2 tasks,active_tools,git_status,stash,project
```

Enable them by removing `--preview`, or select individual widgets with `--show`. Hide them with `--hide`.

| Widget | Meaning |
|---|---|
| `tasks` | Completed / total steps in the latest recorded `update_plan` call |
| `active_tools` | Observed outstanding function/custom tool calls; at most three unique names plus an overflow count |
| `git_status` | Staged, modified, and untracked file counts |
| `stash` | Number of local Git stash entries |
| `project` | Git repository root folder name |

The full preset includes the new widgets; the default and minimal presets do not. Task descriptions, tool arguments, and tool outputs are not retained. Tool activity is last-recorded telemetry; interrupted or partial logs can be incomplete. Explicit turn-end events clear active calls. Git counts describe the repository, not changes attributable to Codex.

## Validation

Regression tests cover ANSI negotiation and restoration, escape-free fallback, repeated-frame suppression, resize handling, partial rollouts, session locking, argument safety, and actual Git changes. On Windows, the suite launches a hidden console with VT initially disabled and reads back the real console screen buffer for both rendering paths.

See [reference revisions and license notices](THIRD_PARTY_NOTICES.md).
