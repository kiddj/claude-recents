"""py2app build script.

Usage:  .venv/bin/python setup.py py2app
Output: dist/Claude Recents.app  (self-contained, Python runtime included)
"""

import sys

from setuptools import setup

sys.path.insert(0, "src")

setup(
    name="Claude Recents",
    app=["launcher.py"],
    options={
        "py2app": {
            "packages": ["claude_recents"],
            "iconfile": "assets/ClaudeRecents.icns",
            "plist": {
                "CFBundleName": "Claude Recents",
                "CFBundleDisplayName": "Claude Recents",
                "CFBundleIdentifier": "com.kiddj.claude-recents",
                "CFBundleShortVersionString": "0.1.6",
                "CFBundleVersion": "0.1.6",
                "LSUIElement": True,  # 메뉴바 전용: Dock 아이콘 없음
                # GUI 앱은 로케일 env 없이 떠서 기본 인코딩이 ASCII가 됨 —
                # 한글 트랜스크립트를 읽는 순간 죽는다. UTF-8 강제.
                "LSEnvironment": {"PYTHONUTF8": "1", "LANG": "en_US.UTF-8"},
                "LSMinimumSystemVersion": "12.0",
                "NSHumanReadableCopyright": "© 2026 kiddj",
            },
        }
    },
)
