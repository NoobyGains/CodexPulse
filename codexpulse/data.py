"""Normalize Codex metadata. Never estimate quota windows or invent missing values."""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

from .rpc import Client, RpcError
from .storage import home, read_json, write_json

def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None

def get(value, camel, snake=None):
    return value.get(camel, value.get(snake or camel))

def normalize_limits(response):
    buckets = response.get("rateLimitsByLimitId") or {}
    single = response.get("rateLimits") or response.get("rate_limits") or {}
    if not buckets and single:
        buckets = {get(single, "limitId", "limit_id") or "codex": single}
    windows = []
    for ident, bucket in buckets.items():
        if not isinstance(bucket, dict):
            continue
        for slot in ("primary", "secondary"):
            window = bucket.get(slot)
            if not isinstance(window, dict):
                continue
            pct = number(get(window, "usedPercent", "used_percent"))
            minutes = number(get(window, "windowDurationMins", "window_minutes"))
            if pct is None:
                continue
            # A primary window can be weekly (observed on live Codex accounts).
            kind = "weekly" if minutes == 10080 else "session" if minutes == 300 else "other"
            label = "Weekly" if kind == "weekly" else "Session" if kind == "session" else duration_label(minutes)
            if ident != "codex":
                label = str(get(bucket, "limitName", "limit_name") or ident) + " " + label
            windows.append({"id": str(ident), "slot": slot, "kind": kind, "label": label,
                "used": min(100, max(0, pct)), "minutes": minutes,
                "reset": number(get(window, "resetsAt", "resets_at"))})
    standard = buckets.get("codex") or single
    return {"windows": windows, "plan": get(standard, "planType", "plan_type"),
        "credits": standard.get("credits"),
        "reset_credits": (response.get("rateLimitResetCredits") or {}).get("availableCount")}

def duration_label(minutes):
    if minutes is None:
        return "Limit"
    if minutes >= 1440 and minutes % 1440 == 0:
        return f"{minutes / 1440:g}d"
    return f"{minutes / 60:g}h" if minutes >= 60 else f"{minutes:g}m"

class RolloutReader:
    """Incremental, bounded local telemetry. Message text is discarded immediately."""
    def __init__(self):
        self.path = None
        self.offset = 0
        self.state = {}

    def read(self, path):
        if not path or not Path(path).is_file():
            return {}
        path = Path(path)
        try:
            size = path.stat().st_size
            if path != self.path or size < self.offset:
                self.path, self.offset, self.state = path, 0, {}
            with path.open("rb") as stream:
                if size - self.offset > 4 * 1024 * 1024:
                    self.offset = size - 4 * 1024 * 1024
                    self.state["partial"] = True
                    stream.seek(self.offset)
                    stream.readline()
                    self.offset = stream.tell()
                stream.seek(self.offset)
                for line in stream:
                    if not line.endswith(b"\n"):
                        break  # Retry an in-progress write on the next refresh.
                    self.offset += len(line)
                    try:
                        event = json.loads(line)
                        payload = event.get("payload") or {}
                        if not isinstance(payload, dict):
                            continue
                        self.consume(event.get("type"), payload, event.get("timestamp"))
                    except (ValueError, TypeError, AttributeError):
                        continue
            return dict(self.state)
        except OSError:
            return dict(self.state)

    def consume(self, kind, payload, timestamp=None):
        if kind == "turn_context":
            for key in ("model", "effort", "service_tier"):
                if payload.get(key) is not None:
                    self.state[key] = payload[key]
        elif kind == "event_msg" and payload.get("type") == "token_count":
            info = payload.get("info") or {}
            if info:
                self.state["tokens"] = info
                self.state["tokens_at"] = timestamp
            if payload.get("rate_limits"):
                self.state["rate_limits"] = payload["rate_limits"]
        elif kind == "event_msg" and payload.get("type") in ("task_started", "task_complete", "task_aborted"):
            self.state["activity"] = "working" if payload["type"] == "task_started" else "idle"
        elif kind == "response_item" and payload.get("type") in ("function_call", "custom_tool_call"):
            self.state["tools"] = self.state.get("tools", 0) + 1
            self.state["last_tool"] = payload.get("name")
        elif kind == "compacted":
            self.state["compactions"] = self.state.get("compactions", 0) + 1
            # Context before compaction no longer describes the current window.
            self.state.pop("tokens", None)

def token_metrics(info):
    last = info.get("last_token_usage") or info.get("last") or {}
    total = info.get("total_token_usage") or info.get("total") or {}
    window = number(get(info, "modelContextWindow", "model_context_window"))
    used = number(get(last, "totalTokens", "total_tokens"))
    inp = number(get(total, "inputTokens", "input_tokens"))
    cached = number(get(total, "cachedInputTokens", "cached_input_tokens"))
    return {"context": min(100, max(0, used / window * 100)) if used is not None and window and window > 0 else None,
        "context_tokens": used, "context_window": window,
        "total_tokens": number(get(total, "totalTokens", "total_tokens")),
        "input_tokens": inp, "cached_tokens": cached,
        "output_tokens": number(get(total, "outputTokens", "output_tokens")),
        "reasoning_tokens": number(get(total, "reasoningOutputTokens", "reasoning_output_tokens")),
        "cache": min(100, max(0, cached / inp * 100)) if inp and inp > 0 and cached is not None else None}

