# claude-recents

macOS 메뉴바에서 이 머신의 모든 Claude Code 세션을 실시간으로 보여주는 앱.
아이콘(`✳ busy/전체`)을 클릭하면 팝오버 패널이 열리고, 세션마다 카드 하나씩:

- 상태 표시등 (초록 점멸 = busy/shell, 주황 점멸 = waiting, 회색 = idle) + 경과 시간
- **브리핑**: "X 요청에 대해 …까지 처리했고 결과는 ~였습니다" 식의 1-2문장
  (Haiku 생성; 상태 변화 시에만, 세션당 최대 1회/60초, 패널 열림 + 최근 3일 세션만)
- **요청**: 최근 사용자 요청 전문 (카드 클릭으로 펼치기)
- **현재/최근**: 지금 하는 일 (예: "명령 실행 중 · npm test") 또는 마지막 응답
- 작업 폴더 경로

패널은 **서버별 구역**(💻 이 맥 / 🖥 호스트명, 작업 중·전체 카운트 포함)으로
나뉜다. 카드 제목은 세션의 실제 이름(`name`, `claude -n`이나 자동 파생)이고
옆에 프로젝트 폴더명이 회색으로 붙는다. 각 구역 안에서는 **사용자의 최근 요청
시각순**(트랜스크립트 기준, statusUpdatedAt 아님) 정렬, 3일 넘게 조용한 세션은
"지난 주" / "그 이전" 접이식 그룹으로 숨겨진다.

세션의 소속 구역은 **claude 프로세스가 실행되는 위치** 기준이다: 로컬 세션이
ssh 명령으로 서버를 조작해도 "이 맥"에 나오고, 서버에서 claude를 실행해야
(VS Code Remote-SSH 포함) 해당 서버 구역에 나온다.

아이콘 우클릭 → 종료.

## 구조

- PyObjC 직접 사용: `NSStatusBar` + `NSPopover` + `WKWebView` (HTML/CSS 카드 UI)
- `src/claude_recents/`
  - `app.py` — 상태바 아이콘, 팝오버, 2초 주기 갱신 루프
  - `ui_html.py` — 팝오버 패널 HTML/CSS/JS (`window.update(data)`로 갱신)
  - `sessions.py` — 살아있는 세션 발견
  - `transcript.py` — 요청/현재 활동 추출
  - `summarizer.py` — Haiku 한 줄 요약 (비동기 + 캐시 + 동시 2개 제한)
  - `account.py` — 계정 정보

## 멀티 계정

세션 검색은 여러 Claude 설정 디렉토리를 스캔한다:

1. 기본 `~/.claude` (또는 `CLAUDE_CONFIG_DIR`)
2. claude-swap 계정 프로필 `~/.claude-swap-backup/sessions/*/` (있으면 자동 인식)
3. `~/.config/claude-recents/config.json`의 `{"extra_config_dirs": ["~/.claude-work"]}`

계정이 2개 이상 잡히면 카드에 보라색 계정 배지가 표시된다. 다른 계정으로
세션을 띄우려면 claude-swap(`cswap run <계정>`)을 쓰거나
`CLAUDE_CONFIG_DIR=~/.claude-work claude`처럼 실행하면 된다.

## 원격 서버 모니터링 (SSH)

`~/.config/claude-recents/config.json`:

```json
{ "ssh_hosts": ["my-server"] }
```

각 호스트에 SSH 키 접속(BatchMode)이 되면, 폴링마다 파이썬 스크립트 하나를
`ssh <host> python3 -`로 흘려보내 서버의 `~/.claude/sessions/` + 트랜스크립트
tail + 계정 정보를 JSON으로 받아온다 (서버에 설치하는 것 없음, claude-swap
프로필도 자동 스캔). 카드에 `🖥 호스트` 배지가 붙고, 접속 실패 시 패널 상단에
경고줄이 표시된다. 폴링 주기: 패널 열림 10초 / 닫힘 60초.

## 데이터 소스

