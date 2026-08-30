"""Monitor Claude Code sessions on remote machines over SSH.

Nothing is installed server-side: each poll pipes REMOTE_SCRIPT into
`ssh <host> python3 -`, which scans the server's Claude config dirs
(default ~/.claude plus claude-swap profiles) and prints one JSON bundle
with live sessions, transcript tails, and account identity. Parsing
reuses the same code paths as local sessions.

Hosts come from ~/.config/claude-recents/config.json: {"ssh_hosts": [...]}.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .sessions import APP_CONFIG_PATH, Session
from .transcript import Activity, _tool_label

SSH_TIMEOUT = 20

# Runs server-side via `ssh <host> python3 -`. Transcript parsing happens
# THERE (over a 1MB tail read from local disk) and only the extracted
# fields travel over the wire — a 64KB shipped tail once missed the real
# latest request in a 17MB transcript of a busy autonomous session.
# Filters must mirror transcript.parse_activity.
REMOTE_SCRIPT = r"""
import glob, json, os

home = os.path.expanduser("~")
default_dir = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home, ".claude")
cfg_dirs = [default_dir]
swap = os.path.join(home, ".claude-swap-backup", "sessions")
if os.path.isdir(swap):
    cfg_dirs += sorted(
        p for p in (os.path.join(swap, x) for x in sorted(os.listdir(swap)))
        if os.path.isdir(p)
    )

_SKIP_PREFIXES = (
    "<", "Another Claude session", "[Request interrupted",
    "This session is being continued",
)


def tail(path, n):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(max(0, size - n))
            chunk = f.read()
        lines = chunk.split(b"\n")
        if size > n and lines:
            lines = lines[1:]
        return [l.decode("utf-8", "replace") for l in lines if l.strip()]
    except OSError:
        return []


def parse_transcript(lines):
    act = {"request": "", "request_ts": "", "last_text": "",
           "last_text_ts": "", "tool": None, "last_event_ts": "",
           "mid_turns": 0}
    # Turn = response segment bounded by user events; tool_result user
    # events are intra-turn. Mirrors transcript.parse_activity.
    segments = 0
    seg_has_text = False
    for ln in lines:
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        if e.get("isSidechain"):
            continue
        t = e.get("type")
        if t == "user":
            c = e.get("message", {}).get("content")
            if isinstance(c, list):
                if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                    continue
                c = "\n".join(
                    b.get("text", "") for b in c
                    if isinstance(b, dict) and b.get("type") == "text"
                ).strip()
            if seg_has_text:
                segments += 1
                seg_has_text = False
            if e.get("isMeta"):
                continue
            if isinstance(c, str) and c and not c.startswith(_SKIP_PREFIXES):
                act["request"] = c[:1200]
                act["request_ts"] = e.get("timestamp", act["request_ts"])
                act["last_event_ts"] = e.get("timestamp", act["last_event_ts"])
                segments = 0
        elif t == "attachment":
            att = e.get("attachment") or {}
            if (att.get("type") == "queued_command"
                    and (att.get("origin") or {}).get("kind") == "human"):
                prompt = str(att.get("prompt") or "").strip()
                if prompt and not prompt.startswith(("/", "<")):
                    act["request"] = prompt[:1200]
                    act["request_ts"] = e.get("timestamp", act["request_ts"])
                    act["last_event_ts"] = e.get("timestamp", act["last_event_ts"])
                    segments = 0
        elif t == "assistant":
            c = e.get("message", {}).get("content")
            if not isinstance(c, list):
                continue
            for b in c:
                bt = b.get("type")
                if bt == "text" and b.get("text", "").strip():
                    act["last_text"] = b["text"].strip()[:1200]
                    act["last_text_ts"] = e.get("timestamp", act["last_text_ts"])
                    act["tool"] = None
                    seg_has_text = True
                elif bt == "tool_use":
                    ti = b.get("input") or {}
                    tgt = (ti.get("description") or ti.get("file_path")
                           or ti.get("path") or ti.get("pattern")
                           or ti.get("prompt") or ti.get("command")
                           or ti.get("url") or "")
                    act["tool"] = [b.get("name", "tool"), str(tgt)[:120]]
            act["last_event_ts"] = e.get("timestamp", act["last_event_ts"])
    if seg_has_text:
        segments += 1
    act["mid_turns"] = max(0, segments - 1)
    act["turns_capped"] = not bool(act["request"])
    return act


