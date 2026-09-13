"""Small, atomic, private local state; never stores credentials or transcripts."""
import copy
import json
import os
from pathlib import Path
import tempfile

DEFAULTS = {
    "theme": "default", "animate": "off", "animation_speed": "normal",
    "bar_style": "classic", "bar_size": 12, "layout": "standard",
    "wrap": "auto", "color_depth": "auto", "clock": "12h",
    "header": True, "native_mode": "auto", "spark": False,
    "redraw": "changes", "ascii": False,
    "widgets": ["session", "weekly", "limits", "context", "model", "effort", "branch"],
    "line2_widgets": [], "refresh": 10, "cache_ttl": 60,
    "currency": "USD", "fx_rate": 1.0, "budget": 0.0,
    "priority": {},
}

def home():
    return Path(os.environ.get("CODEXPULSE_HOME", Path.home() / ".codexpulse"))

def codex_home():
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))

def read_json(path, fallback=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return copy.deepcopy(fallback)

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def config():
    value = read_json(home() / "config.json", {})
    if not isinstance(value, dict):
        raise ValueError("CodexPulse config.json must contain an object")
    return copy.deepcopy(DEFAULTS) | value

def save_config(value):
    path = home() / "config.json"
    history = read_json(home() / "config-history.json", [])
    history.append(config())
    write_json(home() / "config-history.json", history[-20:])
    write_json(path, value)

def undo():
    history = read_json(home() / "config-history.json", [])
    if not history:
        raise ValueError("No configuration changes to undo")
    write_json(home() / "config.json", history.pop())
    write_json(home() / "config-history.json", history)
