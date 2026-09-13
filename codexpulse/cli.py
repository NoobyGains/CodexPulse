"""CodexPulse command-line entrypoint."""
import argparse
import copy
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

from . import __version__
from .data import Monitor, record_sample
from . import native
from .render import ANIMATIONS, STYLES, THEMES, WIDGETS, clean, demo, render, watch_rows
from .rpc import Client, RpcError, codex_command
from .storage import DEFAULTS, config, home, read_json, save_config, undo, write_json

PRESETS = {
    "minimal": ["session", "weekly", "limits", "context"],
    "balanced": DEFAULTS["widgets"],
    "full": ["session", "weekly", "limits", "context", "model", "effort", "branch", "tokens", "cache", "activity", "heartbeat", "focus", "files", "lines", "plan", "credits"],
}

def parser():
    p = argparse.ArgumentParser(description="CodexPulse — native Codex footer + themed usage companion (no runtime dependencies).")
    p.add_argument("--version", action="version", version="CodexPulse " + __version__)
    p.add_argument("--watch", action="store_true", help="refresh in a dedicated terminal pane; Ctrl+C exits")
    p.add_argument("--header", action=argparse.BooleanOptionalAction, default=None,
        help="show or hide the companion banner (saved; --no-header hides it)")
    p.add_argument("--native-mode", choices=("auto", "off"),
        help="auto complements configured Codex footer fields; off shows all Pulse fields")
    p.add_argument("--launch", action="store_true", help="open Codex above a Pulse pane in Windows Terminal")
    p.add_argument("--cwd", default=os.getcwd(), help="monitor the latest session in this directory")
    p.add_argument("--thread", help="pin an exact Codex thread ID")
    p.add_argument("--refresh", type=float, help="metadata refresh seconds, minimum 2; quota is cached separately")
    p.add_argument("--json", action="store_true", help="emit normalized metadata as JSON")
    p.add_argument("--plain", action="store_true", help="disable ANSI colors")
    p.add_argument("--width", type=int, help="terminal width override")
    p.add_argument("--preview", action="store_true", help="render labeled demo data offline")
    p.add_argument("--show-themes", "--themes", action="store_true", help="preview all fifteen themes offline")
    p.add_argument("--pick-theme", "--pick", action="store_true", help="interactive theme selection")
    p.add_argument("--theme", choices=THEMES)
    p.add_argument("--animate", choices=ANIMATIONS)
    p.add_argument("--animation-speed", choices=("slow", "normal", "fast"))
    p.add_argument("--bar-style", choices=STYLES)
    p.add_argument("--bar-size", choices=("small", "small-medium", "medium", "medium-large", "large"))
    p.add_argument("--layout", choices=("standard", "compact", "minimal", "percent-first"))
    p.add_argument("--wrap", choices=("auto", "off"))
    p.add_argument("--color-depth", choices=("auto", "truecolor", "256", "16", "none"))
    p.add_argument("--clock", choices=("12h", "24h"))
    p.add_argument("--show", help="enable comma-separated widgets in the listed order")
    p.add_argument("--hide", help="disable comma-separated widgets")
    p.add_argument("--line2", help="move comma-separated widgets onto a second row; empty clears")
    p.add_argument("--priority", help="widget=number,widget=number; lower numbers display first")
    p.add_argument("--widgets", action="store_true", help="list available widgets")
    p.add_argument("--preset", choices=PRESETS)
    p.add_argument("--budget", type=float, help="optional USD ceiling for Codex-reported estimated cost")
    p.add_argument("--currency", help="three-letter display currency, e.g. SGD")
    p.add_argument("--fx-rate", type=float, help="explicit conversion rate from USD (1 USD = this many units)")
    p.add_argument("--focus", nargs="+", metavar="ACTION", help="start [minutes], pause, resume, or stop")
    p.add_argument("--stats", action="store_true", help="read official account token activity")
    p.add_argument("--heatmap", action="store_true", help="show official daily token buckets")
    p.add_argument("--config", action="store_true", help="print CodexPulse configuration")
    p.add_argument("--undo", action="store_true", help="undo the last display configuration edit")
    p.add_argument("--reset", action="store_true", help="restore display defaults (undoable)")
    p.add_argument("--install", action="store_true", help="configure the native Codex footer with backup")
    p.add_argument("--install-skill", action="store_true", help="install the conversational $codexpulse configuration helper")
    p.add_argument("--uninstall", action="store_true", help="restore the backed-up Codex configuration if unchanged")
    p.add_argument("--native-preview", action="store_true", help="print the native footer TOML without changing files")
    p.add_argument("--doctor", action="store_true", help="check Codex executable, login quota, and local session telemetry")
    p.add_argument("--check-updates", action="store_true", help="check GitHub for a CodexPulse release")
    p.add_argument("--update", action="store_true", help="fast-forward a clean CodexPulse git checkout")
    return p

