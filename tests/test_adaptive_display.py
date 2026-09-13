import copy
import os
import unittest
from unittest.mock import patch

from codexpulse.cli import configure, parser, validate
from codexpulse.native import configured_fields
from codexpulse.render import clean, demo, render, watch_rows
from codexpulse.rpc import RpcError
from codexpulse.storage import DEFAULTS
from test_core import Isolated


class AdaptiveDisplay(Isolated):
    def setUp(self):
        super().setUp()
        self.cfg = copy.deepcopy(DEFAULTS) | {
            "layout": "compact", "bar_style": "dot", "animate": "glow",
        }
        self.snapshot = demo() | {
            "native_fields": ["weekly-limit", "context-used", "model-with-reasoning", "git-branch"],
        }

    def test_native_numbers_have_complementary_bars_and_no_repeated_metadata(self):
        output = render(self.snapshot, self.cfg, 500, True)
        self.assertIn("Weekly used ●", output)
        self.assertIn("Context used ●", output)
        self.assertNotIn("78%", output)
        self.assertNotIn("14%", output)
        self.assertNotIn("codex-model", output)
        self.assertNotIn("Effort high", output)
        self.assertNotIn("main", output)
        self.assertIn("39%", output)  # No session item in the native footer.
        self.assertIn("89%", output)  # Other model quotas must remain visible.

    def test_disabled_detection_restores_the_requested_widgets(self):
        output = render(self.snapshot, self.cfg | {"native_mode": "off"}, 500, True)
        self.assertIn("78%", output)
        self.assertIn("codex-model", output)
        self.assertIn("Effort high", output)

    def test_missing_native_fields_keeps_full_information(self):
        output = render(demo(), self.cfg, 500, True)
        self.assertIn("78%", output)
        self.assertIn("codex-model", output)

    def test_adaptive_minimal_still_shows_supplementary_bars(self):
        output = render(self.snapshot, self.cfg | {"layout": "minimal"}, 500, True)
        self.assertIn("Weekly used ●", output)

    def test_dot_animation_is_preserved(self):
        with patch.dict(os.environ):
            os.environ.pop("NO_COLOR", None)
            first = render(self.snapshot, self.cfg | {"color_depth": "truecolor"}, 500, frame=0)
            next_frame = render(self.snapshot, self.cfg | {"color_depth": "truecolor"}, 500, frame=5)
        self.assertIn("●", clean(first))
        self.assertEqual(clean(first), clean(next_frame))
        self.assertNotEqual(first, next_frame)

    def test_header_never_crowds_out_usage(self):
        rows = watch_rows(self.snapshot, self.cfg, 60, 2, plain=True)
        self.assertEqual(len(rows), 1)
        self.assertIn("Session", rows[0])
        self.assertNotIn("CodexPulse", rows[0])

    def test_header_toggle_and_validation(self):
        rows = watch_rows(self.snapshot, self.cfg, 500, 20, plain=True)
        self.assertIn("CodexPulse", rows[0])
        self.assertNotIn("CodexPulse", "\n".join(watch_rows(
            self.snapshot, self.cfg | {"header": False}, 500, 20, plain=True)))
        cfg, changed = configure(parser().parse_args(["--no-header", "--native-mode", "off", "--preview"]))
        self.assertTrue(changed)
        self.assertFalse(cfg["header"])
        self.assertEqual(cfg["native_mode"], "off")
        for changes in ({"header": "false"}, {"native_mode": "invalid"}):
            with self.assertRaises(ValueError):
                validate(self.cfg | changes)


class NativeFields(unittest.TestCase):
    def test_effective_project_settings_are_requested_without_persisting_other_config(self):
        calls = []
        class Fake:
            def call(self, method, params):
                calls.append((method, params))
                return {"config": {"tui": {"status_line": ["weekly-limit"]}, "unrelated": "not retained"}}
        self.assertEqual(configured_fields(Fake(), "."), ["weekly-limit"])
        self.assertEqual(calls[0][0], "config/read")
        self.assertFalse(calls[0][1]["includeLayers"])
        self.assertIn("cwd", calls[0][1])

    def test_unavailable_disabled_and_malformed_configs_keep_fallback(self):
        for value in ({}, {"config": None}, {"config": {"tui": None}},
                      {"config": {"tui": {"status_line": None}}},
                      {"config": {"tui": {"status_line": [123]}}}):
            class Fake:
                def call(self, *args):
                    return value
            self.assertEqual(configured_fields(Fake(), "."), [])
        class Offline:
            def call(self, *args):
                raise RpcError("unavailable")
        self.assertEqual(configured_fields(Offline(), "."), [])


if __name__ == "__main__":
    unittest.main()
