"""Bounded JSON-RPC over Codex's supported stdio transport."""
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time

class RpcError(RuntimeError):
    pass

def codex_command():
    override = os.environ.get("CODEXPULSE_CODEX")
    found = override or shutil.which("codex")
    if not found:
        raise RpcError("Codex CLI was not found. Install Codex and run codex login first.")
    path = Path(found)
    # Avoid shell=True and npm .cmd/.ps1 quoting on Windows, including paths with spaces.
    if path.suffix.lower() in (".cmd", ".ps1"):
        entry = path.parent / "node_modules/@openai/codex/bin/codex.js"
        node = shutil.which("node")
        if entry.is_file() and node:
            return [node, str(entry)]
        raise RpcError("Set CODEXPULSE_CODEX to the native codex.exe executable.")
    return [str(path)]

class Client:
    def __init__(self, command=None, timeout=12):
        self.command = command
        self.timeout = timeout
        self.process = None
        self.inbox = queue.Queue()
        self.sequence = 0
        self.notifications = []

    def __enter__(self):
        command = self.command or codex_command() + ["app-server"]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        threading.Thread(target=self._reader, daemon=True).start()
        try:
            self.call("initialize", {"clientInfo": {"name": "codexpulse", "version": "0.1.0"}})
            self.send({"method": "initialized", "params": {}})
        except Exception:
            self.close()
            raise
        return self

    def _reader(self):
        try:
            for line in self.process.stdout:
                try:
                    message = json.loads(line)
                    if isinstance(message, dict):
                        self.inbox.put(message)
                except ValueError:
                    continue
        finally:
            self.inbox.put(None)

    def send(self, message):
        try:
            self.process.stdin.write(json.dumps(message) + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise RpcError("Codex app server closed its connection") from exc

    def call(self, method, params=None):
        self.sequence += 1
        ident = self.sequence
        self.send({"id": ident, "method": method, "params": params or {}})
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                message = self.inbox.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty as exc:
                raise RpcError(f"Codex timed out while reading {method}") from exc
            if message is None:
                raise RpcError("Codex app server exited before replying")
            if message.get("id") == ident and "method" not in message:
                if "error" in message:
                    # Server errors can carry private URLs/details. Report method/code only.
                    code = (message.get("error") or {}).get("code", "unknown")
                    raise RpcError(f"Codex {method} is unavailable (code {code})")
                return message.get("result") or {}
            if "method" in message and "id" in message:
                self.send({"id": message["id"], "error": {"code": -32601,
                    "message": "CodexPulse is a read-only observer"}})
            elif "method" in message:
                self.notifications.append(message)
                self.notifications = self.notifications[-100:]

    def close(self):
        if self.process is None:
            return
        try:
            self.process.stdin.close()
            self.process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self.process.stdout.close()

    def __exit__(self, *args):
        self.close()
