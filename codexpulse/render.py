"""Pulse palettes, terminal-width-aware widgets, and independent animation frames."""
import colorsys
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import time
import unicodedata

from .data import number
from .storage import home, read_json

THEMES = json.loads(Path(__file__).with_name("themes.json").read_text(encoding="utf-8"))
STYLES = {"classic": ("━", "─"), "block": ("█", "░"), "shade": ("▓", "░"),
    "pipe": ("┃", "┊"), "dot": ("●", "○"), "square": ("■", "□"),
    "star": ("★", "☆"), "braille": ("⣿", "⣀"), "ascii": ("#", "-")}
ANIMATIONS = ("off", "rainbow", "pulse", "glow", "shift")
WIDGETS = ("session", "weekly", "limits", "context", "model", "effort", "branch",
    "tokens", "input", "output", "reasoning", "cache", "context_tokens", "plan", "credits",
    "reset_credits", "fast", "activity", "heartbeat", "last_tool", "elapsed", "focus",
    "cost", "budget", "files", "lines", "git_drift", "worktree", "agents", "streak",
    "lifetime", "sparkline", "burn_rate", "runway", "pace", "version", "compactions",
    "tasks", "active_tools", "git_status", "stash", "project")
ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))")
RESET = "\x1b[0m"

def clean(text):
    text = ESCAPE.sub("", str(text))
    return "".join(c for c in text if unicodedata.category(c) not in ("Cc", "Cf", "Cs"))

def cell_width(text):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
        for c in ESCAPE.sub("", text))

def clip(text, width):
    out, used, pos = [], 0, 0
    while pos < len(text):
        match = ESCAPE.match(text, pos)
        if match:
            out.append(match.group())
            pos = match.end()
            continue
        char = text[pos]
        size = cell_width(char)
        if used + size > width:
            break
        out.append(char)
        used += size
        pos += 1
    return "".join(out) + (RESET if "\x1b" in text else "")

def wrap_text(text, width):
    """Wrap on words, splitting overlong tokens by terminal cells, including ANSI."""
    width = max(1, width)
    rows, current = [], ""
    for word in text.split(" "):
        candidate = current + (" " if current else "") + word
        if cell_width(candidate) <= width:
            current = candidate
            continue
        if current:
            rows.append(current)
            current = ""
        # Long identifiers and CJK text have no convenient space to wrap on.
        pos, used = 0, 0
        while pos < len(word):
            match = ESCAPE.match(word, pos)
            if match:
                current += match.group()
                pos = match.end()
                continue
            char = word[pos]
            size = cell_width(char)
            if used + size > width and used:
                rows.append(current)
                current, used = "", 0
            if size > width:
                char, size = "?", 1
            current += char
            used += size
            pos += 1
    if current:
        rows.append(current)
    return rows


def is_spark_window(window):
    """Match the reported model identity, without hiding unrelated trend widgets."""
    identity = str(window.get("id", "")) + " " + str(window.get("label", ""))
    return bool(re.search(r"(?:^|[^a-z0-9])spark(?:$|[^a-z0-9])", identity, re.I))


def paint(text, hex_color, depth="truecolor", fallback=None):
    if depth == "none":
        return text
    rgb = tuple(int(hex_color[i:i+2], 16) for i in (1, 3, 5))
    if depth == "16":
        prefix = f"\x1b[{fallback or 97}m"
    elif depth == "256":
        code = fallback if fallback is not None else 16 + sum(round(c / 255 * 5) * m for c, m in zip(rgb, (36, 6, 1)))
        prefix = f"\x1b[38;5;{code}m"
    else:
        prefix = "\x1b[38;2;" + ";".join(map(str, rgb)) + "m"
    return prefix + text + RESET

def color_depth(cfg, plain):
    if plain or "NO_COLOR" in os.environ:
        return "none"
    if cfg["color_depth"] != "auto":
        return cfg["color_depth"]
    if os.name == "nt" or os.environ.get("COLORTERM") in ("truecolor", "24bit"):
        return "truecolor"
    return "256" if "256color" in os.environ.get("TERM", "") else "16"