def names(value):
    result = list(dict.fromkeys(x.strip() for x in value.split(",") if x.strip()))
    unknown = set(result) - set(WIDGETS)
    if unknown:
        raise ValueError("Unknown widgets: " + ", ".join(sorted(unknown)) + "; see --widgets")
    return result

def validate(cfg):
    for key, choices in (("theme", THEMES), ("animate", ANIMATIONS), ("bar_style", STYLES),
        ("layout", ("standard", "compact", "minimal", "percent-first")), ("wrap", ("auto", "off")),
        ("native_mode", ("auto", "off")),
        ("animation_speed", ("slow", "normal", "fast")), ("clock", ("12h", "24h")),
        ("color_depth", ("auto", "none", "truecolor", "256", "16"))):
        if cfg.get(key) not in choices:
            raise ValueError(f"Invalid {key} in configuration")
    if not isinstance(cfg.get("header"), bool):
        raise ValueError("header must be true or false")
    for key in ("widgets", "line2_widgets"):
        if not isinstance(cfg[key], list) or any(x not in WIDGETS for x in cfg[key]):
            raise ValueError(f"Invalid {key}; use --widgets to list supported names")
    if not isinstance(cfg["bar_size"], int) or not 1 <= cfg["bar_size"] <= 40:
        raise ValueError("bar_size must be an integer from 1 to 40")
    for key, minimum in (("refresh", 2), ("cache_ttl", 30), ("fx_rate", .000001), ("budget", 0)):
        value = cfg[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
            raise ValueError(f"{key} must be a finite number >= {minimum}")
    if not isinstance(cfg["currency"], str) or len(cfg["currency"]) != 3 or not cfg["currency"].isascii() or not cfg["currency"].isalpha():
        raise ValueError("currency must be a three-letter code such as USD or SGD")
    if not isinstance(cfg["priority"], dict) or any(k not in WIDGETS or not isinstance(v, int) for k, v in cfg["priority"].items()):
        raise ValueError("priority must map widget names to integer positions")

def configure(args):
    cfg = copy.deepcopy(DEFAULTS) if args.reset else config()
    changed = args.reset
    if args.preset:
        cfg["widgets"], cfg["line2_widgets"], cfg["priority"] = list(PRESETS[args.preset]), [], {}
        changed = True
    for key in ("theme", "animate", "animation_speed", "bar_style", "layout", "wrap", "color_depth", "clock", "refresh", "budget", "currency", "fx_rate", "header", "native_mode"):
        value = getattr(args, key)
        if value is not None:
            cfg[key] = value.upper() if key == "currency" else value
            changed = True
    if args.bar_size:
        cfg["bar_size"] = {"small": 4, "small-medium": 6, "medium": 8, "medium-large": 10, "large": 12}[args.bar_size]
        changed = True
    if args.show is not None:
        cfg["widgets"] = list(dict.fromkeys(cfg["widgets"] + names(args.show)))
        changed = True
    if args.hide is not None:
        hidden = names(args.hide)
        cfg["widgets"] = [x for x in cfg["widgets"] if x not in hidden]
        cfg["line2_widgets"] = [x for x in cfg["line2_widgets"] if x not in hidden]
        changed = True
    if args.line2 is not None:
        cfg["line2_widgets"] = names(args.line2)
        changed = True
    if args.priority:
        for pair in args.priority.split(","):
            key, value = pair.split("=", 1)
            names(key)
            cfg["priority"][key] = int(value)
        changed = True
    validate(cfg)
    # Preview flags form a genuine dry run, even when chained with theme/preset flags.
    if changed and not (args.preview or args.show_themes or args.native_preview):
        save_config(cfg)
    return cfg, changed

def focus_action(words):
    action, *rest = words
    path = home() / "focus.json"
    value = read_json(path, {})
    now = time.time()
    if action == "start":
        minutes = float(rest[0]) if rest else 25
        if not math.isfinite(minutes) or not 0 < minutes <= 1440:
            raise ValueError("Focus duration must be between 0 and 1440 minutes")
        value = {"end": now + minutes * 60}
    elif action == "pause":
        value = {"remaining": max(0, value.get("end", now) - now)}
    elif action == "resume":
        value = {"end": now + value.get("remaining", 0)}
    elif action == "stop":
        value = {}
    else:
        raise ValueError("Focus action must be start, pause, resume, or stop")
    write_json(path, value)
    print("Focus " + action)

def launch_command(cwd, thread=None):
    wt = shutil.which("wt")
    if not wt:
        raise ValueError("Windows Terminal (wt) is required for --launch. Elsewhere run --watch in a split terminal pane.")
    script = Path(__file__).resolve().parents[1] / "codex_status.py"
    if not script.is_file():
        raise ValueError("--launch requires a git checkout. Run codexpulse --watch in a separate pane for pip installs.")
    watch = [sys.executable, str(script), "--watch", "--cwd", str(Path(cwd).resolve())]
    codex = codex_command()
    if thread:
        watch += ["--thread", thread]
        codex += ["resume", thread]
    return [wt, "new-tab", "--title", "CodexPulse", "-d", str(Path(cwd).resolve()), *codex,
        ";", "split-pane", "-H", "--size", ".2", "-d", str(Path(cwd).resolve()), *watch,
        ";", "move-focus", "up"]

def update():
    root = Path(__file__).resolve().parents[1]
    def run(*args):
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30, check=True).stdout.strip()
    if run("remote", "get-url", "origin").removesuffix(".git").lower() not in ("https://github.com/noobygains/codexpulse", "git@github.com:noobygains/codexpulse"):
        raise ValueError("Update requires the official NoobyGains/CodexPulse checkout")
    if run("status", "--porcelain"):
        raise ValueError("Commit or stash local changes before updating")
    if run("branch", "--show-current") != "main":
        raise ValueError("Update requires the main branch")
    print(run("pull", "--ff-only", "origin", "main"))

