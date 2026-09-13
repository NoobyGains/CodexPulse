# Companion display alongside Codex

Codex owns its native footer and activity animation. CodexPulse runs in a separate
terminal pane; it cannot inject themed bars into that footer.

`--native-mode auto` reads the effective `tui.status_line` settings for the monitored
directory through Codex's read-only `config/read` endpoint. It keeps supplementary
usage bars and reset timers, but omits percentages and metadata already configured
in Codex. Bars are labelled **used**, since Codex may display the percentage left.
Other model quota windows remain visible. It neither writes Codex configuration nor
stores the configuration response. The animation and widget selections are retained.

Detection reflects settings on disk, not another pane's actual pixels or command-line
overrides. If detection fails or the footer is disabled, Pulse keeps its full display.
Use `--native-mode off` when monitoring without an adjacent native Codex footer or
when the running Codex session has different settings.

```powershell
python codex_status.py --layout compact --bar-style dot --bar-size medium --animate glow --no-header --native-mode auto
```

Display edits are saved and hot reload in the companion. `--undo` restores the
previous display configuration. `--header` restores the banner; short panes hide it
automatically when it would crowd out usage. The `minimal` layout intentionally
omits bars unless adaptive mode supplies a complementary bar for a native field.

After updating Python source, restart only the companion: focus that pane, press
Ctrl+C, then run its original watch command again. Codex itself need not restart:

```powershell
python codex_status.py --watch --cwd C:\path\to\your\project
```

The path passed to `--cwd` is the project being monitored; it does not determine
which Pulse implementation runs. `CodexPulse/codex_status.py` is the Codex companion;
the separate `Pulse/claude_status.py` project targets Claude Code.

Official references:
- https://learn.chatgpt.com/docs/config-file/config-reference
- https://learn.chatgpt.com/docs/app-server