def bar(pct, cfg, plain=False, frame=0):
    theme = THEMES[cfg["theme"]]
    tier = 0 if pct < 50 else 1 if pct < 80 else 2
    color = theme[("low", "mid", "high")[tier]]
    depth = color_depth(cfg, plain)
    size = cfg["bar_size"]
    filled = round(pct / 100 * size)
    full, empty = STYLES["ascii" if cfg.get("ascii") else cfg["bar_style"]]
    fallback = theme["c" + depth][tier] if depth in ("16", "256") else None
    animation = cfg["animate"]
    if cfg["theme"] == "rainbow" and animation == "off":
        animation = "rainbow"
    phase = frame * {"slow": .03, "normal": .07, "fast": .13}[cfg["animation_speed"]]
    chunks = []
    for i in range(size):
        active = i < filled
        char = full if active else empty
        if cfg["bar_style"] == "braille" and not cfg.get("ascii"):
            steps = "⣀⣄⣤⣦⣶⣷⣿"
            level = max(0, min(6, round((pct / 100 * size - i) * 6)))
            char, active = steps[level], level > 0
        tone = color if active else theme["track"]
        if active and animation != "off" and depth != "none":
            rgb = tuple(int(color[k:k+2], 16) / 255 for k in (1, 3, 5))
            if animation in ("rainbow", "pulse"):
                rgb = colorsys.hsv_to_rgb((phase + (i / max(1, size) if animation == "rainbow" else 0)) % 1, .6, 1)
            elif animation == "glow":
                factor = .7 + .3 * math.sin(phase * 6 + i / 2)
                rgb = tuple(c * factor for c in rgb)
            elif animation == "shift" and i == int(phase * 10) % max(1, size):
                rgb = (1, 1, 1)
            tone = "#" + "".join(f"{round(c * 255):02x}" for c in rgb)
        chunks.append(paint(char, tone, depth, fallback if active else (theme["c" + depth][3] if depth in ("16", "256") else None)))
    return "".join(chunks)

def short(value):
    if value is None:
        return "?"
    return f"{value / 1e6:.1f}M" if value >= 1e6 else f"{value / 1000:.1f}k" if value >= 1000 else f"{value:g}"

