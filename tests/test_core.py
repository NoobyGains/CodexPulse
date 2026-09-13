import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codexpulse.cli import configure, parser, validate
from codexpulse.data import RolloutReader, cached_call, normalize_limits, token_metrics
from codexpulse import native
from codexpulse.render import ANIMATIONS, STYLES, THEMES, cell_width, clean, demo, render
from codexpulse.rpc import RpcError
from codexpulse.storage import DEFAULTS, config, save_config, undo, write_json

class Isolated(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"CODEXPULSE_HOME": str(self.root / "pulse"), "CODEX_HOME": str(self.root / "codex")})
        self.env.start()
    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

class Quotas(Isolated):
    def test_primary_weekly_is_not_mislabeled_session(self):
        r = normalize_limits({"rateLimits": {"primary": {"usedPercent": 19, "windowDurationMins": 10080}}})
        self.assertEqual(r["windows"][0]["kind"], "weekly")
        self.assertEqual(r["windows"][0]["label"], "Weekly")
    def test_unknown_windows_and_buckets_keep_real_identity(self):
        r = normalize_limits({"rateLimitsByLimitId": {"codex_other": {"primary": {"usedPercent": 20, "windowDurationMins": 60}}}})
        self.assertEqual(r["windows"][0]["label"], "codex_other 1h")
    def test_missing_and_nonfinite_are_not_zero(self):
        for value in (None, "bad", float("nan"), float("inf"), True):
            self.assertFalse(normalize_limits({"rateLimits": {"primary": {"usedPercent": value}}})["windows"])
    def test_snake_case_and_clamping(self):
        r = normalize_limits({"rate_limits": {"primary": {"used_percent": 120, "window_minutes": 300, "resets_at": 10}}})
        self.assertEqual(r["windows"][0]["used"], 100)
        self.assertEqual(r["windows"][0]["kind"], "session")
    def test_tokens_use_last_context_not_cumulative(self):
        result = token_metrics({"last_token_usage": {"total_tokens": 140}, "total_token_usage": {"total_tokens": 999999, "input_tokens": 1000, "cached_input_tokens": 800}, "model_context_window": 1000})
        self.assertAlmostEqual(result["context"], 14)
        self.assertEqual(result["cache"], 80)
    def test_zero_context_unknown_cache(self):
        self.assertIsNone(token_metrics({})["context"])
        self.assertEqual(token_metrics({"last": {"totalTokens": 0}, "modelContextWindow": 1000})["context"], 0)
    def test_cache_failure_backoff_retains_last_good(self):
        class Broken:
            count = 0
            def call(self, *args):
                self.count += 1
                raise RpcError("offline")
        client = Broken()
        write_json(self.root / "pulse/limits.json", {"at": 1, "value": {"rateLimits": {"primary": {"usedPercent": 42}}}})
        first = cached_call(client, "account/rateLimits/read", {}, "limits", 60)
        second = cached_call(client, "account/rateLimits/read", {}, "limits", 60)
        self.assertEqual(first[0], second[0])
        self.assertEqual(client.count, 1)
        self.assertEqual(first[0]["rateLimits"]["primary"]["usedPercent"], 42)

class Rollouts(Isolated):
    def test_partial_write_retried_and_never_returns_prompt(self):
        path = self.root / "rollout.jsonl"
        event = json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {"model_context_window": 1000}}})
        path.write_text(json.dumps({"type": "response_item", "payload": {"type": "message", "text": "private user prompt"}}) + "\n" + event[:30])
        reader = RolloutReader()
        self.assertNotIn("tokens", reader.read(path))
        with path.open("a") as f:
            f.write(event[30:] + "\n")
        value = reader.read(path)
        self.assertEqual(value["tokens"]["model_context_window"], 1000)
        self.assertNotIn("private user prompt", json.dumps(value))
    def test_switch_session_resets_counters(self):
        a, b = self.root / "a", self.root / "b"
        a.write_text(json.dumps({"type": "response_item", "payload": {"type": "function_call", "name": "exec"}}) + "\n")
        b.write_text("{}\n")
        reader = RolloutReader()
        self.assertEqual(reader.read(a)["tools"], 1)
        self.assertNotIn("tools", reader.read(b))
    def test_compaction_clears_context(self):
        reader = RolloutReader()
        reader.consume("event_msg", {"type": "token_count", "info": {"model_context_window": 1000}})
        reader.consume("compacted", {})
        self.assertNotIn("tokens", reader.state)

