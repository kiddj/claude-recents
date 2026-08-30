# claude-recents

> **지금 돌아가는 Claude 세션 일곱 개 — 각각 뭘 하고 있는지 바로 말할 수 있나요?**
> …그럴 리가요. 그걸 머릿속에 담아두지 마세요. 그러라고 만든 앱입니다.
>
> **당신의 유일한 ADHD 치료제.**

**모든 Claude Code 세션이 지금 무엇을 하고 있는지 — 이 맥에서도, 원격 서버에서도 — 실시간으로 보여주는 macOS 메뉴바 앱.**

Claude Code 세션을 동시에 여러 개 돌리다 보면(로컬 몇 개, SSH 너머 GPU 서버에 몇 개) 꼭 이런 순간이 옵니다: *그 세션이 뭘 하고 있었더라?* claude-recents는 메뉴바에 ✳ 아이콘과 작업 중 세션 수를 띄우고, 클릭 한 번이면 모든 세션의 최근 요청·최근 답변·지금 이 순간 하는 일이 패널로 펼쳐집니다.

[English documentation](README.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/kiddj/claude-recents/main/docs/screenshot-dark.png" width="460" alt="claude-recents 패널 (다크 모드)">
</p>

## 기능

- **실시간 세션 목록** — 이 맥의 모든 Claude Code 세션 + 등록한 원격 서버의 세션. 머신별 구역으로 나뉘고, 내가 요청한 최신 순으로 정렬됩니다.
- **채팅형 카드** — 세션마다 최근 요청과 Claude의 최근 답변이 말풍선으로 표시됩니다 (줄바꿈 그대로). 카드를 클릭하면 전문이 펼쳐집니다. 자율 루프처럼 답변이 여러 턴 쌓였으면 "⋯ N earlier replies" 표시로 알려줍니다 — 카드를 길게 만들지 않고요.
- **지금 하는 일** — 작업 중인 세션은 실시간 활동("Running command · pytest tests/auth -x", "Editing file · …")과 상태를 보여줍니다: 🟢 작업 중, 🟠 승인 대기, ⚪ 유휴.
- **SSH 원격 서버** — `~/.ssh/config`의 호스트를 두 번의 클릭으로 추가. 서버에는 아무것도 설치하지 않습니다: 폴링마다 작은 스크립트를 `ssh`로 흘려보내 서버 쪽에서 파싱합니다. 서버별 연결 상태(연결됨/연결 중/실패)가 항상 표시됩니다.
- **멀티 계정 인식** — 다른 Claude 계정의 세션(별도 `CLAUDE_CONFIG_DIR` 프로필, [claude-swap](https://github.com/realiti4/claude-swap) 프로필)을 자동으로 찾아 계정 배지를 붙입니다.
- **거슬리지 않는 UI** — 플랫하고 네이티브한 디자인, 라이트/다크 테마, 서버 구역 드래그 재정렬, 오래된 세션 접이식 그룹("Last week" / "Older"). 메뉴바 아이콘은 `✳ 작업중/전체`를 한눈에 보여줍니다.
- **프라이버시 우선 설계** — 모든 데이터는 로컬 디스크 또는 직접 설정한 SSH 연결에서만 읽습니다. 어디로도 전송하지 않습니다.

## 설치

**macOS 12+**, **Python 3.12+** 필요.

```sh
uv tool install claude-recents      # 권장
# 또는: pipx install claude-recents
# 또는: pip install claude-recents

claude-recents                       # 메뉴바에 ✳ 등장
```

### 로그인 시 자동 시작 (선택)

메뉴바 ✳ 아이콘 **우클릭 → Start at Login**. 끝입니다 — 앱이 LaunchAgent(`~/Library/LaunchAgents/com.kiddj.claude-recents.plist`)를 직접 등록하고 다음 로그인부터 자동 시작됩니다. 다시 누르면 해제됩니다.

> **팁:** tmux 데몬이나 SSH 셸에서 직접 실행하면 프로세스는 뜨지만 아이콘이 안 보입니다 — 메뉴바 아이템은 GUI 로그인 세션이 필요하거든요. 일반 실행(또는 Start at Login)이 올바른 컨텍스트를 보장합니다.

## 사용법

- ✳ 아이콘 **클릭** → 패널 열림. 다시 클릭(또는 바깥 클릭) → 닫힘.
- **카드 클릭** → 요청/답변 전문과 작업 디렉토리가 펼쳐집니다.
- **서버 헤더 클릭** → 그 머신의 세션 접기/펼치기.
- **서버 헤더 드래그** → 머신 순서 변경 (파란 삽입 라인이 들어갈 자리를 표시).
- 패널 맨 아래 **Add Server** → `~/.ssh/config`의 호스트를 골라 Add.
- 서버 헤더의 **연결 해제 아이콘** → "Disconnect / Cancel" 2단 확인으로 제거.
- **☀ / ☾** → 라이트/다크 테마 (기본은 시스템 따라가기).
- 메뉴바 아이콘 **우클릭** → 종료.

### 원격 서버 추가하기

원격 모니터링에는 **비밀번호 없는 (키 기반) SSH**가 필요합니다 — 앱이 `ssh -o BatchMode=yes`로 폴링하므로 비밀번호 프롬프트는 동작할 수 없습니다. 서버당 한 번만 설정하면 됩니다:

```sh
ssh-copy-id my-server
```

서버에는 PATH에 `python3`만 있으면 됩니다 (현대 리눅스는 다 있습니다). 인증에 실패하면 패널에 해결 방법과 함께 그대로 표시됩니다.

## 동작 원리

Claude Code는 세션별 상태를 디스크에 기록합니다. claude-recents는 그걸 읽기만 합니다:

| 보이는 것 | 출처 |
|---|---|
| 라이브 세션, 작업중/유휴/대기 | `~/.claude/sessions/*.json` (+ 프로세스 생존 확인) |
| 최근 요청, 최근 답변, 현재 도구 활동 | `~/.claude/projects/…`의 세션 트랜스크립트 |
| 계정 배지 | `~/.claude.json` |
| 원격 세션 | 서버의 같은 파일들 — `ssh <host> python3 -`로 자체 완결 스크립트를 보내 서버 쪽에서 파싱, 압축된 결과만 수신 |

로컬은 2초마다 갱신, 원격은 패널이 열려 있으면 10초 / 닫혀 있으면 60초마다 폴링합니다.

> **참고:** 세션 상태 파일은 Claude Code의 *문서화되지 않은* 내부 포맷입니다 (v2.1.x 기준 검증). 향후 업데이트로 바뀔 수 있으며, 파서는 방어적으로 작성되어 있지만 깨지면 Claude Code 버전과 함께 이슈를 열어주세요.

## 설정

UI에서 바꾸는 모든 것(서버, 구역 순서, 접힘 상태, 테마)은 `~/.config/claude-recents/config.json`에 저장됩니다. 직접 편집해도 됩니다:

```jsonc
{
  "ssh_hosts": ["gpu-server", "staging-box"],   // 모니터링할 원격 머신
  "host_order": ["gpu-server", ""],             // 구역 순서 ("" = 이 맥)
  "host_collapsed": [],                          // 접힌 구역
  "theme": "auto",                               // "auto" | "light" | "dark"
  "extra_config_dirs": ["~/.claude-work"],       // 추가 CLAUDE_CONFIG_DIR 프로필
  "panel_width": 460,                            // 선택, 기본값 표시
  "panel_height": 900                            // 선택, 기본은 화면 높이
}
```

## 프라이버시

- 모든 데이터는 로컬 디스크 또는 **직접** 설정한 SSH 연결에서만 읽습니다.
- 앱 자체의 네트워크 요청은 없습니다 — 텔레메트리 없음, 계정 없음, 클라우드 없음.
- 요청/답변은 표시만 할 뿐 어디에도 새로 저장하지 않습니다.

## 제약

- **macOS 전용** (PyObjC 기반 메뉴바 앱).
- 접근 가능한 머신의 세션만 보입니다 — Claude 계정의 클라우드/웹 세션을 나열하는 공개 API가 없어 표시할 수 없습니다.
- 세션 제목은 Claude Code의 로컬 세션 이름 기준이라, Claude 모바일/데스크톱 앱에 보이는 제목(서버에서 생성, 로컬에 없음)과 다를 수 있습니다.

## 개발

```sh
git clone https://github.com/kiddj/claude-recents
cd claude-recents
python3 -m venv .venv && .venv/bin/pip install pyobjc-framework-Cocoa pyobjc-framework-WebKit
PYTHONPATH=src .venv/bin/python -m claude_recents.app
```

### 배포용 .app 번들 빌드 (py2app)

대상 머신에 Python이 없어도 되는 독립 실행형 번들:

```sh
.venv/bin/pip install py2app "setuptools<70"
mv pyproject.toml pyproject.toml.bak   # py2app이 [project] dependencies를 install_requires로 오인함
PYTHONPATH=src .venv/bin/python setup.py py2app
mv pyproject.toml.bak pyproject.toml
```

- 산출물: `dist/Claude Recents.app` (~31MB), 메뉴바 전용(LSUIElement)
- **UTF-8 주의**: GUI 앱은 로케일 env 없이 떠서 기본 인코딩이 ASCII가 됩니다. 소스의 모든 파일 I/O에 `encoding="utf-8"`이 명시돼 있고 Info.plist `LSEnvironment`에 `PYTHONUTF8=1`이 들어갑니다. launchd로 직접 실행할 땐 plist `EnvironmentVariables`에도 필요합니다.
- **빌드 후 개인정보 스크럽 2단계** (기능 영향 없음):
  1. Info.plist `PythonExecutable`의 빌드 머신 경로 → `@executable_path/../Frameworks/Python.framework/Versions/3.13/Python`으로 치환
  2. 번들 내 `.pyc`들의 co_filename에 박힌 `/Users/<사용자명>/` → 같은 길이 문자열로 바이너리 치환 (marshal 포맷상 길이가 같아야 함)

## 라이선스

[MIT](LICENSE) © 2026 kiddj