def countdown(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "<1m"
    minutes = seconds // 60
    return f"{minutes // 60}h {minutes % 60}m" if minutes >= 60 else f"{minutes}m"

def reset_time(window, cfg, now):
    reset = window.get("reset")
    if reset is None:
        return ""
    if reset <= now:
        return " refresh pending"
    if window["kind"] == "session" or reset - now < 86400:
        return " " + countdown(reset - now)
    date = datetime.fromtimestamp(reset)
    hour = date.strftime("%H:%M") if cfg["clock"] == "24h" else f"{date.hour % 12 or 12}" + (f":{date.minute:02}" if date.minute else "") + ("am" if date.hour < 12 else "pm")
    return " R:" + date.strftime("%a ") + hour

def usage_widget(label, pct, cfg, plain, frame, native=False):
    label = clean(label)
    if native:
        # Codex already supplies the number (often remaining); these bars show used.
        return f"{label} used {bar(pct, cfg, plain, frame)}"
    if cfg["layout"] == "minimal":
        theme = THEMES[cfg["theme"]]
        tier = 0 if pct < 50 else 1 if pct < 80 else 2
        depth = color_depth(cfg, plain)
        fallback = theme["c" + depth][tier] if depth in ("16", "256") else None
        return paint(f"{label} {pct:.0f}%", theme[("low", "mid", "high")[tier]], depth, fallback)
    if cfg["layout"] == "compact":
        return f"{label}:{bar(pct, cfg, plain, frame)} {pct:.0f}%"
    if cfg["layout"] == "percent-first":
        return f"{label} {pct:.0f}% {bar(pct, cfg, plain, frame)}"
    return f"{label} {bar(pct, cfg, plain, frame)} {pct:.0f}%"

def widgets(snapshot, cfg, plain=False, frame=0):
    values = {}
    native = set(snapshot.get("native_fields", [])) if cfg.get("native_mode") == "auto" else set()
    now = snapshot.get("at", time.time())
    windows = [w for w in snapshot.get("windows", [])
        if cfg.get("spark", False) or not is_spark_window(w)]
    for kind in ("session", "weekly", "limits"):
        selected = [w for w in windows if (w["id"] != "codex" or w["kind"] == "other") == (kind == "limits")
            and (kind == "limits" or w["kind"] == kind)]
        if selected:
            fields = {"session": "five-hour-limit", "weekly": "weekly-limit"}
            values[kind] = [usage_widget(w["label"], w["used"], cfg, plain, frame,
                fields.get(kind) in native) + ("" if cfg.get("_short_resets") else reset_time(w, cfg, now))
                for w in selected]
    context = snapshot.get("context")
    values["context"] = usage_widget("Context", context, cfg, plain, frame,
        bool(native & {"context-used", "context-remaining"})) + (" !" if context >= 90 else "") if context is not None else "Context ?"
    for key, label in (("model", ""), ("effort", "Effort "), ("plan", "Plan "), ("last_tool", "Tool "), ("activity", "")):
        if snapshot.get(key) is not None:
            values[key] = label + clean(snapshot[key])
    for widget, key, label in (("tokens", "total_tokens", "Tokens"), ("input", "input_tokens", "In"),
        ("output", "output_tokens", "Out"), ("reasoning", "reasoning_tokens", "Reasoning"),
        ("context_tokens", "context_tokens", "Context tokens")):
        if snapshot.get(key) is not None:
            values[widget] = label + " " + short(snapshot[key])
    if snapshot.get("cache") is not None:
        values["cache"] = f"Cache {snapshot['cache']:.0f}%"
    thread = snapshot.get("thread", {})
    if thread.get("createdAt"):
        values["elapsed"] = "Elapsed " + countdown(now - thread["createdAt"])
    if thread.get("cliVersion"):
        values["version"] = "Codex " + clean(thread["cliVersion"])
    if snapshot.get("service_tier") in ("fast", "priority"):
        values["fast"] = "Fast"
    if snapshot.get("tools") is not None:
        spinner = "|/-\\"[frame % 4]
        values["heartbeat"] = f"{spinner} {snapshot['tools']} " + ("recent tools" if snapshot.get("partial") else "tools")
    if snapshot.get("compactions"):
        values["compactions"] = f"Compacted {snapshot['compactions']}" + ("+" if snapshot.get("partial") else "")
    git = snapshot.get("git", {})
    if git.get("branch"):
        values["branch"] = clean(git["branch"])
    if git.get("files") is not None:
        values["files"] = f"Files {git['files']}"
    if git.get("added") is not None:
        values["lines"] = f"Diff +{git['added']} -{git['removed']}"
    if git.get("ahead") is not None:
        values["git_drift"] = f"Git ↑{git['ahead']} ↓{git['behind']}"
    if git.get("worktree"):
        values["worktree"] = "Worktree"
    if git.get("staged") is not None:
        values["git_status"] = f"Git staged {git['staged']} modified {git['modified']} untracked {git['untracked']}"
    if git.get("stash") is not None:
        values["stash"] = f"Stash {git['stash']}"
    if git.get("project"):
        values["project"] = clean(git["project"])
    tasks = snapshot.get("tasks")
    if isinstance(tasks, dict):
        values["tasks"] = f"Tasks {tasks['completed']}/{tasks['total']}"
    if isinstance(snapshot.get("active_tools"), list):
        names = list(dict.fromkeys(clean(n) for n in snapshot["active_tools"]))
        values["active_tools"] = "Tools " + (", ".join(names[:3]) if names else "idle")
        if len(names) > 3:
            values["active_tools"] += f" +{len(names) - 3}"
        if snapshot.get("partial"):
            values["active_tools"] += " (observed)"
    if "agents" in snapshot:
        agents = snapshot["agents"]
        active = sum(a["status"] == "active" for a in agents)
        values["agents"] = f"Agents {active} active / {len(agents)} listed"
    summary = (snapshot.get("account_usage") or {}).get("summary") or {}
    if summary.get("currentStreakDays") is not None:
        values["streak"] = f"Streak {summary['currentStreakDays']}d"
    if summary.get("lifetimeTokens") is not None:
        values["lifetime"] = "Lifetime " + short(summary["lifetimeTokens"])
    credits = snapshot.get("credits") or {}
    if credits.get("unlimited"):
        values["credits"] = "Credits unlimited"
    elif credits.get("balance") is not None:
        values["credits"] = "Credits " + clean(credits["balance"])
    if snapshot.get("reset_credits") is not None:
        values["reset_credits"] = f"Resets {snapshot['reset_credits']}"
    cost = number(snapshot.get("cost_usd"))
    if cost is not None:
        values["cost"] = f"Est {cfg['currency']} {cost * cfg['fx_rate']:.2f}"
        if cfg["budget"] > 0:
            values["budget"] = usage_widget("Budget", min(100, cost / cfg["budget"] * 100), cfg, plain, frame)
    focus = read_json(home() / "focus.json", {})
    if focus.get("end"):
        values["focus"] = "Focus " + (countdown(focus["end"] - now) if focus["end"] > now else "done!")
    rows = snapshot.get("samples", [])
    if rows:
        chars = "._-:=+*#" if cfg.get("ascii") else "▁▂▃▄▅▆▇█"
        values["sparkline"] = "".join(chars[min(7, max(0, round(r[1] / 100 * 7)))] for r in rows[-12:])
    if len(rows) >= 2 and rows[-1][0] > rows[0][0] and rows[-1][1] >= rows[0][1]:
        rate = (rows[-1][1] - rows[0][1]) / ((rows[-1][0] - rows[0][0]) / 60)
        values["burn_rate"] = f"~{rate:.2f}%/m"
        if rate > 0:
            values["runway"] = "Runway ~" + countdown((100 - rows[-1][1]) / rate * 60)
    main = next((w for w in windows if w["id"] == "codex" and w["reset"] and w["minutes"]), None)
    if main and main["reset"] > now:
        elapsed_pct = max(0, min(100, 100 * (1 - (main["reset"] - now) / (main["minutes"] * 60))))
        values["pace"] = f"Pace {main['used'] - elapsed_pct:+.0f}%"
    duplicates = {
        "model": {"model", "model-name", "model-with-reasoning"},
        "effort": {"reasoning", "model-with-reasoning"},
        "branch": {"git-branch"}, "fast": {"fast-mode"},
        "tokens": {"used-tokens"}, "input": {"total-input-tokens"},
        "output": {"total-output-tokens"}, "version": {"codex-version"},
    }
    for widget, fields in duplicates.items():
        if native & fields:
            values.pop(widget, None)
    return values

def watch_rows(snapshot, cfg, width, height, thread=None, plain=False, frame=0):
    """Keep actual usage visible even when a companion pane is only two rows tall."""
    capacity = max(1, height - 1)
    width = max(1, width)
    rows = render(snapshot, cfg, width, plain, frame).splitlines()
    if cfg["wrap"] == "auto" and len(rows) > capacity:
        # Recompute on every frame; resizing never changes saved preferences.
        compact = cfg | {"bar_size": min(4, cfg["bar_size"])}
        combined = list(dict.fromkeys(cfg["widgets"] + cfg["line2_widgets"]))
        for candidate in (
            compact,
            compact | {"layout": "minimal"},
            compact | {"layout": "minimal", "widgets": combined, "line2_widgets": []},
            compact | {"layout": "minimal", "widgets": combined, "line2_widgets": [], "_short_resets": True},
        ):
            fitted = render(snapshot, candidate, width, plain, frame).splitlines()
            if len(fitted) < len(rows):
                rows = fitted
            if len(rows) <= capacity:
                break
    if len(rows) > capacity:
        hidden = len(rows) - capacity
        rows = rows[:capacity]
        marker = f" … +{hidden} rows"
        rows[-1] = (clip(rows[-1], width - cell_width(marker)) + marker
                    if cell_width(marker) < width else clip("…", width))
    if cfg.get("header", True) and capacity >= len(rows) + 2:
        header = "CodexPulse · " + ("thread " + clean(thread[:8]) if thread else "latest session in directory") + " · Ctrl+C to exit"
        rows = [clip(header, width), "", *rows]
    return [ascii_text(row) for row in rows[:capacity]] if cfg.get("ascii") else rows[:capacity]


def ascii_text(text):
    return text.translate(str.maketrans({"↑": "^", "↓": "v", "…": "~", "·": "|"})).encode("ascii", "replace").decode("ascii")


def render(snapshot, cfg, width=120, plain=False, frame=0):
    width = max(1, width)
    values = widgets(snapshot, cfg, plain, frame)
    lines = []
    def row(names):
        ordered = sorted(enumerate(names), key=lambda pair: cfg["priority"].get(pair[1], pair[0] * 10))
        parts = []
        for _, name in ordered:
            item = values.get(name)
            parts.extend(item if isinstance(item, list) else [item] if item else [])
        current = ""
        for part in parts:
            candidate = current + (" | " if current else "") + part
            if cfg["wrap"] == "auto" and cell_width(candidate) > width:
                if current:
                    lines.append(current)
                wrapped = wrap_text(part, width)
                lines.extend(wrapped[:-1])
                current = wrapped[-1] if wrapped else ""
            else:
                current = clip(candidate, width) if cell_width(candidate) > width else candidate
        if current:
            lines.append(current)
    row([w for w in cfg["widgets"] if w not in cfg["line2_widgets"]])
    row(cfg["line2_widgets"])
    notices = []
    if not snapshot.get("windows"):
        notices.append("Quota unavailable (requires a supported Codex login)")
    elif not cfg.get("spark", False) and all(is_spark_window(w) for w in snapshot["windows"]):
        notices.append("No non-Spark quota reported; --spark shows Spark")
    if not snapshot.get("thread", {}).get("id"):
        notices.append("No Codex session in this directory")
    if snapshot.get("age", 0) > max(120, cfg["cache_ttl"] * 2):
        notices.append("Quota stale " + countdown(snapshot["age"]))
    if snapshot.get("quota_source"):
        notices.append("Quota: " + snapshot["quota_source"])
    if snapshot.get("errors"):
        notices.append(clean(snapshot["errors"][0]))
    if notices:
        notice = " · ".join(notices)
        lines.extend(wrap_text(notice, width) if cfg["wrap"] == "auto" else [clip(notice, width)])
    result = "\n".join(lines)
    return ascii_text(result) if cfg.get("ascii") else result

def demo():
    now = time.time()
    return {"at": now, "windows": [
        {"id": "codex", "slot": "primary", "kind": "session", "label": "Session", "used": 39, "reset": now + 12660, "minutes": 300},
        {"id": "codex", "slot": "secondary", "kind": "weekly", "label": "Weekly", "used": 78, "reset": now + 3*86400, "minutes": 10080},
        {"id": "example-model", "slot": "secondary", "kind": "weekly", "label": "Model quota", "used": 89, "reset": None, "minutes": 10080}],
        "context": 14, "model": "codex-model", "effort": "high", "plan": "pro",
        "total_tokens": 182400, "input_tokens": 170000, "output_tokens": 12400, "reasoning_tokens": 3200,
        "cache": 82, "git": {"branch": "main", "files": 4, "added": 42, "removed": 7, "staged": 1, "modified": 2, "untracked": 1, "stash": 2, "project": "codexpulse"},
        "thread": {"id": "demo", "createdAt": now-2700, "cliVersion": "0.154.0"}, "age": 0,
        "cost_usd": 1.24, "tools": 47, "activity": "working", "last_tool": "exec_command",
        "tasks": {"total": 5, "completed": 2, "in_progress": 1}, "active_tools": ["exec_command"]}
