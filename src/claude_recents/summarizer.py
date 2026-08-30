"""Generate a briefing for each session — the answer an employee would
give to "너 지금 뭐 하고 있어?".

Default backend: `claude -p --model haiku` — headless Claude Code, so the
user's logged-in Claude subscription is used (no API key required).
Set CLAUDE_STATUS_USE_API=1 (with ANTHROPIC_API_KEY) to call the Claude API
directly instead.

Quota guards: briefings regenerate only when the session's state (request /
latest response) changes, at most once per 60s per session, with at most 2
calls in flight. Callers only trigger fetches while the panel is open.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

CACHE_PATH = Path.home() / ".config" / "claude-recents" / "briefings.json"

_PROMPT = (
    "You are an assistant reporting work status. Below is the recent record "
    "of one Claude Code session.\n"
    "Write a 1-2 sentence briefing, as if answering \"what are you working on?\".\n"
    "- If working: what the user asked for and what is being done now\n"
    "- If idle: what was completed and how it turned out\n"
    "- Include what the task is about so a reader without context understands\n"
    "- Mention concrete targets (files/models/numbers) but stay concise\n"
    "- Output the briefing sentence only. No prefixes, quotes, or bullets.\n\n"
    "[Status] {status}\n\n"
    "[User request]\n{request}\n\n"
    "[Current activity]\n{doing}\n\n"
    "[Latest response]\n{last_text}\n"
)


_TIMEOUT = 60
_PER_SESSION_INTERVAL = 20    # floor between any two fetches per session
_CONTENT_REFRESH = 600        # refresh for mere content drift at most per 10min


def _via_api(prompt: str, api_key: str) -> str:
    body = json.dumps(
        {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        data = json.loads(resp.read())
    return "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    ).strip()


def _via_claude_cli(prompt: str) -> str:
    claude = shutil.which("claude")
    if not claude:
        return ""
    # Strip API-key auth so the call always uses the claude.ai login
    # (the user's subscription) instead of a possibly unfunded API key.
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
    }
    result = subprocess.run(
        [claude, "-p", "--model", "haiku"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
        cwd=os.path.expanduser("~"),
        env=env,
    )
    out = result.stdout.strip()
    if result.returncode != 0 or "Credit balance is too low" in out:
        return ""
    return out


class Summarizer:
    def __init__(self) -> None:
        self._cache: dict[str, str] = {}       # state key -> briefing
        self._fingerprint: dict[str, str] = {} # state key -> last_text at gen time
        self._latest: dict[str, str] = {}      # session_id -> latest briefing
        self._last_fetch: dict[str, float] = {}
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        # At most 2 concurrent claude/API calls, whatever the session count.
        self._slots = threading.Semaphore(2)
        # The cache survives app restarts — without this, every restart
        # regenerated every briefing from scratch.
        try:
            data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            self._cache = dict(data.get("cache", {}))
            self._fingerprint = dict(data.get("fingerprint", {}))
            self._latest = dict(data.get("latest", {}))
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    def _save_locked(self) -> None:
        """Persist cache to disk. Caller must hold self._lock."""
        try:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = CACHE_PATH.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    {
                        "cache": self._cache,
                        "fingerprint": self._fingerprint,
                        "latest": self._latest,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            tmp.replace(CACHE_PATH)
        except OSError:
            pass

    @staticmethod
    def _key(session_id: str, request: str, active: bool) -> str:
        # Keyed on request + active flag only. The latest response is NOT
        # part of the key: autonomous sessions (watchers, monitors) emit
        # new responses constantly, and keying on them regenerated
        # briefings nonstop. Content drift refreshes on a slow timer
        # instead (_CONTENT_REFRESH).
        return f"{session_id}\x00{request[:400]}\x00{int(active)}"

    def peek(self, session_id: str) -> str | None:
        """Latest known briefing for this session — never fetches."""
        with self._lock:
            return self._latest.get(session_id)

    def get(
        self,
        session_id: str,
        request: str,
        doing: str,
        last_text: str = "",
        active: bool = False,
    ) -> str | None:
        """Current briefing; kicks off a background refresh when the
        session state changed and the per-session throttle allows it.
        Returns the previous briefing (or None) in the meantime."""
        if not (request or doing or last_text):
            return None
        key = self._key(session_id, request, active)
        now = time.time()
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._latest[session_id] = cached
                # Same request/state: refresh only when the latest response
                # drifted AND the slow content timer allows it.
                drifted = self._fingerprint.get(key) != last_text[:100]
                due = now - self._last_fetch.get(session_id, 0) > _CONTENT_REFRESH
                if not (drifted and due):
                    return cached
            # cached is None → the request/state changed: the old briefing
            # is wrong now, so show "generating" (None), never the old one.
            if key in self._pending:
                return cached
            if now - self._last_fetch.get(session_id, 0) < _PER_SESSION_INTERVAL:
                return cached
            self._pending.add(key)
            self._last_fetch[session_id] = now
        threading.Thread(
            target=self._fetch,
            args=(key, session_id, request, doing, last_text, active),
            daemon=True,
        ).start()
        return cached

    def _fetch(
        self,
        key: str,
        session_id: str,
        request: str,
        doing: str,
        last_text: str,
        active: bool,
    ) -> None:
        prompt = _PROMPT.format(
            status="working" if active else "idle (last task finished)",
            request=request[:1500] or "(없음)",
            doing=doing[:400] or "(없음)",
            last_text=last_text[:1500] or "(없음)",
        )
        summary = ""
        try:
            with self._slots:
                api_key = os.environ.get("ANTHROPIC_API_KEY")
                use_api = api_key and os.environ.get("CLAUDE_STATUS_USE_API") == "1"
                summary = (
                    _via_api(prompt, api_key) if use_api else _via_claude_cli(prompt)
                )
        except Exception:
            pass
        summary = " ".join(summary.split()) if summary else ""
        with self._lock:
            self._pending.discard(key)
            if summary:
                self._cache[key] = summary
                self._fingerprint[key] = last_text[:100]
                self._latest[session_id] = summary
                # crude bound so a long-running app doesn't grow forever
                if len(self._cache) > 500:
                    for k in list(self._cache)[:250]:
                        del self._cache[k]
                        self._fingerprint.pop(k, None)
                self._save_locked()