def check_updates():
    request = urllib.request.Request("https://api.github.com/repos/NoobyGains/CodexPulse/releases/latest", headers={"User-Agent": "CodexPulse/" + __version__})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            tag = json.load(response)["tag_name"]
        print("Installed " + __version__ + " | Latest " + clean(tag))
    except OSError:
        print("Release information unavailable. Installed " + __version__)

def watch(monitor, cfg, args):
    if not sys.stdout.isatty():
        raise ValueError("--watch needs an interactive terminal; use --json or a one-shot command when piping")
    next_read, frame, snapshot = 0, 0, {}
    print("\x1b[?1049h\x1b[?25l", end="", flush=True)
    try:
        while True:
            now = time.monotonic()
            if now >= next_read:
                fresh = config()
                validate(fresh)
                cfg = fresh
                snapshot = monitor.collect(cfg)
                snapshot["samples"] = record_sample(snapshot)
                next_read = now + cfg["refresh"]
            elapsed = max(0, time.time() - snapshot.get("at", time.time()))
            live = snapshot | {"at": time.time(), "age": snapshot.get("age", 0) + elapsed}
            width, height = shutil.get_terminal_size((120, 20))
            width = max(10, min(args.width or width, width) - 1)
            rows = watch_rows(live, cfg, width, height, args.thread, args.plain, frame)
            print("\x1b[H" + "\n".join(rows) + "\x1b[J", end="", flush=True)
            frame += 1
            time.sleep(.2 if cfg["animate"] != "off" or cfg["theme"] == "rainbow" else 1)
    finally:
        print("\x1b[0m\x1b[?25h\x1b[?1049l", end="", flush=True)

