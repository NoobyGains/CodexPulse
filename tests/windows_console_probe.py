"""Run in a private, hidden Windows console; never uses the user's screen."""
import ctypes
from ctypes import wintypes as wt
import json
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codexpulse.terminal import TerminalOutput, WindowsConsole, ScreenInfo, Coord

sys.stdout.reconfigure(encoding="utf-8")
result = {}
console = WindowsConsole(sys.stdout)
original = console.mode
try:
    console.api.SetConsoleMode(console.handle, original & ~4)
    for fallback in (False, True):
        manager = patch.object(WindowsConsole, "enable_ansi", return_value=False) if fallback else patch.object(WindowsConsole, "enable_ansi", WindowsConsole.enable_ansi)
        with manager, TerminalOutput() as output:
            mode = wt.DWORD()
            console.api.GetConsoleMode(console.handle, ctypes.byref(mode))
            result["fallback" if fallback else "vt"] = {"ansi": output.ansi, "mode": mode.value}
            # Use the actual console buffer, with VT disabled before entry.
            output.start()
            output.draw(["Weekly 55% | Context 9%"], (80, 5))
            info = ScreenInfo()
            console.api.GetConsoleScreenBufferInfo(console.handle, ctypes.byref(info))
            buf = ctypes.create_unicode_buffer(80)
            count = wt.DWORD()
            read = console.api.ReadConsoleOutputCharacterW
            read.argtypes = [wt.HANDLE, wt.LPWSTR, wt.DWORD, Coord, ctypes.POINTER(wt.DWORD)]
            read.restype = wt.BOOL
            ok = read(console.handle, buf, 80, Coord(info.window.Left, info.window.Top), ctypes.byref(count))
            result["fallback" if fallback else "vt"]["text"] = buf.value if ok else "READ FAILED"
        mode = wt.DWORD()
        console.api.GetConsoleMode(console.handle, ctypes.byref(mode))
        result["fallback" if fallback else "vt"]["restored"] = not bool(mode.value & 4)
finally:
    console.api.SetConsoleMode(console.handle, original)
Path(sys.argv[1]).write_text(json.dumps(result), encoding="utf-8")
