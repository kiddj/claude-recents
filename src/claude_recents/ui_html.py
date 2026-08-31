"""HTML/CSS/JS for the popover panel rendered inside a WKWebView.

The Python side calls `window.update(data)` every tick with:
  { account: str,
    sessions: [{ id, project, status, elapsed, summary, request, doing,
                 doing_kind, cwd }] }
"""

PAGE_HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<style>
:root { color-scheme: light; }
body.dark { color-scheme: dark; }
* { margin: 0; box-sizing: border-box; }
html, body {
  overflow-x: hidden; max-width: 100%;
  overscroll-behavior-x: none;  /* no horizontal rubber-banding */
}
body {
  --tx: #1c1c21; --tx2: #5c5c66; --tx3: #8e8e99;
  font-family: -apple-system, "Apple SD Gothic Neo", sans-serif;
  font-size: 13px; color: var(--tx); background: #ebebf0;
  -webkit-user-select: none; cursor: default;
}
body.dark {
  --tx: #f2f2f6; --tx2: #b9b9c6; --tx3: #84848f;
  color: var(--tx); background: #1b1b21;
}
header {
  position: sticky; top: 0; z-index: 2;
  display: flex; align-items: baseline; gap: 8px;
  padding: 9px 12px 8px;
  background: #ebebf0;
  border-bottom: 1px solid rgba(0,0,0,.1);
}
body.dark header { background: #1e1e24; border-color: rgba(255,255,255,.09); }
header h1 { font-size: 13px; font-weight: 700; }
header .acct { margin-left: auto; font-size: 11px; opacity: .55; }
#list { padding: 6px 8px 0; }
.card {
  contain: content;  /* keeps layout/paint local to the card while scrolling */
  border-radius: 10px; padding: 9px 11px; margin-bottom: 8px;
  background: #ffffff;
  border: 1px solid rgba(0,0,0,.1);
}
body.dark .card {
  background: #2d2d36;
  border-color: rgba(255,255,255,.09);
}
.card.st-busy { border-color: #2f9e44; }
body.dark .card.st-busy { border-color: rgba(52,199,89,.4); }
.card.st-waiting { border-color: #e8790c; }
body.dark .card.st-waiting { border-color: rgba(255,159,10,.4); }
.top {
  display: flex; align-items: center; gap: 7px;
  padding-bottom: 6px; margin-bottom: 1px;
  border-bottom: 1px solid rgba(0,0,0,.09);
}
body.dark .top { border-bottom-color: rgba(255,255,255,.07); }
.dot { width: 9px; height: 9px; border-radius: 50%; background: #a1a1a6; flex: none; }
.dot.busy { background: #34c759; animation: pulse 1.6s ease-in-out infinite; }
.dot.waiting { background: #ff9f0a; animation: pulse 1.6s ease-in-out infinite; }
.dot.stalled {
  background: transparent; width: 7px; height: 7px;
  border: 2px solid #e08a0a;
}
@keyframes pulse { 50% { opacity: .35; } }
.proj {
  font-weight: 600; font-size: 12.5px;
  flex: 0 1 auto; min-width: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.projtag { flex: none; font-size: 10.5px; color: var(--tx2); font-weight: 400; }
.stalledbadge {
  flex: none; font-size: 10px; font-weight: 700;
  padding: 1.5px 7px; border-radius: 9px;
  background: rgba(224,138,10,.15); color: #e08a0a;
}
.card.open .proj { white-space: normal; }
.acctbadge {
  flex: none; font-size: 10px; font-weight: 600; opacity: .65;
  padding: 1.5px 7px; border-radius: 9px;
  background: rgba(175,82,222,.15); color: #af52de;
}
.hostbadge {
  flex: none; font-size: 10px; font-weight: 600; opacity: .75;
  padding: 1.5px 7px; border-radius: 9px;
  background: rgba(90,200,250,.16); color: #0a84c1;
}
.updbar {
  display: flex; align-items: center; gap: 8px;
  margin: 8px 10px 0; padding: 7px 11px; border-radius: 9px;
  font-size: 11.5px; font-weight: 600;
  background: rgba(232,121,12,.1); color: var(--tx);
  border: 1px solid #e8790c;
}
body.dark .updbar {
  background: rgba(255,159,10,.14);
  border-color: rgba(255,159,10,.55);
}
.updbar button {
  margin-left: auto; border: none; border-radius: 6px; flex: none;
  padding: 3px 10px; font-size: 11px; font-weight: 600;
  background: #e8790c; color: #fff; cursor: pointer; font-family: inherit;
}
body.dark .updbar button { background: #ff9f0a; color: #291800; }
.updbar .upderr { margin-left: auto; color: #e0443e; font-size: 10.5px; }
.hosterr {
  margin: 0 2px 8px; padding: 6px 10px; border-radius: 8px;
  font-size: 11px; line-height: 1.4;
  background: rgba(255,159,10,.12); color: #c77700;
}
.elapsed { margin-left: auto; font-size: 10.5px; color: var(--tx2); flex: none; }
.summary { font-size: 12px; line-height: 1.5; margin: 7px 0 2px; font-weight: 500; color: var(--tx); }
.summary.pending { color: var(--tx3); font-weight: 400; font-style: italic; }
.chat { display: flex; flex-direction: column; gap: 4px; margin-top: 6px; }
.bubble {
  max-width: 92%; padding: 5px 9px; border-radius: 10px;
  font-size: 11.5px; line-height: 1.5;
}
.bubble.user {
  align-self: flex-end; border-bottom-right-radius: 4px;
  background: #0a84ff; color: #ffffff;
}
.bubble.asst {
  align-self: flex-start; border-bottom-left-radius: 4px;
  background: #e9e9ec; color: #1c1c21;
}
body.dark .bubble.user { background: #0a6ae8; color: #ffffff; }
body.dark .bubble.asst { background: #3a3a41; color: #f2f2f6; }
.bubble.old { opacity: .65; }
.midturns {
  align-self: flex-start; font-size: 10px; color: var(--tx3);
  margin: 0 0 -1px 5px;
}
.btext {
  white-space: pre-wrap; word-break: break-word; overflow: hidden;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
}
.card.open .btext { -webkit-line-clamp: unset; }
.nowline {
  margin-top: 5px; font-size: 10.5px; color: var(--tx2);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.toggle {
  display: flex; align-items: center; gap: 4px;
  font-size: 11px; opacity: .7; cursor: pointer; user-select: none;
}
.toggle input { accent-color: #0a84ff; margin: 0; }
body.nosum .summary { display: none; }
.hbtn {
  margin-left: auto; align-self: center; flex: none;
  width: 25px; height: 25px; border: none; border-radius: 7px;
  background: transparent; color: var(--tx2); cursor: pointer;
  display: flex; align-items: center; justify-content: center; padding: 0;
}
.hbtn:active { background: rgba(0,0,0,.07); }
body.dark .hbtn:active { background: rgba(255,255,255,.1); }
@keyframes hspin { to { transform: rotate(360deg); } }
.hbtn.spinning svg { animation: hspin .7s linear; }
.seg {
  align-self: center; flex: none;
  display: flex; gap: 2px; padding: 2px; border-radius: 8px;
  background: rgba(0,0,0,.06);
}
body.dark .seg { background: rgba(255,255,255,.09); }
.seg-btn {
  width: 27px; height: 21px; border: none; border-radius: 6px;
  background: transparent; color: var(--tx3); cursor: pointer;
  display: flex; align-items: center; justify-content: center; padding: 0;
  transition: background .15s ease, color .15s ease;
}
.seg-btn.active { background: #ffffff; color: var(--tx); }
body.dark .seg-btn.active { background: #494a56; }
.addzone {
  margin-top: 6px; padding: 8px 10px 9px;
  border-top: 1px solid rgba(0,0,0,.1);
  background: rgba(0,0,0,.03);
}
body.dark .addzone {
  border-top-color: rgba(255,255,255,.12);
  background: rgba(255,255,255,.04);
}
.addzone .zhint {
  margin-top: 8px; font-size: 10.5px; color: var(--tx3); line-height: 1.5;
}
.addzone .zhint code {
  font-family: ui-monospace, Menlo, monospace; font-size: 10px;
  background: rgba(128,128,140,.15); padding: 1px 4px; border-radius: 4px;
}
.addzone .zlabel {
  font-size: 11px; font-weight: 700; color: var(--tx2);
  margin-bottom: 7px; display: block;
}
.addbar { display: flex; gap: 6px; }
.selwrap { position: relative; flex: 1; min-width: 0; display: flex; }
.selwrap::after {
  content: '▾'; position: absolute; right: 10px; top: 50%;
  transform: translateY(-50%); pointer-events: none;
  font-size: 11px; color: var(--tx2);
}
.addbar select {
  -webkit-appearance: none; appearance: none;
  width: 100%; height: 28px; padding: 0 26px 0 10px;
  font-size: 12px; font-family: inherit;
  border: 1px solid rgba(0,0,0,.14); border-radius: 7px;
  background: #ffffff; color: var(--tx); outline: none; cursor: pointer;
}
.addbar select:focus { border-color: #0a84ff; }
body.dark .addbar select {
  background: #35353d; border-color: rgba(255,255,255,.16);
}
.addbar button {
  border: none; border-radius: 7px; padding: 0 13px; height: 28px;
  font-size: 12px; flex: none;
  background: #0a84ff; color: #fff; cursor: pointer; font-family: inherit;
}
.addbar .cfgbtn {
  background: transparent; color: var(--tx2);
  border: 1px solid rgba(0,0,0,.14); padding: 0 11px;
}
body.dark .addbar .cfgbtn { border-color: rgba(255,255,255,.16); }
.hostrm {
  border: none; background: transparent; cursor: pointer; flex: none;
  color: #e0443e; padding: 0 5px; border-radius: 5px; height: 18px;
  display: inline-flex; align-items: center;
}
.rmset {
  display: inline-flex; gap: 4px; flex: none;
  margin-left: auto; height: 18px;
}
.rmset button {
  border: none; border-radius: 5px; cursor: pointer; font-family: inherit;
  font-size: 10.5px; font-weight: 700; padding: 0 8px; height: 18px;
  display: inline-flex; align-items: center;
}
.rmgo { background: #e0443e; color: #fff; }
.rmcancel {
  background: transparent; color: var(--tx2);
  border: 1px solid rgba(128,128,140,.4) !important;
}
.hostempty { font-size: 11.5px; color: var(--tx3); padding: 2px 6px 6px; }
.cwd {
  display: none;
  margin-top: 6px; font-size: 10px; color: var(--tx3);
  font-family: ui-monospace, Menlo, monospace;
}
.card.open .cwd { display: block; }
.empty { text-align: center; opacity: .5; padding: 48px 0; }
.hostsec {
  display: flex; align-items: center; gap: 8px;
  margin: 8px 2px 5px; padding-top: 7px;
  font-size: 11.5px; font-weight: 700; line-height: 18px;
  border-top: 1px solid rgba(0,0,0,.13);
}
.hostsec:first-child, #list > .hosterr + .hostsec { border-top: none; margin-top: 2px; padding-top: 0; }
body.dark .hostsec { border-top-color: rgba(255,255,255,.1); }
.hostcount { margin-left: auto; font-size: 10.5px; font-weight: 400; color: var(--tx2); }
.hostcount .stale { color: #e0443e; font-weight: 600; }
.hostsec.armed .hostcount { display: none; }
.hostsec { cursor: grab; }
.hostsec:active { cursor: grabbing; }
.grip { font-size: 10px; opacity: .35; margin-right: 2px; }
.hchev { font-size: 13px; opacity: .8; margin-right: 3px; }
.hostdot { width: 8px; height: 8px; border-radius: 50%; flex: none; background: #a1a1a6; }
.hostdot.ok { background: #34c759; }
.hostdot.err { background: #e0443e; }
.hostdot.conn { background: #f5c518; animation: pulse 1.2s ease-in-out infinite; }
.hostbody.hidden { display: none; }
.hostsec.dragging { opacity: .35; }
#dropline {
  position: fixed; left: 10px; right: 10px; height: 3px;
  background: #0a84ff; border-radius: 2px; display: none;
  z-index: 10; pointer-events: none;
}
.grouphdr {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 5px 4px; font-size: 10.5px; font-weight: 600;
  letter-spacing: .3px; color: var(--tx2);
}
.grouphdr .chev { font-size: 12px; }
.groupbody { display: none; }
.groupbody.expanded { display: block; }
footer { padding: 4px 12px 8px; font-size: 10px; opacity: .4; text-align: center; }
</style></head>
<body>
<header><h1>Recents</h1>
<!-- 요약 토글 (기능 비활성화로 주석 처리; 복원 시 app.py의 briefings_enabled도 원복)
<label class="toggle"><input type="checkbox" id="sumtoggle"
  onchange="document.body.classList.toggle('nosum', !this.checked);try{window.webkit.messageHandlers.app.postMessage({cmd:'briefings',value:this.checked})}catch(e){}">Summary</label>
-->
<button class="hbtn" id="refreshbtn" onclick="forceRefresh()" aria-label="Refresh now"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg></button>
<div class="seg" role="group" aria-label="Theme">
<button class="seg-btn" id="seg-light" onclick="setTheme('light')" aria-label="Light mode"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="12" r="4.4"/><path d="M12 2v2.4M12 19.6V22M4.8 4.8l1.7 1.7M17.5 17.5l1.7 1.7M2 12h2.4M19.6 12H22M4.8 19.2l1.7-1.7M17.5 6.5l1.7-1.7"/></svg></button>
<button class="seg-btn" id="seg-dark" onclick="setTheme('dark')" aria-label="Dark mode"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg></button>
</div>
</header>
<div id="updbar"></div>
<div id="list"><div class="empty">Loading…</div></div>
<div class="addzone">
  <span class="zlabel">Add Server</span>
  <div class="addbar">
    <span class="selwrap"><select id="newhost"></select></span>
    <button onclick="addHost()">Add</button>
    <button class="cfgbtn" onclick="openSshConfig()" title="Open ~/.ssh/config in your editor">Open Config</button>
  </div>
  <div class="zhint">This list comes from <code>~/.ssh/config</code> — add a
  <code>Host &lt;alias&gt;</code> entry there and it appears here.
  Requires passwordless (key-based) SSH — set up once with
  <code>ssh-copy-id &lt;host&gt;</code>.</div>
</div>
<div id="dropline"></div>
<footer>Click a card to expand · Right-click the menu bar icon to quit</footer>
<script>
function esc(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}
window._theme = 'auto';
function applyTheme(theme) {
  const dark = theme === 'dark' || (theme !== 'light' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.body.classList.toggle('dark', dark);
  const l = document.getElementById('seg-light');
  const d = document.getElementById('seg-dark');
  if (l && d) {
    l.classList.toggle('active', !dark);
    d.classList.toggle('active', dark);
  }
}
window.forceRefresh = function () {
  const b = document.getElementById('refreshbtn');
  b.classList.add('spinning');
  setTimeout(function () { b.classList.remove('spinning'); }, 700);
  window._lastKey = null;  // force the next update to rebuild
  try {
    window.webkit.messageHandlers.app.postMessage({ cmd: 'refresh' });
  } catch (err) {}
};
window.setTheme = function (mode) {
  window._theme = mode;
  applyTheme(mode);
  try {
    window.webkit.messageHandlers.app.postMessage(
      { cmd: 'theme', value: mode }
    );
  } catch (err) {}
};
applyTheme('auto');
function bubble(cls, text) {
  return '<div class="bubble ' + cls + '"><div class="btext">' + esc(text) +
    '</div></div>';
}
function card(s, open, showAccount, briefings) {
  const active = ['busy', 'shell', 'waiting'].indexOf(s.status) !== -1;
  const dotCls = s.status === 'waiting' ? ' waiting'
    : (s.status === 'stalled' ? ' stalled' : (active ? ' busy' : ''));
  const stalledBadge = s.status === 'stalled'
    ? '<span class="stalledbadge">stalled</span>' : '';
  let summaryLine = '';
  if (briefings) {
    if (s.summary) {
      summaryLine = '<div class="summary">' + esc(s.summary) + '</div>';
    } else if (active) {
      summaryLine = '<div class="summary pending">Generating summary…</div>';
    }
  }
  const acctBadge = (showAccount && s.account)
    ? '<span class="acctbadge">' + esc(s.account) + '</span>'
    : '';
  let chat = '';
  if (s.answer && s.answer_old) chat += bubble('asst old', s.answer);
  if (s.request) chat += bubble('user', s.request);
  if (s.answer && !s.answer_old) {
    if (s.mid_turns > 0) {
      chat += '<div class="midturns">⋯ ' + s.mid_turns +
        (s.turns_capped ? '+' : '') + ' earlier replies</div>';
    }
    chat += bubble('asst', s.answer);
  }
  if (chat) chat = '<div class="chat">' + chat + '</div>';
  let nowLine = '';
  if (active) {
    const tool = (s.doing && s.doing !== s.answer) ? esc(s.doing) : '';
    if (s.answer_old || !s.answer) {
      nowLine = '<div class="nowline">⏳ ' + (tool || 'Writing a reply…') + '</div>';
    } else if (tool) {
      nowLine = '<div class="nowline">⏳ ' + tool + '</div>';
    }
  }
  const stCls = s.status === 'waiting' ? ' st-waiting' : (active ? ' st-busy' : ' st-idle');
  return '<div class="card' + stCls + (open ? ' open' : '') + '" data-id="' + esc(s.id) + '"' +
    ' onclick="this.classList.toggle(\'open\')">' +
    '<div class="top"><span class="dot' + dotCls + '" style="animation-delay:' + pulsePhase(1.6) + '"></span>' +
    '<span class="proj">' + esc(s.title || s.project) + '</span>' +
    '<span class="projtag">' + esc(s.project) + '</span>' + stalledBadge + acctBadge +
    '<span class="elapsed">' + esc(s.elapsed) + '</span></div>' +
    summaryLine + chat + nowLine +
    '<div class="cwd">' + esc(s.cwd) + '</div></div>';
}
window.addEventListener('scroll', function () {
  window._scrollQuietAt = Date.now() + 350;
}, { passive: true });
window.update = function (data) {
  try {
    _updateImpl(data);
  } catch (e) {
    // A render bug must be visible, not an eternal "Loading…".
    document.getElementById('list').innerHTML =
      '<div class="empty">render error: ' + esc(String(e)) + '</div>';
  }
};
function _updateImpl(data) {
  if (window._dragging) return;  // don't rebuild mid-drag
  // Rebuilding layout mid-scroll causes hitches — wait for the scroll to
  // settle; the next 2s tick delivers the same data anyway.
  if (Date.now() < (window._scrollQuietAt || 0)) return;
  // Rebuilding 30+ cards every tick is wasteful when nothing changed.
  const key = JSON.stringify(data);
  if (window._lastKey === key) return;
  window._lastKey = key;
  const list = document.getElementById('list');
  const open = new Set(
    Array.from(document.querySelectorAll('.card.open')).map(c => c.dataset.id)
  );
  const expanded = new Set(
    Array.from(document.querySelectorAll('.groupbody.expanded'))
      .map(g => g.dataset.g)
  );
  // Only badge accounts when more than one is present.
  const showAccount =
    new Set(data.sessions.map(s => s.account).filter(Boolean)).size > 1;
  const briefings = !!data.briefings;
  const t = document.getElementById('sumtoggle');
  if (t && document.activeElement !== t) t.checked = briefings;
  document.body.classList.toggle('nosum', !briefings);
  if (data.theme) { window._theme = data.theme; }
  applyTheme(window._theme);

  const render = arr =>
    arr.map(s => card(s, open.has(s.id), showAccount, briefings)).join('');
  const section = (key, title, arr) => {
    if (!arr.length) return '';
    const isOpen = expanded.has(key);
    return '<div class="grouphdr" onclick="toggleGroup(this)">' +
      '<span class="chev">' + (isOpen ? '▾' : '▸') + '</span>' +
      title + ' (' + arr.length + ')</div>' +
      '<div class="groupbody' + (isOpen ? ' expanded' : '') + '" data-g="' +
      key + '">' + render(arr) + '</div>';
  };
  const hosts = (data.host_order || ['']).slice();
  data.sessions.forEach(s => {
    if (hosts.indexOf(s.host) === -1) hosts.push(s.host);
  });
  window._hosts = hosts;
  const collapsed = new Set(data.host_collapsed || []);
  window._collapsedHosts = Array.from(collapsed);
  let html = '';
  const rmArmed = (window._rmArm && Date.now() - window._rmArm.t < 8000)
    ? window._rmArm.h : null;
  hosts.forEach(h => {
    const arr = data.sessions.filter(s => s.host === h);
    if (!h && !arr.length && hosts.length === 1) {
      html += '<div class="empty">No running Claude Code sessions</div>';
      return;
    }
    const st = h ? (data.host_status || {})[h] : null;
    const busyN = arr.filter(
      s => ['busy', 'shell', 'waiting'].indexOf(s.status) !== -1
    ).length;
    const isCollapsed = collapsed.has(h);
    const armedHere = rmArmed === h;
    html += '<div class="hostsec' + (armedHere ? ' armed' : '') +
      '" draggable="true" data-host="' + esc(h) + '"' +
      ' onclick="hostToggle(this)"' +
      ' ondragstart="hostDragStart(event,this)"' +
      ' ondragend="hostDragEnd(this)">' +
      '<span class="grip">⠿</span>' +
      '<span class="hostdot ' + hostDotOf(h, data) + '" style="animation-delay:' + pulsePhase(1.2) + '"></span>' +
      (h ? '🖥 ' + esc(h) : '💻 This Mac') +
      '<span class="hostcount">' + busyN + ' active · ' + arr.length + ' total' +
      staleTag(st) + '</span>' + (h ? rmControls(h, armedHere) : '') +
      '</div>';
    const groups = { recent: [], week: [], old: [] };
    arr.forEach(s => (groups[s.group] || groups.old).push(s));
    let statusLine = '';
    if (st && st.state === 'error') {
      statusLine = '<div class="hosterr">⚠ Connection failed · ' + esc(st.error) +
        (arr.length ? ' — showing last received data' : '') + '</div>';
    }
    let body;
    if (arr.length) {
      body = statusLine +
        render(groups.recent) +
        section(h + '|week', 'Last week', groups.week) +
        section(h + '|old', 'Older', groups.old);
    } else if (st && st.state === 'connecting') {
      body = '<div class="hostempty">Connecting…</div>';
    } else if (statusLine) {
      body = statusLine;
    } else {
      body = '<div class="hostempty">No sessions — they will appear once connected</div>';
    }
    html += '<div class="hostbody' + (isCollapsed ? ' hidden' : '') + '">' +
      body + '</div>';
  });
  list.innerHTML = html;
  renderHostOptions(data.ssh_config_hosts || []);
  renderUpdateBar(data.update || {});
}
function pulsePhase(period) {
  // Rebuilding the DOM restarts CSS animations at 0%; anchoring the phase
  // to the wall clock makes the pulse continue seamlessly across rebuilds.
  return '-' + ((Date.now() / 1000) % period).toFixed(3) + 's';
}
function renderUpdateBar(u) {
  const el = document.getElementById('updbar');
  const key = JSON.stringify(u);
  if (el.dataset.key === key) return;
  el.dataset.key = key;
  if (u.state === 'updating') {
    el.innerHTML = '<div class="updbar">Updating to ' + esc(u.latest) + '…</div>';
  } else if (u.state && u.state.indexOf('error') === 0) {
    el.innerHTML = '<div class="updbar">Update failed' +
      '<span class="upderr">' + esc(u.state) + '</span></div>';
  } else if (u.available) {
    el.innerHTML = '<div class="updbar">v' + esc(u.latest) + ' is available' +
      '<button onclick="selfUpdate()">Update &amp; Restart</button></div>';
  } else {
    el.innerHTML = '';
  }
}
window.selfUpdate = function () {
  try {
    window.webkit.messageHandlers.app.postMessage({ cmd: 'self_update' });
  } catch (err) {}
};
window.hostToggle = function (el) {
  // A click that lands right after a drag is drag residue, not a toggle.
  if (Date.now() - (window._lastDragEnd || 0) < 400) return;
  const body = el.nextElementSibling;
  if (!body) return;
  body.classList.toggle('hidden');
  const isCollapsed = body.classList.contains('hidden');
  const set = new Set(window._collapsedHosts || []);
  if (isCollapsed) set.add(el.dataset.host); else set.delete(el.dataset.host);
  window._collapsedHosts = Array.from(set);
  try {
    window.webkit.messageHandlers.app.postMessage(
      { cmd: 'host_collapsed', value: window._collapsedHosts }
    );
  } catch (err) {}
};
window.openSshConfig = function () {
  try {
    window.webkit.messageHandlers.app.postMessage({ cmd: 'open_ssh_config' });
  } catch (err) {}
};
window.addHost = function () {
  const sel = document.getElementById('newhost');
  const h = (sel.value || '').trim();
  if (!h) return;
  try {
    window.webkit.messageHandlers.app.postMessage({ cmd: 'add_host', value: h });
  } catch (err) {}
};
function renderHostOptions(hosts) {
  const sel = document.getElementById('newhost');
  const key = JSON.stringify(hosts);
  if (sel.dataset.key === key) return;
  sel.dataset.key = key;
  if (!hosts.length) {
    sel.innerHTML = '<option value="" disabled selected>No servers to add from ~/.ssh/config</option>';
    return;
  }
  sel.innerHTML = hosts.map(h =>
    '<option value="' + esc(h) + '">' + esc(h) + '</option>').join('');
}
window.removeHost = function (h) {
  try {
    window.webkit.messageHandlers.app.postMessage({ cmd: 'remove_host', value: h });
  } catch (err) {}
};
var UNLINK_SVG = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none"' +
  ' stroke="currentColor" stroke-width="2" stroke-linecap="round"' +
  ' stroke-linejoin="round">' +
  '<path d="m18.84 12.25 1.72-1.71a5.004 5.004 0 0 0-.12-7.07 5.006 5.006 0 0 0-6.95 0l-1.72 1.71"/>' +
  '<path d="m5.17 11.75-1.71 1.71a5.004 5.004 0 0 0 .12 7.07 5.006 5.006 0 0 0 6.95 0l1.71-1.71"/>' +
  '<line x1="8" y1="2" x2="8" y2="5"/><line x1="2" y1="8" x2="5" y2="8"/>' +
  '<line x1="16" y1="19" x2="16" y2="22"/><line x1="19" y1="16" x2="22" y2="16"/></svg>';
function rmControls(h, armed) {
  if (armed) {
    return '<span class="rmset">' +
      '<button class="rmgo" data-host="' + esc(h) + '"' +
      ' onclick="hostRmGo(event,this)">Disconnect</button>' +
      '<button class="rmcancel" onclick="hostRmCancel(event,this)">Cancel</button>' +
      '</span>';
  }
  return '<button class="hostrm" data-host="' + esc(h) + '"' +
    ' onclick="hostRm(event,this)" aria-label="Disconnect">' + UNLINK_SVG + '</button>';
}
function staleTag(st) {
  // Only shown when the data is meaningfully old — silence is freshness.
  if (!st || st.age_s === undefined || st.age_s < 60) return '';
  const m = Math.floor(st.age_s / 60);
  const t = m < 60 ? m + 'm' : Math.floor(m / 60) + 'h';
  return ' · <span class="stale">' + t + ' old</span>';
}
function hostDotOf(h, data) {
  if (!h) return 'ok';  // this Mac
  const st = (data.host_status || {})[h];
  if (!st || st.state === 'connecting') return 'conn';
  return st.state === 'ok' ? 'ok' : 'err';
}
window.hostRm = function (e, el) {
  e.stopPropagation();
  const h = el.dataset.host;
  window._rmArm = { h: h, t: Date.now() };
  el.closest('.hostsec').classList.add('armed');
  el.outerHTML = rmControls(h, true);
};
window.hostRmGo = function (e, el) {
  e.stopPropagation();
  window._rmArm = null;
  removeHost(el.dataset.host);
};
window.hostRmCancel = function (e, el) {
  e.stopPropagation();
  const h = window._rmArm ? window._rmArm.h : '';
  window._rmArm = null;
  const sec = el.closest('.hostsec');
  if (sec) sec.classList.remove('armed');
  el.parentElement.outerHTML = rmControls(h, false);
};
window.hostDragStart = function (e, el) {
  window._dragHost = el.dataset.host;
  window._dragging = true;
  el.classList.add('dragging');
  // WebKit does not initiate an HTML5 drag unless setData is called.
  e.dataTransfer.setData('text/plain', el.dataset.host);
  e.dataTransfer.effectAllowed = 'move';
};
window.hostDragEnd = function (el) {
  el.classList.remove('dragging');
  document.getElementById('dropline').style.display = 'none';
  window._dragging = false;
  window._lastDragEnd = Date.now();
};
// Where would a drop at clientY land? Returns the insertion slot among the
// visible sections (excluding the dragged one) and the y for the indicator.
function dropSlot(clientY) {
  const others = Array.from(document.querySelectorAll('.hostsec'))
    .filter(s => s.dataset.host !== window._dragHost);
  if (!others.length) return null;
  let idx = 0;
  others.forEach(s => {
    const r = s.getBoundingClientRect();
    if (clientY > r.top + r.height / 2) idx++;
  });
  let y;
  if (idx >= others.length) {
    const last = others[others.length - 1];
    const body = last.nextElementSibling;
    const anchor = (body && !body.classList.contains('hidden')) ? body : last;
    y = anchor.getBoundingClientRect().bottom + 2;
  } else {
    y = others[idx].getBoundingClientRect().top - 4;
  }
  return { idx: idx, others: others, y: y };
}
document.addEventListener('dragover', function (e) {
  if (window._dragHost === undefined) return;
  e.preventDefault();  // whole panel accepts the drop
  const slot = dropSlot(e.clientY);
  const line = document.getElementById('dropline');
  if (slot) {
    line.style.display = 'block';
    line.style.top = slot.y + 'px';
  }
});
document.addEventListener('drop', function (e) {
  if (window._dragHost === undefined) return;
  e.preventDefault();
  const from = window._dragHost;
  const slot = dropSlot(e.clientY);
  window._dragHost = undefined;
  window._dragging = false;
  window._lastDragEnd = Date.now();
  document.getElementById('dropline').style.display = 'none';
  if (!slot) return;
  const order = (window._hosts || []).slice();
  order.splice(order.indexOf(from), 1);
  const visible = slot.others.map(s => s.dataset.host);
  const insertAt = slot.idx >= visible.length
    ? order.length
    : order.indexOf(visible[slot.idx]);
  order.splice(insertAt, 0, from);
  try {
    window.webkit.messageHandlers.app.postMessage(
      { cmd: 'host_order', value: order }
    );
  } catch (err) {}
});
window.toggleGroup = function (el) {
  const body = el.nextElementSibling;
  body.classList.toggle('expanded');
  el.querySelector('.chev').textContent =
    body.classList.contains('expanded') ? '▾' : '▸';
};
</script>
</body></html>
"""