def latest_from_history(lines, sid):
    best_ts, best = 0, ""
    for ln in lines:
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        if e.get("sessionId") != sid:
            continue
        d = e.get("display", "")
        if not d or d.startswith("/"):
            continue
        if e.get("timestamp", 0) >= best_ts:
            best_ts, best = e.get("timestamp", 0), d
    return best[:1200], best_ts


out = {"dirs": []}
for d in cfg_dirs:
    if d == os.path.join(home, ".claude"):
        ident = os.path.join(home, ".claude.json")
    else:
        ident = os.path.join(d, ".claude.json")
    try:
        acct = json.load(open(ident)).get("oauthAccount") or {}
    except Exception:
        acct = {}
    entry = {
        "config_dir": d,
        "account": {
            k: acct.get(k, "")
            for k in ("displayName", "emailAddress", "organizationType")
        },
        "sessions": [],
    }
    history = None
    for f in glob.glob(os.path.join(d, "sessions", "*.json")):
        try:
            s = json.load(open(f))
        except Exception:
            continue
        pid = s.get("pid")
        sid = s.get("sessionId")
        if not isinstance(pid, int) or not sid:
            continue
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        except PermissionError:
            pass
        if s.get("entrypoint") not in (None, "cli"):
            continue
        if s.get("kind") not in (None, "interactive"):
            continue
        cwd = s.get("cwd", "")
        slug = cwd.replace("/", "-").replace(".", "-").replace("_", "-")
        tp = os.path.join(d, "projects", slug, sid + ".jsonl")
        act = parse_transcript(tail(tp, 1048576))
        if not act["request"]:
            # Busy autonomous sessions can push the last typed request
            # beyond 1MB of tail; widen once before falling back to
            # history (which misses Remote-Control-submitted prompts).
            try:
                big = os.path.getsize(tp) > 1048576
            except OSError:
                big = False
            if big:
                act2 = parse_transcript(tail(tp, 8388608))
                if act2["request"]:
                    act = act2
        if not act["request"]:
            if history is None:
                history = tail(os.path.join(d, "history.jsonl"), 262144)
            req, ts = latest_from_history(history, sid)
            act["request"] = req
            if ts:
                act["request_ts"] = ts  # epoch ms, handled client-side
        entry["sessions"].append({"session": s, "activity": act})
    out["dirs"].append(entry)
