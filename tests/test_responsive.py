import copy
import os
from unittest.mock import patch, Mock

from codexpulse.cli import configure, parser, validate, watch
from codexpulse.render import cell_width, clean, demo, render, watch_rows, wrap_text
from codexpulse.storage import DEFAULTS, config, write_json
from test_core import Isolated


class SparkPreference(Isolated):
    def snapshot(self):
        snapshot = demo() | {"model": "gpt-6-astra"}
        snapshot["windows"].append(snapshot["windows"][-1] | {
            "id": "codex_spark", "label": "GPT-5.3-Codex-Spark Weekly", "used": 27})
        snapshot["windows"].append(snapshot["windows"][-1] | {
            "id": "astra", "label": "GPT-6-Astra Weekly", "used": 61})
        return snapshot

    def test_spark_hidden_by_default_without_hiding_astra_or_shared_quota(self):
        value = render(self.snapshot(), copy.deepcopy(DEFAULTS), 300, True)
        self.assertNotIn("Spark", value)
        self.assertIn("GPT-6-Astra Weekly", value)
        self.assertIn("61%", value)
        self.assertIn("78%", value)
        self.assertIn("gpt-6-astra", value)

    def test_toggle_persists_and_preview_does_not_save(self):
        cfg, _ = configure(parser().parse_args(["--spark", "--preview"]))
        self.assertIn("Spark", render(self.snapshot(), cfg, 300, True))
        self.assertFalse(config()["spark"])
        configure(parser().parse_args(["--spark"]))
        self.assertTrue(config()["spark"])
        configure(parser().parse_args(["--no-spark"]))
        self.assertFalse(config()["spark"])
        with self.assertRaises(ValueError):
            validate(config() | {"spark": "false"})

    def test_existing_config_and_label_only_spark_identity(self):
        old = copy.deepcopy(DEFAULTS)
        old.pop("spark")
        write_json(self.root / "pulse/config.json", old)
        snapshot = self.snapshot()
        snapshot["windows"][-2]["id"] = "opaque-model-id"
        self.assertNotIn("Spark", render(snapshot, config(), 300, True))
        self.assertFalse(config()["spark"])

    def test_spark_only_never_presented_as_astra_quota(self):
        snapshot = self.snapshot()
        snapshot["windows"] = [snapshot["windows"][-2]]
        value = render(snapshot, copy.deepcopy(DEFAULTS), 120, True)
        self.assertIn("No non-Spark quota reported", value)
        self.assertNotIn("27%", value)


class ResponsiveDisplay(Isolated):
    def test_long_label_keeps_percentage_and_reset_when_wrapped(self):
        snapshot = demo()
        snapshot["windows"][-1]["label"] = "An unusually long model quota name Weekly"
        value = render(snapshot, copy.deepcopy(DEFAULTS), 20, True)
        self.assertIn("89%", value)
        self.assertIn("Weekly", value)
        self.assertTrue(all(cell_width(line) <= 20 for line in value.splitlines()))

    def test_word_wrap_preserves_colored_and_wide_tokens(self):
        value = "\x1b[31m模型verylongidentifier\x1b[0m"
        lines = wrap_text(value, 7)
        self.assertTrue(all(cell_width(line) <= 7 for line in lines))
        self.assertEqual(clean("".join(lines)), clean(value))

    def test_small_pane_keeps_core_numbers_and_restores_layout_on_growth(self):
        snapshot = demo()
        snapshot["windows"] = snapshot["windows"][:2]
        cfg = copy.deepcopy(DEFAULTS) | {"native_mode": "off",
            "widgets": ["session", "weekly", "context", "model", "effort"],
            "line2_widgets": ["model", "effort"]}
        original = copy.deepcopy(cfg)
        small = watch_rows(snapshot, cfg, 48, 3, plain=True)
        self.assertLessEqual(len(small), 2)
        for percent in ("39%", "78%", "14%"):
            self.assertIn(percent, " ".join(small))
        large = watch_rows(snapshot, cfg, 180, 20, plain=True)
        self.assertIn("━", "".join(large))
        self.assertIn("CodexPulse", large[0])
        self.assertEqual(cfg, original)

    def test_every_row_fits_width_and_height_including_extreme_sizes(self):
        for width in (1, 5, 10, 20, 40, 80, 160):
            for height in (1, 2, 3, 6, 20):
                rows = watch_rows(demo(), copy.deepcopy(DEFAULTS), width, height, plain=True)
                self.assertLessEqual(len(rows), max(1, height - 1))
                self.assertTrue(all(cell_width(row) <= width for row in rows))

    def test_overflow_is_signaled_and_wrap_off_keeps_one_row(self):
        cfg = copy.deepcopy(DEFAULTS) | {"widgets": ["model"], "header": False}
        snapshot = demo() | {"model": "abcdef" * 100}
        rows = watch_rows(snapshot, cfg, 30, 3, plain=True)
        self.assertIn("rows", rows[-1])
        self.assertEqual(len(render(snapshot, cfg | {"wrap": "off"}, 30, True).splitlines()), 1)

    def test_watch_reads_dimensions_each_frame_without_refetching_quota(self):
        cfg = copy.deepcopy(DEFAULTS)
        args = parser().parse_args(["--watch"])
        class Monitor:
            calls = 0
            def collect(self, cfg):
                self.calls += 1
                return demo()
        monitor = Monitor()
        sizes = [os.terminal_size((80, 6)), os.terminal_size((30, 3))]
        with patch("codexpulse.cli.sys.stdout.isatty", return_value=True), \
             patch("codexpulse.cli.config", return_value=cfg), \
             patch("codexpulse.cli.record_sample", return_value=[]), \
             patch("codexpulse.cli.shutil.get_terminal_size", side_effect=sizes), \
             patch("codexpulse.cli.time.monotonic", return_value=1), \
             patch("codexpulse.cli.time.sleep", side_effect=[None, KeyboardInterrupt]), \
             patch("codexpulse.cli.print"), \
             patch("codexpulse.cli.watch_rows", wraps=watch_rows) as rows:
            with self.assertRaises(KeyboardInterrupt):
                watch(monitor, cfg, args, Mock(ansi=True))
        self.assertEqual(monitor.calls, 1)
        self.assertEqual([(c.args[2], c.args[3]) for c in rows.call_args_list], [(79, 6), (29, 3)])