def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parser().parse_args(argv)
    try:
        if args.undo:
            undo()
            print("Restored previous display configuration")
            return 0
        cfg, changed = configure(args)
        width = args.width or shutil.get_terminal_size((120, 20)).columns
        if width < 10:
            raise ValueError("--width must be at least 10")
        if args.native_preview:
            print("[tui]\nstatus_line = " + json.dumps(native.PRESETS[args.preset or "balanced"]))
        elif args.install:
            print("Native footer configured in " + str(native.install(args.preset or "balanced")) + ". Restart Codex to apply.")
            write_json(home() / "installation.json", {"project": str(Path(__file__).resolve().parents[1])})
        elif args.install_skill:
            from .storage import codex_home
            source = Path(__file__).resolve().parents[1] / "plugins/codexpulse/skills/codexpulse/SKILL.md"
            target = codex_home() / "skills/codexpulse/SKILL.md"
            if not source.is_file():
                raise ValueError("Skill installation requires the CodexPulse git checkout")
            if target.exists() and target.read_bytes() != source.read_bytes():
                raise ValueError("An existing codexpulse skill differs; preserve it or remove it before installing this version")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            write_json(home() / "installation.json", {"project": str(Path(__file__).resolve().parents[1])})
            print("Installed $codexpulse helper. Start a new Codex session to use it.")
        elif args.uninstall:
            print("Restored " + str(native.uninstall()))
        elif args.launch:
            subprocess.run(launch_command(args.cwd, args.thread), check=True, timeout=15)
        elif args.widgets:
            print(", ".join(WIDGETS))
        elif args.config:
            print(json.dumps(cfg, indent=2))
        elif args.focus:
            focus_action(args.focus)
            if "focus" not in cfg["widgets"]:
                cfg["widgets"].append("focus")
                save_config(cfg)
        elif args.update:
            update()
        elif args.check_updates:
            check_updates()
        elif args.show_themes or args.pick_theme:
            for i, theme in enumerate(THEMES, 1):
                print(f"{i:2}. {theme}\n" + render(demo(), cfg | {"theme": theme}, width, args.plain))
            if args.pick_theme:
                if not sys.stdin.isatty():
                    raise ValueError("Theme picker needs an interactive terminal")
                answer = input("Theme name/number (Enter cancels): ").strip()
                if answer:
                    theme = list(THEMES)[int(answer)-1] if answer.isdigit() and 1 <= int(answer) <= len(THEMES) else answer
                    if theme not in THEMES:
                        raise ValueError("Unknown theme")
                    cfg["theme"] = theme
                    save_config(cfg)
        elif args.preview or (changed and not (args.watch or args.json or args.doctor)):
            print("Demo data" + (" — configuration saved" if changed and not args.preview else ""))
            print(render(demo(), cfg, width, args.plain))
        else:
            with Client() as client:
                if args.stats or args.heatmap:
                    from .data import cached_call
                    value, age, error = cached_call(client, "account/usage/read", {}, "account-usage", 300)
                    if error:
                        print(error, file=sys.stderr)
                    if args.heatmap:
                        buckets = value.get("dailyUsageBuckets") or []
                        maximum = max((b["tokens"] for b in buckets), default=1) or 1
                        for bucket in buckets:
                            print(clean(bucket["startDate"]), "█" * round(bucket["tokens"] / maximum * 24), bucket["tokens"])
                        if not buckets:
                            print("Daily token activity unavailable")
                    else:
                        print(json.dumps(value.get("summary") or {}, indent=2))
                    return 1 if error else 0
                monitor = Monitor(client, args.cwd, args.thread)
                if args.watch:
                    watch(monitor, cfg, args)
                else:
                    snapshot = monitor.collect(cfg)
                    snapshot["samples"] = record_sample(snapshot)
                    if args.doctor:
                        print("Codex app server: connected")
                        print("Quota windows: " + str(len(snapshot.get("windows", []))))
                        print("Matching session: " + ("yes" if snapshot.get("thread", {}).get("id") else "none in this directory"))
                        print("Context telemetry: " + ("available" if snapshot.get("context") is not None else "unavailable (send a turn or pin --thread)"))
                        print("Native footer: built-in items; Pulse themes render in the companion pane")
                    print(json.dumps(snapshot, indent=2) if args.json else render(snapshot, cfg, width, args.plain or not sys.stdout.isatty()))
                    return 1 if snapshot.get("errors") and not snapshot.get("windows") else 0
        return 0
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, RpcError, subprocess.SubprocessError) as exc:
        print("CodexPulse: " + clean(exc), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
