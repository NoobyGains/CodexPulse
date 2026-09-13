# Changelog

## Unreleased

- Fix raw ANSI color/cursor codes in Windows consoles by enabling VT output and restoring console state; fall back to native console drawing and ASCII when VT is unavailable.
- Skip unchanged watch frames by default; retain optional animation with `--redraw live`.
- Keep the compact Pulse display and add opt-in task progress, active tools, Git status, stash, and project widgets.
- Add ASCII display mode, current-window pane attachment, session locking, and visible shell activation for Windows Terminal execution aliases.
- Accept a bare `--cwd` as the current directory.
- Preserve responsive wrapping, height adaptation, and opt-in Spark filtering.
- Document reference implementations and their MIT license notices.
- Verify rendering through real Windows console screen-buffer tests.

## 0.1.0 — 2026-09-13

- Adapt Pulse to Codex with a reversible native footer installer and full terminal companion.
- Read actual quota windows and model buckets through Codex app-server; retain last known data with backoff on request failure.
- Read bounded incremental context, token, and activity metadata from Codex rollouts.
- Carry over fifteen palettes, eight bar styles, five animation modes, widget ordering, two-row layouts, and focus timers.
- Add Codex token/cache details, account activity, explicit estimated-cost widgets, project/thread selection, and JSON output.
- Add Windows Terminal launch, cross-platform installers, a conversational helper, tests, and a Codex-specific README.
- Include adaptive display support that complements configured native footer fields, plus a hideable banner for small panes.

Earlier Claude Pulse history is preserved in Git; see the upstream project for its releases.