| 정보 | 소스 |
|---|---|
| 살아있는 세션, busy/idle | `~/.claude/sessions/<pid>.json` (+ PID 생존 확인) |
| 최근 사용자 요청 | 세션 트랜스크립트 tail, 폴백 `~/.claude/history.jsonl` |
| 현재 활동 | `~/.claude/projects/<slug>/<session-id>.jsonl` tail |
| 계정 정보 | `~/.claude.json` → `oauthAccount` |
| 한 줄 요약 | `claude -p --model haiku` (로그인된 클로드 구독 사용, API 키 불필요) |

- 요약 호출 시 `ANTHROPIC_API_KEY`를 환경에서 제거하고 claude.ai 로그인을 쓴다.
  API 직접 호출을 원하면 `CLAUDE_STATUS_USE_API=1` + `ANTHROPIC_API_KEY` 설정.
- **중요**: `claude -p` 헤드리스 세션(entrypoint `sdk-cli`)은 목록/요약 대상에서
  제외한다. 이 필터가 없으면 요약 호출이 만든 세션을 또 요약하는 무한 루프가 생긴다.

## 실행 / 관리

로그인 시 자동 시작 (LaunchAgent `~/Library/LaunchAgents/com.kiddj.claude-recents.plist`):

```sh
launchctl kickstart -k gui/501/com.kiddj.claude-recents   # 재시작
launchctl bootout gui/501/com.kiddj.claude-recents        # 중지
launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.kiddj.claude-recents.plist  # 시작
```

수동 실행 (개발용): `PYTHONPATH=src .venv/bin/python -m claude_recents.app`
로그: `/tmp/claude-recents.log`

주의: 백그라운드 셸(tmux 데몬 등, `launchctl managername`이 `Background`인 곳)에서
직접 실행하면 프로세스는 뜨지만 메뉴바 아이콘이 표시되지 않는다. GUI 세션
(`gui/501`) 안에서 실행되어야 하며, LaunchAgent가 이를 보장한다.

## 알려진 제약

- `~/.claude/sessions/`는 Claude Code의 **문서화되지 않은 내부 포맷** (v2.1.x 확인).
  업데이트로 깨지면 공식 hooks(SessionStart/UserPromptSubmit/Stop) 기반으로 전환.
- 이 머신의 세션만 보인다. 계정의 다른 기기/클라우드 세션을 열람하는 공식 API 없음
  (서드파티 OAuth 미지원). 원격 서버 세션은 SSH로 같은 파일을 읽어오는 방식이 후보.
- 세션 카드 클릭 동작(터미널 점프 등)은 아직 미구현 (카드 클릭은 내용 펼치기).

## 배포용 .app 번들 빌드

```sh
.venv/bin/pip install py2app "setuptools<70"
mv pyproject.toml pyproject.toml.bak   # py2app이 [project] dependencies를 install_requires로 오인함
PYTHONPATH=src .venv/bin/python setup.py py2app
mv pyproject.toml.bak pyproject.toml
```

- 산출물: `dist/Claude Recents.app` (~31MB, 파이썬 런타임 포함 독립 실행형)
- 메뉴바 전용(LSUIElement), 아이콘 `assets/ClaudeRecents.icns`
- **주의**: GUI 앱은 로케일 env 없이 떠서 기본 인코딩이 ASCII → 한글 트랜스크립트에서
  즉사한다. 모든 파일 I/O에 `encoding="utf-8"` 명시 + Info.plist `LSEnvironment`에
  `PYTHONUTF8=1` 적용됨. launchd로 직접 실행할 땐 plist `EnvironmentVariables`에도 필요.
- 로그인 자동 시작: LaunchAgent가 번들 실행 파일을 직접 가리킴
  (`~/Library/LaunchAgents/com.kiddj.claude-recents.plist`)

빌드 후 개인정보 스크럽 2단계 (기능 영향 없음):
1. Info.plist `PythonExecutable`의 빌드 머신 경로 →
   `@executable_path/../Frameworks/Python.framework/Versions/3.13/Python`으로 치환
2. 번들 내 `.pyc`들의 co_filename에 박힌 `/Users/<사용자명>/` → 같은 길이 문자열로
   바이너리 치환 (예: 사용자명 6글자 → `runner`; marshal 포맷상 길이가 같아야 함)
