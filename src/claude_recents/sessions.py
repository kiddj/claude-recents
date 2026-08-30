"""Discover live Claude Code sessions from ~/.claude/sessions/<pid>.json.

These per-PID state files are an undocumented internal of Claude Code
(observed in v2.1.x): each interactive session maintains one with fields
like sessionId, cwd, name, status ("busy"/"idle"), and statusUpdatedAt.
Parse defensively — the format may change between Claude Code versions.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
SWAP_PROFILES_DIR = Path.home() / ".claude-swap-backup" / "sessions"
APP_CONFIG_PATH = Path.home() / ".config" / "claude-recents" / "config.json"


def config_dirs() -> list[Path]:
    """All Claude config dirs to scan: the default one, claude-swap
    per-account profiles, and any extras from the app config file
    (~/.config/claude-recents/config.json: {"extra_config_dirs": [...]})."""
    dirs = [CLAUDE_DIR]
    if SWAP_PROFILES_DIR.is_dir():
        dirs += sorted(p for p in SWAP_PROFILES_DIR.iterdir() if p.is_dir())
    try:
        extra = json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8")).get("extra_config_dirs", [])
        dirs += [Path(p).expanduser() for p in extra]
    except (OSError, json.JSONDecodeError):
        pass
    seen, out = set(), []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


@dataclass
class Session:
    pid: int
    session_id: str
    cwd: str
    status: str  # "busy" | "idle" | unknown values pass through
    name: str = ""
    kind: str = ""
    started_at: int = 0
    status_updated_at: int = 0
    bridge_session_id: str = ""
    tmux: str = ""
    config_dir: Path = CLAUDE_DIR
    account: str = ""
    host: str = ""  # empty = this machine; else SSH host name
    raw: dict = field(default_factory=dict)

    @property
    def project_label(self) -> str:
        return Path(self.cwd).name or self.cwd

    @property
    def transcript_path(self) -> Path:
        # Claude Code maps cwd to a project dir by replacing path separators
        # and dots with hyphens.
        slug = self.cwd.replace("/", "-").replace(".", "-").replace("_", "-")
        return self.config_dir / "projects" / slug / f"{self.session_id}.jsonl"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def live_sessions() -> list[Session]:
    """Return live interactive sessions across all config dirs, newest first."""
    from .account import account_for_config_dir

    sessions: list[Session] = []
    for cfg_dir in config_dirs():
        sessions.extend(_sessions_in(cfg_dir, account_for_config_dir(cfg_dir)))
    sessions.sort(key=lambda s: s.started_at, reverse=True)
    return sessions


def _sessions_in(cfg_dir: Path, account: str) -> list[Session]:
    sessions: list[Session] = []
    sessions_dir = cfg_dir / "sessions"
    if not sessions_dir.is_dir():
        return sessions
    for f in sessions_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pid = data.get("pid")
        session_id = data.get("sessionId")
        if not isinstance(pid, int) or not session_id:
            continue
        if not _pid_alive(pid):
            continue
        # Headless runs (claude -p, SDK), including our own summarizer
        # calls, also report kind "interactive" — but their entrypoint is
        # "sdk-cli", not "cli". Only real terminal sessions pass. Without
        # this, summarizer calls spawn sessions that get summarized in
        # turn: a runaway feedback loop.
        if data.get("entrypoint") not in (None, "cli"):
            continue
        if data.get("kind") not in (None, "interactive"):
            continue
        sessions.append(
            Session(
                pid=pid,
                session_id=session_id,
                cwd=data.get("cwd", ""),
                status=data.get("status", "unknown"),
                name=data.get("name", ""),
                kind=data.get("kind", ""),
                started_at=data.get("startedAt", 0),
                status_updated_at=data.get("statusUpdatedAt", 0),
                bridge_session_id=data.get("bridgeSessionId", ""),
                tmux=data.get("tmux", ""),
                config_dir=cfg_dir,
                account=account,
                raw=data,
            )
        )
    return sessions
