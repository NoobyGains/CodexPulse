import copy
import io
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

from codexpulse.cli import configure, launch_command, parser, terminal_executable, open_terminal
from codexpulse.data import Monitor, RolloutReader, git_metrics
from codexpulse.render import demo, render
from codexpulse.storage import DEFAULTS, config
from codexpulse.terminal import TerminalOutput
from test_core import Isolated


class TerminalTests(unittest.TestCase):
    def test_windows_enables_vt_and_restores_even_after_error(self):
        stream = Mock()
        stream.isatty.return_value = True
        console = Mock()
        console.enable_ansi.return_value = True
        with patch("codexpulse.terminal.os.name", "nt"), patch("codexpulse.terminal.WindowsConsole", return_value=console):
            with self.assertRaises(RuntimeError):
                with TerminalOutput(stream) as terminal:
                    self.assertTrue(terminal.ansi)
                    terminal.start()
                    terminal.draw(["Weekly 55%"], (80, 5))
                    raise RuntimeError("test")
        console.enable_ansi.assert_called_once()
        console.restore.assert_called_once()
        self.assertIn("\x1b[?1049l", stream.write.call_args.args[0])

    def test_no_vt_fallback_emits_no_escape_sequences(self):
        stream = Mock()
        console = Mock()
        console.enable_ansi.return_value = False
        with patch("codexpulse.terminal.os.name", "nt"), patch("codexpulse.terminal.WindowsConsole", return_value=console):
            with TerminalOutput(stream) as terminal:
                terminal.start()
                terminal.draw(["\x1b[31mWeekly 55%\x1b[0m"], (80, 5))
        self.assertEqual(stream.write.call_args.args[0], "Weekly 55%")
        console.clear.assert_called_once()
        console.restore.assert_called_once()

    def test_unchanged_frames_skipped_and_resize_repaints(self):
        stream = io.StringIO()
        terminal = TerminalOutput(stream)
        terminal.ansi = True
        self.assertTrue(terminal.draw(["Weekly 55%"], (80, 5)))
        before = stream.getvalue()
        self.assertFalse(terminal.draw(["Weekly 55%"], (80, 5)))
        self.assertEqual(before, stream.getvalue())
        self.assertTrue(terminal.draw(["Weekly 55%"], (60, 5)))
        self.assertTrue(terminal.draw(["Weekly 56%"], (60, 5)))

    def test_pipes_never_enable_ansi_and_cannot_watch(self):
        with TerminalOutput(io.StringIO()) as terminal:
            self.assertFalse(terminal.ansi)
            with self.assertRaises(ValueError):
                terminal.start()


class OptionalFeatures(Isolated):
    def test_default_stays_simple_and_preview_does_not_save(self):
        before = config()
        cfg, _ = configure(parser().parse_args(["--show", "tasks,active_tools,git_status,stash,project", "--ascii", "--redraw", "live", "--preview"]))
        self.assertEqual(config(), before)
        for name in ("tasks", "active_tools", "git_status", "stash", "project"):
            self.assertNotIn(name, DEFAULTS["widgets"])
            self.assertIn(name, cfg["widgets"])
        self.assertTrue(cfg["ascii"])

    def test_ascii_and_optional_widgets_render_without_controls(self):
        cfg = copy.deepcopy(DEFAULTS) | {"ascii": True, "widgets": ["session", "tasks", "active_tools", "git_status", "stash", "project"]}
        output = render(demo(), cfg, 300, True)
        self.assertTrue(output.isascii())
        self.assertNotIn("\x1b", output)
        self.assertIn("Tasks 2/5", output)
        self.assertIn("exec_command", output)
        self.assertIn("staged 1 modified 2 untracked 1", output)
        self.assertIn("Stash 2", output)

    def test_tool_completion_and_plan_counts_discard_private_arguments(self):
        reader = RolloutReader()
        reader.consume("response_item", {"type": "function_call", "name": "functions.update_plan", "call_id": "p",
            "arguments": json.dumps({"plan": [{"step": "PRIVATE", "status": "completed"}, {"step": "SECRET", "status": "in_progress"}]})})
        self.assertEqual(reader.state["tasks"], {"total": 2, "completed": 1, "in_progress": 1})
        self.assertEqual(reader.state["active_tools"], ["functions.update_plan"])
        reader.consume("response_item", {"type": "function_call_output", "call_id": "p", "output": "PRIVATE"})
        self.assertEqual(reader.state["active_tools"], [])
        self.assertNotIn("PRIVATE", json.dumps(reader.state))
        self.assertNotIn("SECRET", json.dumps(reader.state))
        reader.consume("response_item", {"type": "function_call", "name": "update_plan", "arguments": "bad"})
        self.assertEqual(reader.state["tasks"]["total"], 2)

    def test_session_switch_and_turn_end_clear_active_tools(self):
        a, b = self.root / "a", self.root / "b"
        a.write_text(json.dumps({"type": "response_item", "payload": {"type": "custom_tool_call", "call_id": "c", "name": "exec"}}) + "\n")
        b.write_text("{}\n")
        reader = RolloutReader()
        self.assertEqual(reader.read(a)["active_tools"], ["exec"])
        self.assertNotIn("active_tools", reader.read(b))
        reader.consume("response_item", {"type": "function_call", "call_id": "c", "name": "exec"})
        reader.consume("event_msg", {"type": "task_aborted"})
        self.assertEqual(reader.state["active_tools"], [])

    def test_git_counts_include_rename_as_one_and_stash(self):
        repo = self.root / "git repo"
        repo.mkdir()
        def git(*args):
            subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
        git("init")
        git("config", "user.name", "Pulse Test")
        git("config", "user.email", "pulse@example.invalid")
        (repo / "old.txt").write_text("base")
        (repo / "tracked.txt").write_text("base")
        git("add", ".")
        git("commit", "-m", "base")
        (repo / "tracked.txt").write_text("stash change")
        git("stash", "push", "-m", "fixture")
        git("mv", "old.txt", "new name.txt")
        (repo / "tracked.txt").write_text("modified")
        (repo / "untracked.txt").write_text("new")
        result = git_metrics(repo, extra=True)
        self.assertEqual((result["staged"], result["modified"], result["untracked"]), (1, 1, 1))
        self.assertEqual(result["files"], 3)
        self.assertEqual(result["stash"], 1)
        self.assertEqual(result["project"], "git repo")