def git_metrics(cwd):
    result = {}
    def run(*args):
        return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=2,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        branch = run("branch", "--show-current")
        if branch.returncode:
            return result
        result["branch"] = branch.stdout.strip() or "detached"
        changed = run("status", "--porcelain")
        result["files"] = len(changed.stdout.splitlines()) if changed.returncode == 0 else None
        diff = run("diff", "HEAD", "--numstat")
        if diff.returncode == 0:
            rows = [line.split("\t") for line in diff.stdout.splitlines()]
            result["added"] = sum(int(r[0]) for r in rows if r[0].isdigit())
            result["removed"] = sum(int(r[1]) for r in rows if len(r) > 1 and r[1].isdigit())
        drift = run("rev-list", "--left-right", "--count", "HEAD...@{upstream}")
        if drift.returncode == 0:
            result["ahead"], result["behind"] = map(int, drift.stdout.split())
        gitdir = run("rev-parse", "--git-dir").stdout.strip()
        common = run("rev-parse", "--git-common-dir").stdout.strip()
        result["worktree"] = gitdir != common
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return result

def cached_call(client, method, params, key, ttl):
    path = home() / (key + ".json")
    saved = read_json(path, {})
    now = time.time()
    age = max(0, now - saved.get("at", 0))
    if age < ttl and "value" in saved:
        return saved["value"], age, None
    if now < saved.get("retry_at", 0):
        return saved.get("value", {}), age, saved.get("error")
    try:
        value = client.call(method, params)
        # Do not retain account identifiers or UI upsell payloads in the cache.
        if method == "account/rateLimits/read":
            value = {k: value[k] for k in ("rateLimits", "rateLimitsByLimitId", "rateLimitResetCredits") if k in value}
        write_json(path, {"at": now, "value": value})
        return value, 0, None
    except RpcError as exc:
        failures = saved.get("failures", 0) + 1
        saved.update(failures=failures, retry_at=now + min(900, 30 * 2 ** min(failures, 5)), error=str(exc))
        write_json(path, saved)
        return saved.get("value", {}), age, str(exc)

class Monitor:
    def __init__(self, client, cwd, thread_id=None):
        self.client, self.cwd, self.thread_id = client, str(Path(cwd).resolve()), thread_id
        self.reader = RolloutReader()

    def collect(self, config):
        from .native import configured_fields
        now = time.time()
        response, age, error = cached_call(self.client, "account/rateLimits/read", {}, "limits", max(30, config["cache_ttl"]))
        snapshot = normalize_limits(response) | {"at": now, "age": age, "errors": [error] if error else []}
        if config.get("native_mode") == "auto":
            snapshot["native_fields"] = configured_fields(self.client, self.cwd)
        try:
            if self.thread_id:
                thread = self.client.call("thread/read", {"threadId": self.thread_id, "includeTurns": False})["thread"]
            else:
                threads = self.client.call("thread/list", {"cwd": self.cwd, "limit": 1, "sortKey": "updated_at"}).get("data", [])
                thread = threads[0] if threads else {}
            snapshot["selection"] = "pinned" if self.thread_id else "latest in directory"
            snapshot["thread"] = {k: thread.get(k) for k in ("id", "model", "reasoningEffort", "status", "createdAt", "updatedAt", "cliVersion", "agentNickname")}
            telemetry = self.reader.read(thread.get("path"))
            snapshot.update(token_metrics(telemetry.get("tokens", {})))
            snapshot.update({k: v for k, v in telemetry.items() if k not in ("tokens", "rate_limits")})
            snapshot["model"] = thread.get("model") or telemetry.get("model")
            snapshot["effort"] = thread.get("reasoningEffort") or telemetry.get("effort")
            if not snapshot["windows"] and telemetry.get("rate_limits"):
                snapshot.update(normalize_limits({"rate_limits": telemetry["rate_limits"]}))
                snapshot["quota_source"] = "last recorded turn"
            snapshot["git"] = git_metrics(thread.get("cwd") or self.cwd)
            if set(config["widgets"] + config["line2_widgets"]) & {"streak", "lifetime", "heatmap"}:
                usage, _, usage_error = cached_call(self.client, "account/usage/read", {}, "account-usage", 300)
                snapshot["account_usage"] = usage
                if usage_error:
                    snapshot["errors"].append(usage_error)
            if set(config["widgets"] + config["line2_widgets"]) & {"cost", "budget"} and thread.get("id"):
                key = hashlib.sha256(thread["id"].encode()).hexdigest()[:16]
                usage, _, _ = cached_call(self.client, "account/usage/read", {"threadId": thread["id"]}, "thread-usage-" + key, 300)
                micros = number((usage.get("threadUsage") or {}).get("estimatedUsageUsdMicros"))
                if micros is not None:
                    snapshot["cost_usd"] = micros / 1_000_000
                    snapshot["cost_source"] = "Codex estimate"
            if "agents" in config["widgets"] + config["line2_widgets"]:
                # Server validates parent relationship locally; never infer agents from cwd alone.
                children = self.client.call("thread/list", {"limit": 100, "sortKey": "updated_at", "sourceKinds": ["subAgent"]}).get("data", [])
                snapshot["agents"] = [{"name": t.get("agentNickname") or t.get("agentRole") or "agent",
                    "status": (t.get("status") or {}).get("type", "unknown"), "model": t.get("model")}
                    for t in children if t.get("parentThreadId") == thread.get("id") and thread.get("id")]
        except (RpcError, KeyError) as exc:
            snapshot["errors"].append(str(exc))
        return snapshot

def record_sample(snapshot):
    windows = snapshot.get("windows", [])
    window = next((w for w in windows if w["id"] == "codex" and w["kind"] == "session"),
        next((w for w in windows if w["id"] == "codex"), None))
    if not window or snapshot.get("age", 0) > 120:
        return []
    path = home() / "history.json"
    rows = read_json(path, [])
    now = snapshot["at"]
    rows = [r for r in rows if now - r[0] < 86400 and r[2] == window["reset"]]
    if not rows or now - rows[-1][0] >= 60:
        rows.append([now, window["used"], window["reset"]])
        write_json(path, rows[-1440:])
    return rows
