import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

@unittest.skipUnless(os.name == "nt", "Windows console API integration")
class RealConsole(unittest.TestCase):
    def test_vt_disabled_console_and_native_fallback_render_and_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Path(tmp) / "console.json"
            startup = subprocess.STARTUPINFO()
            startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("windows_console_probe.py")), str(result)],
                creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup)
            try:
                self.assertEqual(process.wait(timeout=20), 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
            data = json.loads(result.read_text(encoding="utf-8"))
            self.assertTrue(data["vt"]["ansi"])
            self.assertTrue(data["vt"]["mode"] & 4)
            self.assertFalse(data["fallback"]["ansi"])
            for mode in ("vt", "fallback"):
                self.assertIn("Weekly 55% | Context 9%", data[mode]["text"])
                self.assertNotIn("[H", data[mode]["text"])
                self.assertTrue(data[mode]["restored"])