class SessionLaunch(Isolated):
    def test_bare_cwd_uses_current_directory(self):
        self.assertEqual(parser().parse_args(["--watch", "--cwd"]).cwd, os.getcwd())

    def test_lock_ignores_old_sessions_and_does_not_follow_newer_work(self):
        client = Mock()
        client.call.side_effect = [
            {"data": [{"id": "old", "createdAt": 10}]},
            {"data": [{"id": "newer", "createdAt": 120}, {"id": "ours", "createdAt": 100}]},
            {"thread": {"id": "ours", "createdAt": 100}},
        ]
        monitor = Monitor(client, ".", lock_session=True, started_after=100.2)
        self.assertEqual(monitor.select_thread(), {})
        self.assertEqual(monitor.select_thread()["id"], "ours")
        self.assertEqual(monitor.select_thread()["id"], "ours")
        self.assertEqual(client.call.call_args.args, ("thread/read", {"threadId": "ours", "includeTurns": False}))

    def test_attach_targets_current_window_and_exact_thread(self):
        with patch("codexpulse.cli.shutil.which", return_value="wt.exe"), patch.dict(os.environ, {"WT_SESSION": "window-id"}), patch("codexpulse.cli.codex_command") as codex:
            command = launch_command(str(self.root / "space dir"), "exact-thread", attach=True)
        codex.assert_not_called()
        self.assertEqual(command[:3], ["wt.exe", "-w", "window-id"])
        self.assertIn("--thread", command)
        self.assertIn("exact-thread", command)
        self.assertNotIn("new-tab", command)

    def test_launch_resumes_same_thread_and_plain_is_forwarded(self):
        with patch("codexpulse.cli.shutil.which", return_value="wt.exe"), patch("codexpulse.cli.codex_command", return_value=["codex.exe"]):
            command = launch_command(".", "exact-thread", plain=True)
        self.assertIn("resume", command)
        self.assertEqual(command.count("exact-thread"), 2)
        self.assertIn("--plain", command)

    def test_attach_requires_windows_terminal_and_rejects_command_delimiters(self):
        with patch("codexpulse.cli.shutil.which", return_value="wt.exe"), patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                launch_command(".", attach=True)
            with self.assertRaises(ValueError):
                launch_command("bad;path")


class TerminalLauncher(Isolated):
    def test_override_is_explicit_and_validated(self):
        exe = self.root / "WindowsTerminal.exe"
        exe.write_bytes(b"fixture")
        with patch.dict(os.environ, {"CODEXPULSE_TERMINAL": str(exe)}):
            self.assertEqual(terminal_executable(), str(exe))
        with patch.dict(os.environ, {"CODEXPULSE_TERMINAL": str(self.root / "missing")}):
            with self.assertRaises(ValueError):
                terminal_executable()

    @unittest.skipUnless(os.name == "nt", "Windows shell activation")
    def test_shell_activation_preserves_spaces_and_reports_errors(self):
        shell = Mock()
        shell.ShellExecuteW.return_value = 33
        with patch("ctypes.WinDLL", return_value=shell):
            open_terminal(["C:/Program Files/Terminal.exe", "new-tab", "C:/space dir/python.exe"])
        args = shell.ShellExecuteW.call_args.args
        self.assertEqual(args[2], "C:/Program Files/Terminal.exe")
        self.assertIn('"C:/space dir/python.exe"', args[3])
        self.assertEqual(args[-1], 1)
        shell.ShellExecuteW.return_value = 2
        with patch("ctypes.WinDLL", return_value=shell), self.assertRaises(OSError):
            open_terminal(["missing"])

    @unittest.skipUnless(os.name == "nt", "Windows app execution alias")
    def test_zero_byte_alias_resolves_installed_package(self):
        alias = self.root / "wt.exe"
        alias.write_bytes(b"")
        package = self.root / "package"
        package.mkdir()
        exe = package / "WindowsTerminal.exe"
        exe.write_bytes(b"fixture")
        with patch.dict(os.environ, {"CODEXPULSE_TERMINAL": ""}), patch("codexpulse.cli.shutil.which", side_effect=[str(alias), "pwsh"]), patch("codexpulse.cli.subprocess.run", return_value=Mock(stdout=str(package), returncode=0)):
            self.assertEqual(terminal_executable(), str(exe))