class Display(Isolated):
    def test_all_themes_styles_and_animation_frames_fit(self):
        for theme in THEMES:
            for style in STYLES:
                for animation in ANIMATIONS:
                    cfg = copy.deepcopy(DEFAULTS) | {"theme": theme, "bar_style": style, "animate": animation}
                    output = render(demo(), cfg, 65, frame=7)
                    self.assertTrue(all(cell_width(line) <= 65 for line in output.splitlines()))
    def test_minimal_matches_requested_shape(self):
        cfg = copy.deepcopy(DEFAULTS) | {"layout": "minimal", "widgets": ["session", "weekly", "limits", "context"]}
        value = render(demo(), cfg, 180, True)
        self.assertIn("Session 39% 3h 31m", value)
        self.assertIn("Context 14%", value)
        self.assertNotIn("\x1b", value)
    def test_ansi_and_control_injection_removed(self):
        self.assertEqual(clean("main\x1b[2J\n\x07"), "main")
        s = demo() | {"model": "model\x1b]0;bad\x07\nname"}
        self.assertNotIn("bad", render(s, copy.deepcopy(DEFAULTS), 150, True))
    def test_wide_characters_and_unknown_data(self):
        value = render({"model": "模型" * 50}, copy.deepcopy(DEFAULTS), 20, True)
        self.assertTrue(all(cell_width(line) <= 20 for line in value.splitlines()))
        self.assertIn("Context ?", value)
    def test_line_two_moves_widget_without_duplicate(self):
        cfg = copy.deepcopy(DEFAULTS) | {"line2_widgets": ["model", "effort"]}
        value = render(demo(), cfg, 300, True)
        self.assertEqual(value.count("codex-model"), 1)
        self.assertIn("\ncodex-model", value)
    def test_expired_quota_is_pending_not_zero(self):
        value = demo()
        value["windows"][0]["reset"] = 1
        output = render(value, copy.deepcopy(DEFAULTS), 300, True)
        self.assertIn("refresh pending", output)
        self.assertIn("39%", output)

class Configuration(Isolated):
    def test_invalid_numbers_rejected(self):
        for key, value in (("budget", float("nan")), ("refresh", 0), ("fx_rate", -1), ("cache_ttl", 1)):
            with self.assertRaises(ValueError):
                validate(copy.deepcopy(DEFAULTS) | {key: value})
    def test_preview_does_not_write_and_undo_restores(self):
        cfg, changed = configure(parser().parse_args(["--theme", "ocean", "--preview"]))
        self.assertEqual(cfg["theme"], "ocean")
        self.assertFalse((self.root / "pulse/config.json").exists())
        save_config(copy.deepcopy(DEFAULTS) | {"theme": "candy"})
        undo()
        self.assertEqual(config()["theme"], "default")
    def test_native_install_preserves_and_restores(self):
        path = self.root / "codex/config.toml"
        path.parent.mkdir()
        original = '# user comment\nmodel = "example"\n[tui]\nnotifications = false\n'
        path.write_text(original, encoding="utf-8")
        class Fake:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def call(self, method, params):
                self_method = method
                assert self_method == "config/value/write"
                path.write_text(original + "status_line = " + json.dumps(params["value"]) + "\n", encoding="utf-8")
        native.install(path=path, client_factory=Fake)
        self.assertIn('model = "example"', path.read_text())
        self.assertIn("# user comment", path.read_text())
        native.uninstall()
        self.assertEqual(path.read_text(), original)
    def test_native_uninstall_refuses_to_clobber_new_edits(self):
        path = self.root / "codex/config.toml"
        path.parent.mkdir()
        path.write_text("# newer edit\n")
        write_json(self.root / "pulse/native-backup.json", {"path": str(path), "original": "", "installed_hash": "other"})
        with self.assertRaises(ValueError):
            native.uninstall()
        self.assertEqual(path.read_text(), "# newer edit\n")

if __name__ == "__main__":
    unittest.main()