print(json.dumps(out))
"""


def ssh_hosts() -> list[str]:
    try:
        hosts = json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8")).get("ssh_hosts", [])
        return [h for h in hosts if isinstance(h, str) and h]
    except (OSError, json.JSONDecodeError):
        return []


class RemoteHost:
    """Single-flight poller for one SSH host.

    One worker loop per host: attempt → publish result → sleep until the
    next interval or an explicit wake. request_now() aborts any in-flight
    attempt (its outcome is discarded entirely — success or failure) and
    runs a fresh one immediately. No timing heuristics, no flag juggling:
    single-flight is guaranteed by the loop structure itself.
    """

    def __init__(self, host: str, interval_fn=None) -> None:
        self.host = host
        self.error = ""
        self._bundle: dict | None = None
        self._bundle_at = 0.0
        self._interval_fn = interval_fn or (lambda: 60)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopped = threading.Event()
        self._proc = None
        self._aborted = False
        threading.Thread(target=self._loop, daemon=True).start()

    def request_now(self) -> None:
        """Refresh immediately. Never a no-op: kills any in-flight attempt
        (result discarded) and wakes the loop for a fresh one."""
        with self._lock:
            self._aborted = True
            proc = self._proc
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass
        self._wake.set()

    def stop(self) -> None:
        """Shut the loop down (host removed from the UI)."""
        self._stopped.set()
        with self._lock:
            proc = self._proc
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass
        self._wake.set()

    def status(self) -> tuple:
        """("ok" | "error" | "connecting", error message, bundle age s)."""
        with self._lock:
            age = time.time() - self._bundle_at if self._bundle_at else -1.0
            if self.error:
                return ("error", self.error, age)
            if self._bundle is not None:
                return ("ok", "", age)
            return ("connecting", "", age)

    def _loop(self) -> None:
        while not self._stopped.is_set():
            self._attempt()
            self._wake.wait(timeout=self._interval_fn())
            self._wake.clear()

    def _attempt(self) -> None:
        with self._lock:
            self._aborted = False
        bundle, error = None, ""
        proc = None
        try:
            proc = subprocess.Popen(
                [
                    "ssh",
                    "-o", "BatchMode=yes",
                    "-o", "ConnectTimeout=8",
                    "--",  # host names must never be parsed as ssh options
                    self.host,
                    "python3", "-",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            with self._lock:
                self._proc = proc
            out, err = proc.communicate(input=REMOTE_SCRIPT, timeout=SSH_TIMEOUT)
            if proc.returncode == 0:
                bundle = json.loads(out)
            else:
                error = (err.strip().splitlines() or ["ssh failed"])[-1][:120]
                # BatchMode makes password prompts fail instantly — surface
                # what the user must actually do about it.
                if "Permission denied" in error or "Interactive authentication" in error:
                    error = (
                        "auth failed — key-based SSH required "
                        f"(run: ssh-copy-id {self.host})"
                    )
        except subprocess.TimeoutExpired:
            if proc is not None:
                try:
                    proc.kill()
                except OSError:
                    pass
            error = "connection timed out"
        except (OSError, ValueError) as e:
            error = str(e)[:120]
        with self._lock:
            self._proc = None
            if self._aborted:
                return  # outcome of an aborted attempt: discard entirely
            self.error = error
            if bundle is not None:
                self._bundle = bundle
                self._bundle_at = time.time()

    def snapshot(self) -> list[tuple[Session, Activity]]:
        """Sessions and activities from the last successful fetch."""
        with self._lock:
            bundle = self._bundle
        if not bundle:
            return []
        pairs: list[tuple[Session, Activity]] = []
        for entry in bundle.get("dirs", []):
            acct = entry.get("account", {})
            label = acct.get("displayName") or acct.get("emailAddress") or ""
            for item in entry.get("sessions", []):
                data = item.get("session", {})
                session = Session(
                    pid=data.get("pid", 0),
                    session_id=data.get("sessionId", ""),
                    cwd=data.get("cwd", ""),
                    status=data.get("status", "unknown"),
                    name=data.get("name", ""),
                    kind=data.get("kind", ""),
                    started_at=data.get("startedAt", 0),
                    status_updated_at=data.get("statusUpdatedAt", 0),
                    bridge_session_id=data.get("bridgeSessionId", ""),
                    tmux=data.get("tmux", ""),
                    config_dir=Path(entry.get("config_dir", "")),
                    account=label,
                    host=self.host,
                    raw=data,
                )
                a = item.get("activity", {})
                req_ts = a.get("request_ts", "")
                if isinstance(req_ts, (int, float)):  # history fallback: epoch ms
                    req_ts = (
                        datetime.fromtimestamp(
                            req_ts / 1000, tz=timezone.utc
                        ).isoformat()
                        if req_ts
                        else ""
                    )
                tool = a.get("tool")
                last_text = a.get("last_text", "")
                if tool:
                    doing = _tool_label(tool[0], {"description": tool[1]})
                else:
                    doing = last_text
                pairs.append(
                    (
                        session,
                        Activity(
                            request=a.get("request", ""),
                            request_ts=req_ts,
                            doing=doing,
                            last_text=last_text,
                            last_text_ts=a.get("last_text_ts", ""),
                            last_event_ts=a.get("last_event_ts", ""),
                            mid_turns=int(a.get("mid_turns", 0) or 0),
                            turns_capped=bool(a.get("turns_capped")),
                        ),
                    )
                )
        return pairs
