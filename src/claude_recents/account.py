"""Read the logged-in Claude account from ~/.claude.json (oauthAccount)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CLAUDE_JSON = Path.home() / ".claude.json"

_PLAN_LABELS = {
    "claude_max": "Max",
    "claude_pro": "Pro",
    "claude_team": "Team",
    "claude_enterprise": "Enterprise",
}


@dataclass
class Account:
    display_name: str = ""
    email: str = ""
    plan: str = ""

    @property
    def label(self) -> str:
        parts = [p for p in (self.display_name or self.email, self.plan) if p]
        return " · ".join(parts) if parts else "Claude 계정 정보 없음"


def _identity_file(config_dir: Path | None) -> Path:
    # With CLAUDE_CONFIG_DIR=<dir>, Claude Code keeps .claude.json inside
    # <dir>; the default ~/.claude dir pairs with ~/.claude.json.
    if config_dir is None or config_dir == Path.home() / ".claude":
        return CLAUDE_JSON
    return config_dir / ".claude.json"


_account_cache: dict[Path, str] = {}


def account_for_config_dir(config_dir: Path) -> str:
    """Short label (display name or email) of the account a config dir
    belongs to. Cached; empty string when unknown."""
    if config_dir not in _account_cache:
        acct = current_account(config_dir)
        _account_cache[config_dir] = acct.display_name or acct.email
    return _account_cache[config_dir]


def current_account(config_dir: Path | None = None) -> Account:
    try:
        data = json.loads(_identity_file(config_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Account()
    acct = data.get("oauthAccount") or {}
    plan = _PLAN_LABELS.get(acct.get("organizationType", ""), "")
    tier = acct.get("organizationRateLimitTier") or ""
    if plan and tier.rsplit("_", 1)[-1].endswith("x"):
        plan = f"{plan} {tier.rsplit('_', 1)[-1]}"
    return Account(
        display_name=acct.get("displayName", ""),
        email=acct.get("emailAddress", ""),
        plan=plan,
    )
