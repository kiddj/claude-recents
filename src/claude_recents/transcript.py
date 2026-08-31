"""Extract "latest request" and "current activity" per session.

Sources:
- ~/.claude/history.jsonl: one line per submitted prompt, with sessionId
  and the display text.
- ~/.claude/projects/<slug>/<session-id>.jsonl: full transcript; the tail
  tells us what the assistant is doing right now (text or tool use).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .sessions import Session

_TAIL_BYTES = 256 * 1024


def _tail_lines(path: Path, max_bytes: int = _TAIL_BYTES) -> list[str]:
    try:
        size = path.stat().st_size
        with open(path, "rb") as fh:
            fh.seek(max(0, size - max_bytes))
            chunk = fh.read()
    except OSError:
        return []
    lines = chunk.split(b"\n")
    if size > max_bytes and lines:
        lines = lines[1:]  # drop the partial first line
    return [ln.decode("utf-8", "replace") for ln in lines if ln.strip()]


def latest_request(session: Session) -> str:
    """Most recent prompt the user typed into this session."""
    return parse_latest_request(
        _tail_lines(session.config_dir / "history.jsonl"), session.session_id
    )


@dataclass
class Activity:
    request: str = ""       # latest user request (from transcript, fallback history)
    request_ts: str = ""    # ISO timestamp of that request
    doing: str = ""         # latest assistant text or tool action
    last_text: str = ""     # latest assistant prose (the "result" for briefings)
    last_text_ts: str = ""  # ISO timestamp of that prose
    last_event_ts: str = "" # ISO timestamp of the last transcript event
    mid_turns: int = 0      # assistant text turns between request and last_text
    turns_capped: bool = False  # request fell outside the parse window: count is a floor


_TOOL_VERBS = {
    "Read": "Reading file",
    "Edit": "Editing file",
    "MultiEdit": "Editing file",
    "Write": "Writing file",
    "NotebookEdit": "Editing notebook",
    "Bash": "Running command",
    "Grep": "Searching code",
    "Glob": "Finding files",
    "WebFetch": "Fetching web page",
    "WebSearch": "Searching the web",
    "Task": "Running subagent",
    "Agent": "Running subagent",
    "TodoWrite": "Updating todo list",
    "AskUserQuestion": "Waiting for user input",
}


def _tool_label(name: str, tool_input: dict) -> str:
    target = (
        tool_input.get("description")
        or tool_input.get("file_path")
        or tool_input.get("path")
        or tool_input.get("pattern")
        or tool_input.get("prompt")
        or tool_input.get("command")
        or tool_input.get("url")
        or ""
    )
    target = str(target).strip().replace("\n", " ")
    if target.startswith(str(Path.home())):
        target = "~" + target[len(str(Path.home())):]
    if len(target) > 90:
        target = target[:87] + "..."
    verb = _TOOL_VERBS.get(name, f"Running {name}")
    return f"{verb} · {target}" if target else verb


def activity(session: Session) -> Activity:
    """Parse the transcript tail for the latest request and current action."""
    act = parse_activity(_tail_lines(session.transcript_path))
    if not act.request:
        try:
            big = session.transcript_path.stat().st_size > _TAIL_BYTES
        except OSError:
            big = False
        if big:
            # The wide window is a superset of the narrow one, so its
            # result is strictly better-informed — adopt it even when the
            # request still wasn't found (it may carry the answer that the
            # narrow window missed under megabytes of tool output).
            act = parse_activity(
                _tail_lines(session.transcript_path, 8 * 1024 * 1024)
            )
    if not act.request:
        act.request = latest_request(session)
    return act


def parse_activity(lines: list[str]) -> Activity:
    """Extract request/current action from transcript JSONL lines.

    Shared by the local file reader above and the SSH remote fetcher,
    which ships transcript tails over the wire.
    """
    act = Activity()
    # A "turn" is a response segment bounded by user events. tool_result
    # user events are intra-turn machinery; every other user event (typed
    # request, wakeup, notification) closes the current segment. Counting
    # assistant text messages directly over-counts: one turn often emits
    # prose between tool calls several times.
    segments = 0
    seg_has_text = False
    for ln in lines:
        try:
            event = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if event.get("isSidechain"):
            # Subagent traffic: its "user" prompts and replies are not the
            # user's, and once misread as the latest request.
            continue
        etype = event.get("type")
        if etype == "user":
            content = event.get("message", {}).get("content")
            if isinstance(content, list):
                # Typed requests with attachments arrive as block lists;
                # tool results do too — only the former count.
                if any(b.get("type") == "tool_result" for b in content if isinstance(b, dict)):
                    continue  # intra-turn: not a boundary
                content = "\n".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ).strip()
            # Turn boundary.
            if seg_has_text:
                segments += 1
                seg_has_text = False
            if event.get("isMeta"):
                continue
            if (
                isinstance(content, str)
                and content
                and not content.startswith("<")
                and not content.startswith("Another Claude session")
                and not content.startswith("[Request interrupted")
                and not content.startswith("This session is being continued")
            ):
                act.request = content
                act.request_ts = event.get("timestamp", act.request_ts)
                act.last_event_ts = event.get("timestamp", act.last_event_ts)
                segments = 0
        elif etype == "queue-operation":
            # A message typed while Claude is busy is queued instantly but
            # only surfaces as an `attachment` when actually delivered —
            # potentially minutes later during a long tool run. Show it as
            # the current request the moment it is typed.
            if event.get("operation") == "enqueue":
                content = str(event.get("content") or "").strip()
                if content and not content.startswith(("/", "<")):
                    act.request = content
                    act.request_ts = event.get("timestamp", act.request_ts)
                    act.last_event_ts = event.get("timestamp", act.last_event_ts)
                    segments = 0
        elif etype == "attachment":
            # Mid-turn interjections are recorded as queued_command
            # attachments, not user events — without this they never
            # replace the displayed request.
            att = event.get("attachment") or {}
            if (
                att.get("type") == "queued_command"
                and (att.get("origin") or {}).get("kind") == "human"
            ):
                prompt = str(att.get("prompt") or "").strip()
                if prompt and not prompt.startswith(("/", "<")):
                    act.request = prompt
                    act.request_ts = event.get("timestamp", act.request_ts)
                    act.last_event_ts = event.get("timestamp", act.last_event_ts)
                    segments = 0
        elif etype == "assistant":
            content = event.get("message", {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                btype = block.get("type")
                if btype == "text" and block.get("text", "").strip():
                    act.doing = block["text"].strip()
                    act.last_text = act.doing
                    act.last_text_ts = event.get("timestamp", act.last_text_ts)
                    seg_has_text = True
                elif btype == "tool_use":
                    act.doing = _tool_label(
                        block.get("name", "tool"), block.get("input", {}) or {}
                    )
            act.last_event_ts = event.get("timestamp", act.last_event_ts)
    if seg_has_text:
        segments += 1
    # Turns between the request and the answer shown (autonomous loops,
    # goal runs, etc. produce many) — the UI marks their existence only.
    act.mid_turns = max(0, segments - 1)
    act.turns_capped = not bool(act.request)
    return act


def parse_latest_request(history_lines: list[str], session_id: str) -> str:
    """Most recent prompt for a session, from history.jsonl lines."""
    best_ts, best = 0, ""
    for ln in history_lines:
        try:
            entry = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if entry.get("sessionId") != session_id:
            continue
        display = entry.get("display", "")
        if not display or display.startswith("/"):
            continue
        ts = entry.get("timestamp", 0)
        if ts >= best_ts:
            best_ts, best = ts, display
    return best
