"""claude-recents: macOS menu bar app showing live Claude Code sessions.

Clicking the status item opens an NSPopover with a card per session
(rendered in a WKWebView); right-clicking shows a quit menu.
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSEventMaskLeftMouseUp,
    NSEventMaskRightMouseUp,
    NSEventTypeRightMouseUp,
    NSMakeRect,
    NSMakeSize,
    NSMaxYEdge,
    NSMenu,
    NSMenuItem,
    NSObject,
    NSPopover,
    NSPopoverBehaviorTransient,
    NSStatusBar,
    NSTimer,
    NSVariableStatusItemLength,
    NSViewController,
)
from WebKit import WKWebView, WKWebViewConfiguration

from .account import current_account
from .remote import RemoteHost, ssh_hosts
from .sessions import APP_CONFIG_PATH, Session, live_sessions
from .summarizer import Summarizer
from .transcript import activity
from .ui_html import PAGE_HTML

REFRESH_SECONDS = 2.0
PANEL_WIDTH = 460


def _panel_size() -> tuple:
    """Panel fills most of the screen height; config can override.
    (~/.config/claude-recents/config.json: "panel_width"/"panel_height")"""
    from AppKit import NSScreen

    cfg = _load_app_config()
    screen = NSScreen.mainScreen()
    avail = int(screen.visibleFrame().size.height) - 24 if screen else 700
    width = int(cfg.get("panel_width", PANEL_WIDTH))
    height = int(cfg.get("panel_height", avail))
    return (width, height)

AGENT_LABEL = "com.kiddj.claude-recents"
AGENT_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{AGENT_LABEL}.plist"


def _autostart_command() -> list[str]:
    """How launchd should start this app: the bundle binary when running
    from a .app, the installed console script otherwise."""
    from AppKit import NSBundle

    # Path checks are unreliable here — plain python also lives inside
    # Python.app. Only trust OUR bundle id.
    bundle = NSBundle.mainBundle()
    if bundle and str(bundle.bundleIdentifier() or "") == AGENT_LABEL:
        return [str(bundle.executablePath())]
    script = shutil.which("claude-recents")
    if script:
        return [script]
    return [sys.executable, "-m", "claude_recents.app"]


def autostart_enabled() -> bool:
    return AGENT_PLIST.exists()


def enable_autostart() -> None:
    """Write the LaunchAgent. Takes effect from the next login — we never
    bootstrap here (RunAtLoad would spawn a second instance immediately)."""
    cmd = _autostart_command()
    plist = {
        "Label": AGENT_LABEL,
        "ProgramArguments": cmd,
        "RunAtLoad": True,
        "KeepAlive": False,
        "EnvironmentVariables": {
            # GUI apps launch without locale env; Korean transcripts need UTF-8.
            "PYTHONUTF8": "1",
            "LANG": "en_US.UTF-8",
            "PATH": (
                f"{Path(cmd[0]).parent}:"
                "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
            ),
        },
    }
    AGENT_PLIST.parent.mkdir(parents=True, exist_ok=True)
    with open(AGENT_PLIST, "wb") as f:
        plistlib.dump(plist, f)


def disable_autostart() -> None:
    # Remove the plist only. Never bootout: if THIS process is the launchd
    # job, bootout would kill the running app mid-click.
    AGENT_PLIST.unlink(missing_ok=True)


# Observed status values: busy, shell (running a command), waiting
# (pending permission), idle. The first three mean "actively working".
ACTIVE_STATUSES = ("busy", "shell", "waiting")

_HOME = str(Path.home())


def _load_app_config() -> dict:
    try:
        return json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_app_config(cfg: dict) -> None:
    try:
        APP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        APP_CONFIG_PATH.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def _save_app_config_key(key: str, value) -> None:
    cfg = _load_app_config()
    cfg[key] = value
    _save_app_config(cfg)


# SSH host names are passed to the ssh CLI — restrict to safe alias chars
# (leading '-' would be read as an ssh option).
_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]*$")


def _ssh_config_hosts() -> list[str]:
    """Concrete Host aliases from ~/.ssh/config (wildcards excluded)."""
    hosts: list[str] = []
    try:
        for line in (Path.home() / ".ssh" / "config").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.lower().startswith("host "):
                continue
            for tok in line.split()[1:]:
                if "*" in tok or "?" in tok or tok.startswith("!"):
                    continue
                if _HOST_RE.match(tok) and tok not in hosts:
                    hosts.append(tok)
    except OSError:
        pass
    return hosts


def _config_add_host(host: str) -> bool:
    """Add an SSH host to the config. Returns True if it was added."""
    if not _HOST_RE.match(host):
        return False
    cfg = _load_app_config()
    hosts = [str(h) for h in cfg.get("ssh_hosts", [])]
    if host in hosts:
        return False
    hosts.append(host)
    cfg["ssh_hosts"] = hosts
    _save_app_config(cfg)
    return True


def _config_remove_host(host: str) -> None:
    """Remove an SSH host and every trace of it (order, collapse state)."""
    cfg = _load_app_config()
    cfg["ssh_hosts"] = [h for h in cfg.get("ssh_hosts", []) if h != host]
    for key in ("host_order", "host_collapsed"):
        if key in cfg:
            cfg[key] = [h for h in cfg[key] if h != host]
    _save_app_config(cfg)


def _iso_ms(ts: str) -> float:
    """ISO-8601 timestamp (transcript format) → epoch ms, 0 on failure."""
    if not ts:
        return 0.0
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000
    except ValueError:
        return 0.0


def _fmt_elapsed(delta_ms: float, active: bool) -> str:
    mins = max(0, int(delta_ms / 60000))
    if active:
        if mins < 1:
            return "just started"
        if mins < 60:
            return f"working · {mins}m"
        if mins < 60 * 24:
            return f"working · {mins // 60}h"
        return f"working · {mins // (60 * 24)}d"
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins}m ago"
    if mins < 60 * 24:
        return f"{mins // 60}h ago"
    return f"{mins // (60 * 24)}d ago"


def collect(
    summarizer: Summarizer,
    account_label: str,
    summarize: bool = True,
    remotes: list | None = None,
) -> dict:
    now_ms = time.time() * 1000
    pairs = [(s, activity(s)) for s in live_sessions()]
    host_status = {}
    for r in remotes or []:
        pairs.extend(r.snapshot())
        state, err, age = r.status()
        host_status[r.host] = {
            "state": state,
            "error": err,
            "age_s": int(age) if age >= 0 else -1,
        }
    # Reference time per session = the user's latest request (transcript),
    # falling back to the last transcript event, then the status file.
    # statusUpdatedAt alone lies for long-lived sessions, so it's last.
    def ref_ms(pair) -> float:
        s, act = pair
        return (
            max(_iso_ms(act.request_ts), _iso_ms(act.last_event_ts))
            or float(s.status_updated_at or s.started_at or 0)
        )

    pairs.sort(key=ref_ms, reverse=True)
    sessions = []
    for s, act in pairs:
        ref = ref_ms((s, act))
        # A status flag can stick (a claude process left in a forgotten
        # tmux window keeps "shell" for days). Structural signals were
        # tested and rejected: unresolved-tool detection flickers between
        # calls, and every claude keeps a persistent shell child, so
        # child-process checks have zero discrimination. Time since last
        # observable activity is the honest signal; measured distribution
        # is bimodal (real work <12min vs zombies >1day), so a 3h cutoff
        # sits deep inside the gap while sparing long quiet tool runs.
        last_activity = max(ref, float(s.status_updated_at or 0))
        active = (
            s.status in ACTIVE_STATUSES
            and (now_ms - last_activity) < 3 * 60 * 60 * 1000
        )
        status_out = s.status if active or s.status not in ACTIVE_STATUSES else "idle" 
        age_days = (now_ms - ref) / 86400000 if ref else 999
        group = "recent" if age_days <= 3 else ("week" if age_days <= 7 else "old")
        if act.request or act.doing:
            # Haiku briefings regenerate only while the panel is open, and
            # only for sessions touched in the last 3 days — dozens of
            # dormant remote sessions would burn real quota otherwise.
            if summarize and group == "recent":
                summary = (
                    summarizer.get(
                        s.session_id, act.request, act.doing, act.last_text, active
                    )
                    or ""
                )
            else:
                summary = summarizer.peek(s.session_id) or ""
        else:
            summary = s.name or "(no activity)"
        cwd = s.cwd
        if cwd.startswith(_HOME):
            cwd = "~" + cwd[len(_HOME):]
        # Active sessions: time since the request being worked on;
        # idle ones: time since the last activity.
        base = _iso_ms(act.request_ts) if active else 0
        elapsed = _fmt_elapsed(now_ms - (base or ref), active) if ref else ""
        sessions.append(
            {
                "id": s.session_id,
                "title": s.name or s.project_label,
                "project": s.project_label,
                "account": s.account,
                "host": s.host,
                "status": status_out,
                "group": group,
                "elapsed": elapsed,
                "summary": summary,
                "request": act.request[:800],
                "answer": act.last_text[:800],
                "mid_turns": act.mid_turns,
                "turns_capped": act.turns_capped,
                # The stored answer may predate the latest request (question
                # asked, reply not yet written) — the UI must not present it
                # as the answer to the new request.
                "answer_old": bool(
                    act.last_text
                    and act.request_ts
                    and _iso_ms(act.last_text_ts) < _iso_ms(act.request_ts)
                ),
                "doing": act.doing[:300],
                "cwd": cwd,
            }
        )
    return {
        "account": account_label,
        "sessions": sessions,
        "host_status": host_status,
        "host_order": [""] + [r.host for r in (remotes or [])],
    }


class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, _note):
        self.summarizer = Summarizer()
        self.account_label = current_account().label
        # Hosts poll themselves: 10s while the panel is open, 60s otherwise.
        self.panel_shown = False
        self._interval_fn = lambda: 10 if self.panel_shown else 60
        self.remotes = [RemoteHost(h, self._interval_fn) for h in ssh_hosts()]
        cfg = _load_app_config()
        # 요약(Haiku 브리핑) 기능 전체 비활성화 — 재활성화하려면 아래 줄을
        # bool(cfg.get("briefings", True))로 되돌리고 UI 토글을 복원할 것.
        self.briefings_enabled = False
        self.host_order = [str(h) for h in cfg.get("host_order", [])]
        self.host_collapsed = [str(h) for h in cfg.get("host_collapsed", [])]
        self.theme = str(cfg.get("theme", "auto"))

        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )
        button = self.item.button()
        button.setTitle_("✳")
        button.setTarget_(self)
        button.setAction_("statusItemClicked:")
        button.sendActionOn_(NSEventMaskLeftMouseUp | NSEventMaskRightMouseUp)

        self.quit_menu = NSMenu.alloc().init()
        self.autostart_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Start at Login", "toggleAutostart:", ""
        )
        self.autostart_item.setTarget_(self)
        self.quit_menu.addItem_(self.autostart_item)
        self.quit_menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit Claude Recents", "terminate:", ""
        )
        self.quit_menu.addItem_(quit_item)

        panel_size = _panel_size()
        self.popover = NSPopover.alloc().init()
        self.popover.setBehavior_(NSPopoverBehaviorTransient)
        self.popover.setAnimates_(False)  # instant open/close; the fade felt laggy
        self.popover.setContentSize_(NSMakeSize(*panel_size))
        controller = NSViewController.alloc().init()
        config = WKWebViewConfiguration.alloc().init()
        config.userContentController().addScriptMessageHandler_name_(self, "app")
        self.web = WKWebView.alloc().initWithFrame_configuration_(
            NSMakeRect(0, 0, *panel_size), config
        )
        self.web.loadHTMLString_baseURL_(PAGE_HTML, None)
        controller.setView_(self.web)
        self.popover.setContentViewController_(controller)

        self.timer = (
            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                REFRESH_SECONDS, self, "tick:", None, True
            )
        )
        self.tick_(None)

    def statusItemClicked_(self, sender):
        event = NSApplication.sharedApplication().currentEvent()
        if event is not None and event.type() == NSEventTypeRightMouseUp:
            self.autostart_item.setState_(1 if autostart_enabled() else 0)
            self.item.popUpStatusItemMenu_(self.quit_menu)
            return
        if self.popover.isShown():
            self.popover.performClose_(None)
        else:
            # Recompute on every open: the user may have moved to a
            # different display since launch.
            self.popover.setContentSize_(NSMakeSize(*_panel_size()))
            # Fetch remotes immediately on open — after a VPN drop the
            # cached bundle can be minutes old, which reads as "old answer
            # under a new request" until the next poll catches up.
            for r in self.remotes:
                r.request_now()
            self.popover.showRelativeToRect_ofView_preferredEdge_(
                sender.bounds(), sender, NSMaxYEdge
            )
            self.tick_(None)

    def userContentController_didReceiveScriptMessage_(self, _controller, message):
        # message.body() is an NSDictionary, NOT a Python dict — an
        # isinstance(body, dict) check silently drops it. Duck-type instead.
        try:
            body = message.body()
            cmd, value = body.get("cmd"), body.get("value")
        except Exception:
            return
        if cmd == "briefings":
            self.briefings_enabled = bool(value)
            _save_app_config_key("briefings", self.briefings_enabled)
            self.tick_(None)
        elif cmd == "host_order":
            try:
                self.host_order = [str(h) for h in value]
            except TypeError:
                return
            _save_app_config_key("host_order", self.host_order)
            self.tick_(None)
        elif cmd == "host_collapsed":
            try:
                self.host_collapsed = [str(h) for h in value]
            except TypeError:
                return
            _save_app_config_key("host_collapsed", self.host_collapsed)
        elif cmd == "theme":
            if value in ("auto", "light", "dark"):
                self.theme = str(value)
                _save_app_config_key("theme", self.theme)
        elif cmd == "refresh":
            for r in self.remotes:
                r.request_now()
            self.tick_(None)
        elif cmd == "add_host":
            host = str(value or "").strip()
            if _config_add_host(host):
                self.remotes.append(RemoteHost(host, self._interval_fn))
                self.tick_(None)
        elif cmd == "remove_host":
            host = str(value or "")
            _config_remove_host(host)
            for r in self.remotes:
                if r.host == host:
                    r.stop()
            self.remotes = [r for r in self.remotes if r.host != host]
            self.host_order = [h for h in self.host_order if h != host]
            self.host_collapsed = [h for h in self.host_collapsed if h != host]
            self.tick_(None)

    def toggleAutostart_(self, _sender):
        if autostart_enabled():
            disable_autostart()
        else:
            enable_autostart()
        self.autostart_item.setState_(1 if autostart_enabled() else 0)

    def tick_(self, _timer):
        shown = self.popover.isShown()
        # Hosts poll themselves; we only publish the current panel state
        # so their loops pick the right interval.
        self.panel_shown = shown
        # Transcript parsing can touch megabytes of JSONL — doing it on the
        # main thread made the panel stutter. Collect in a worker thread,
        # apply the result back on the main thread.
        if getattr(self, "_collecting", False):
            return
        self._collecting = True
        threading.Thread(
            target=self._collect_bg, args=(shown,), daemon=True
        ).start()

    def _collect_bg(self, shown):
        try:
            data = collect(
                self.summarizer,
                self.account_label,
                summarize=shown and self.briefings_enabled,
                remotes=self.remotes,
            )
            data["briefings"] = self.briefings_enabled
            data["host_collapsed"] = self.host_collapsed
            data["ssh_hosts"] = [r.host for r in self.remotes]
            added = set(data["ssh_hosts"])
            data["ssh_config_hosts"] = [
                h for h in _ssh_config_hosts() if h not in added
            ]
            data["theme"] = self.theme
            # Apply the user's saved section order; unknown hosts keep default.
            avail = data["host_order"]
            data["host_order"] = [h for h in self.host_order if h in avail] + [
                h for h in avail if h not in self.host_order
            ]
            payload = json.dumps(data, ensure_ascii=False)
        except Exception:
            self._collecting = False
            return
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "applyData:", payload, False
        )

    def applyData_(self, payload):
        self._collecting = False
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            return
        busy = sum(
            1 for s in data["sessions"] if s["status"] in ACTIVE_STATUSES
        )
        # Active count only — totals grow unbounded and belong in the panel.
        self.item.button().setTitle_(f"✳ {busy}" if busy else "✳")
        if self.popover.isShown():
            self.web.evaluateJavaScript_completionHandler_(
                "window.update(%s)" % payload, None
            )


def main() -> None:
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
