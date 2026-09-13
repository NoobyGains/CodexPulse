"""Windows console negotiation and quiet, bounded terminal repainting."""
import ctypes
from ctypes import wintypes as wt
import os
import sys


class Coord(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


class Rect(ctypes.Structure):
    _fields_ = [(name, ctypes.c_short) for name in ("Left", "Top", "Right", "Bottom")]


class ScreenInfo(ctypes.Structure):
    _fields_ = [("size", Coord), ("cursor", Coord), ("attributes", wt.WORD),
                ("window", Rect), ("maximum", Coord)]


class CursorInfo(ctypes.Structure):
    _fields_ = [("size", wt.DWORD), ("visible", wt.BOOL)]


class WindowsConsole:
    def __init__(self, stream):
        import msvcrt
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.handle = wt.HANDLE(msvcrt.get_osfhandle(stream.fileno()))
        signatures = {
            "GetConsoleMode": [wt.HANDLE, ctypes.POINTER(wt.DWORD)],
            "SetConsoleMode": [wt.HANDLE, wt.DWORD],
            "GetConsoleScreenBufferInfo": [wt.HANDLE, ctypes.POINTER(ScreenInfo)],
            "SetConsoleCursorPosition": [wt.HANDLE, Coord],
            "FillConsoleOutputCharacterW": [wt.HANDLE, wt.WCHAR, wt.DWORD, Coord, ctypes.POINTER(wt.DWORD)],
            "FillConsoleOutputAttribute": [wt.HANDLE, wt.WORD, wt.DWORD, Coord, ctypes.POINTER(wt.DWORD)],
            "GetConsoleCursorInfo": [wt.HANDLE, ctypes.POINTER(CursorInfo)],
            "SetConsoleCursorInfo": [wt.HANDLE, ctypes.POINTER(CursorInfo)],
        }
        for name, args in signatures.items():
            fn = getattr(self.api, name)
            fn.argtypes, fn.restype = args, wt.BOOL
        mode = wt.DWORD()
        if not self.api.GetConsoleMode(self.handle, ctypes.byref(mode)):
            raise OSError("Output is not a Windows console")
        self.mode = mode.value
        self.cursor = CursorInfo()
        self.has_cursor = bool(self.api.GetConsoleCursorInfo(self.handle, ctypes.byref(self.cursor)))

    def enable_ansi(self):
        # Preserve all existing flags; VT also requires processed output.
        return bool(self.api.SetConsoleMode(self.handle, self.mode | 0x0004 | 0x0001))

    def hide_cursor(self):
        if self.has_cursor:
            cursor = CursorInfo(self.cursor.size, False)
            self.api.SetConsoleCursorInfo(self.handle, ctypes.byref(cursor))

    def clear(self):
        info = ScreenInfo()
        if not self.api.GetConsoleScreenBufferInfo(self.handle, ctypes.byref(info)):
            raise OSError("Cannot read Windows console dimensions")
        count = wt.DWORD()
        width = info.window.Right - info.window.Left + 1
        for y in range(info.window.Top, info.window.Bottom + 1):
            pos = Coord(info.window.Left, y)
            if not self.api.FillConsoleOutputCharacterW(self.handle, " ", width, pos, ctypes.byref(count)):
                raise OSError("Cannot clear Windows console")
            self.api.FillConsoleOutputAttribute(self.handle, info.attributes, width, pos, ctypes.byref(count))
        if not self.api.SetConsoleCursorPosition(self.handle, Coord(info.window.Left, info.window.Top)):
            raise OSError("Cannot position Windows console cursor")

    def restore(self):
        if self.has_cursor:
            self.api.SetConsoleCursorInfo(self.handle, ctypes.byref(self.cursor))
        self.api.SetConsoleMode(self.handle, self.mode)


class TerminalOutput:
    def __init__(self, stream=None):
        self.stream = stream or sys.stdout
        self.ansi = False
        self.console = None
        self.watching = False
        self.previous = None

    def __enter__(self):
        if self.stream.isatty():
            if os.name == "nt":
                try:
                    self.console = WindowsConsole(self.stream)
                    self.ansi = self.console.enable_ansi()
                except (OSError, ValueError):
                    self.console = None
            else:
                self.ansi = os.environ.get("TERM") != "dumb"
        return self

    def start(self):
        if not self.ansi and self.console is None:
            raise ValueError("This terminal cannot redraw safely. Use Windows Terminal, or omit --watch for a snapshot.")
        self.watching = True
        if self.ansi:
            self._write("\x1b[?1049h\x1b[?25l")
        else:
            self.console.hide_cursor()

    def draw(self, rows, size):
        value = (tuple(rows), size)
        if value == self.previous:
            return False
        if self.ansi:
            self._write("\x1b[H" + "\n".join(rows) + "\x1b[J")
        else:
            # No escape sequences at all in the legacy console fallback.
            from .render import ESCAPE
            self.console.clear()
            self._write(ESCAPE.sub("", "\n".join(rows)))
        self.previous = value
        return True

    def _write(self, value):
        self.stream.write(value)
        self.stream.flush()

    def __exit__(self, *exc):
        try:
            if self.watching and self.ansi:
                self._write("\x1b[0m\x1b[?25h\x1b[?1049l")
        finally:
            if self.console:
                self.console.restore()
