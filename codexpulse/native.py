"""Use Codex's config writer for its native footer, with reversible installation."""
import hashlib
from pathlib import Path
import tomllib

from .rpc import Client, RpcError
from .storage import codex_home, home, read_json, write_json

PRESETS = {
    "minimal": ["five-hour-limit", "weekly-limit", "context-used"],
    "balanced": ["five-hour-limit", "weekly-limit", "context-used", "model-with-reasoning", "git-branch", "fast-mode"],
    "full": ["five-hour-limit", "weekly-limit", "context-used", "model-with-reasoning", "git-branch", "fast-mode", "used-tokens", "context-window-size", "codex-version"],
}

def configured_fields(client, cwd):
    """Read effective footer settings; retain no other configuration or credentials.

    This detects settings on disk, not pixels in another pane or CLI-only overrides.
    Unknown/disabled settings leave Pulse's full display available.
    """
    try:
        response = client.call("config/read", {"cwd": str(Path(cwd).resolve()), "includeLayers": False})
        config = response.get("config")
        tui = config.get("tui") if isinstance(config, dict) else None
        fields = tui.get("status_line") if isinstance(tui, dict) else None
        return fields if isinstance(fields, list) and all(isinstance(f, str) for f in fields) else []
    except (RpcError, OSError, ValueError):
        return []

def install(preset="balanced", path=None, client_factory=Client):
    path = Path(path or codex_home() / "config.toml").resolve()
    before = path.read_bytes() if path.exists() else b""
    tomllib.loads(before.decode("utf-8"))
    backup_path = home() / "native-backup.json"
    saved = read_json(backup_path, {})
    current_hash = hashlib.sha256(before).hexdigest()
    if saved and saved.get("path") == str(path):
        if saved.get("installed_hash") != current_hash:
            raise ValueError("Codex configuration changed since installation. Keep your edits; use /statusline to customize it, or resolve the saved backup before reinstalling.")
        original = saved["original"]
    else:
        original = before.decode("utf-8")
    backup = {"path": str(path), "original": original, "installed_hash": None}
    write_json(backup_path, backup)
    with client_factory() as client:
        client.call("config/value/write", {"keyPath": "tui.status_line", "value": PRESETS[preset],
            "mergeStrategy": "replace", "filePath": str(path)})
    after = path.read_bytes()
    if tomllib.loads(after.decode("utf-8")).get("tui", {}).get("status_line") != PRESETS[preset]:
        raise ValueError("Codex did not save the requested footer. Original configuration is in the local backup.")
    backup["installed_hash"] = hashlib.sha256(after).hexdigest()
    write_json(backup_path, backup)
    return path

def uninstall():
    saved = read_json(home() / "native-backup.json", {})
    if not saved:
        raise ValueError("No CodexPulse native-footer backup found")
    path = Path(saved["path"])
    current = path.read_bytes()
    if hashlib.sha256(current).hexdigest() != saved["installed_hash"]:
        raise ValueError("Codex config has newer edits; automatic restore stopped to preserve them. Use /statusline, or compare the original in ~/.codexpulse/native-backup.json.")
    # Atomic text replacement with the same private-file behavior as JSON state.
    import os
    import tempfile
    fd, name = tempfile.mkstemp(prefix="codexpulse-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(saved["original"])
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    (home() / "native-backup.json").unlink()
    return path
