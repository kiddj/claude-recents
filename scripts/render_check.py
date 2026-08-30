"""Render the panel with synthetic data and save a PNG.

Regression check for the WKWebView UI: JS runtime errors (e.g. TDZ bugs
that `node --check` cannot catch) surface here as a broken/error render.
Also used to produce the README screenshots.

Usage: .venv/bin/python scripts/render_check.py out.png [dark|light]
"""
import json, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "src"))
from AppKit import NSApplication, NSApplicationActivationPolicyProhibited, NSMakeRect, NSObject, NSTimer, NSBitmapImageRep, NSPNGFileType
from WebKit import WKWebView, WKWebViewConfiguration, WKSnapshotConfiguration
from claude_recents.ui_html import PAGE_HTML

DATA = {
    "sessions": [
        {"id": "a1", "title": "auth-flaky-test", "project": "api-server", "account": "", "host": "",
         "status": "busy", "group": "recent", "elapsed": "working · 4m", "summary": "",
         "request": "The auth test is flaky on CI — find the root cause and fix it, then rerun the suite.",
         "answer": "Found it: the token fixture expires mid-run. Pinning the clock in the fixture and rerunning CI now.",
         "answer_old": False, "mid_turns": 0, "doing": "Running command · pytest tests/auth -x", "cwd": "~/work/api-server", "turns_capped": False},
        {"id": "a2", "title": "docs-refresh", "project": "website", "account": "", "host": "",
         "status": "idle", "group": "recent", "elapsed": "2h ago", "summary": "",
         "request": "Update the quickstart guide for the new CLI flags",
         "answer": "Done — rewrote the quickstart with the new flags, added a migration note, and previewed the build locally.",
         "answer_old": False, "mid_turns": 0, "doing": "", "cwd": "~/work/website", "turns_capped": False},
        {"id": "b1", "title": "nightly-training", "project": "trainer", "account": "", "host": "gpu-server",
         "status": "busy", "group": "recent", "elapsed": "working · 3h", "summary": "",
         "request": "Kick off the nightly run and watch for OOMs — restart with a smaller batch if it dies.",
         "answer": "Step 41k, loss 1.83 and stable. One OOM at step 12k; restarted at batch 48 and it has been healthy since.",
         "answer_old": False, "mid_turns": 5, "doing": "Reading file · logs/train.log", "cwd": "~/proj/trainer", "turns_capped": False},
        {"id": "b2", "title": "data-pipeline", "project": "etl", "account": "", "host": "gpu-server",
         "status": "waiting", "group": "recent", "elapsed": "working · 12m", "summary": "",
         "request": "Backfill last week's events into the warehouse",
         "answer": "Dry run looks correct (1.2M rows). Waiting for your approval to run the real backfill.",
         "answer_old": False, "mid_turns": 0, "doing": "", "cwd": "~/proj/etl", "turns_capped": False},
        {"id": "b3", "title": "old-experiment", "project": "sandbox", "account": "", "host": "gpu-server",
         "status": "stalled", "group": "recent", "elapsed": "2d ago", "summary": "",
         "request": "Watch the queue and restart failed jobs",
         "answer": "Watcher armed. I'll report when anything fails.",
         "answer_old": False, "mid_turns": 0, "doing": "", "cwd": "~/proj/sandbox", "turns_capped": False},
    ],
    "host_order": ["", "gpu-server"],
    "host_status": {"gpu-server": {"state": "ok", "error": ""}},
    "host_collapsed": [], "briefings": False, "ssh_hosts": ["gpu-server"],
    "ssh_config_hosts": ["staging-box"], "theme": "dark",
}

OUT = sys.argv[1]
THEME = sys.argv[2] if len(sys.argv) > 2 else "dark"
DATA["theme"] = THEME
app = NSApplication.sharedApplication()
app.setActivationPolicy_(NSApplicationActivationPolicyProhibited)

class D(NSObject):
    def start_(self, _t):
        self.web = WKWebView.alloc().initWithFrame_configuration_(
            NSMakeRect(0, 0, 460, 1010), WKWebViewConfiguration.alloc().init())
        self.web.loadHTMLString_baseURL_(PAGE_HTML, None)
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(2.5, self, "inject:", None, False)
    def inject_(self, _t):
        js = ("var st=document.createElement('style');st.textContent='*{transition:none !important;animation:none !important}';document.head.appendChild(st);"
              + "window.update(%s)" % json.dumps(DATA, ensure_ascii=False))
        self.web.evaluateJavaScript_completionHandler_(js, None)
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(2.0, self, "snap:", None, False)
    def snap_(self, _t):
        def done(image, error):
            if image:
                rep = NSBitmapImageRep.alloc().initWithData_(image.TIFFRepresentation())
                rep.representationUsingType_properties_(NSPNGFileType, None).writeToFile_atomically_(OUT, True)
                print("saved", OUT)
            else:
                print("error", error)
            app.terminate_(None)
        self.web.takeSnapshotWithConfiguration_completionHandler_(WKSnapshotConfiguration.alloc().init(), done)

d = D.alloc().init()
NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(0.1, d, "start:", None, False)
app.run()
