"""Allowlisted public account metadata and quota windows for the loopback UI.

Local ID-token claims supplement display fields only, never authentication or
control decisions. Tokens and arbitrary claims must never leave this module.
"""
import base64
import json
import math
from pathlib import Path
from urllib.parse import urlparse


def text(value, limit=200):
    return value[:limit] if isinstance(value, str) else None


def local_profile(account, auth_path=None):
    if account.get("type") != "chatgpt":
        return {}
    try:
        auth = json.loads(Path(auth_path or Path.home() / ".codex/auth.json").read_text())
        tokens = auth.get("tokens") or {}
        segment = tokens.get("id_token", "").split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
        # A stale token from another login must not supply a name, ID or image.
        if not account.get("email") or claims.get("email") != account["email"]:
            return {}
        namespace = claims.get("https://api.openai.com/auth") or {}
        return {"id": text(tokens.get("account_id") or namespace.get("chatgpt_account_id")),
                "name": text(claims.get("name")), "picture": text(claims.get("picture"), 2000)}
    except (OSError, ValueError, TypeError, IndexError, AttributeError):
        return {}


def avatar_url(value):
    if not isinstance(value, str) or len(value) > 2000:
        return None
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    return value


def window(raw):
    if not isinstance(raw, dict):
        return None
    used, minutes, reset = (raw.get(k) for k in ("usedPercent", "windowDurationMins", "resetsAt"))
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in (used, minutes, reset)):
        return None
    if not 0 <= used <= 100 or minutes <= 0 or reset <= 0:
        return None
    return {"remaining": round(100 - used, 3), "minutes": minutes, "reset": reset}


def display_snapshot(account_response, quota_response, limit_id, observed_at, auth_path=None):
    account = (account_response or {}).get("account") or {}
    local = local_profile(account, auth_path)
    buckets = quota_response.get("rateLimitsByLimitId")
    raw = (buckets.get(limit_id) if isinstance(buckets, dict) else quota_response.get("rateLimits")) or {}
    if raw.get("limitId", limit_id) != limit_id:
        raw = {}
    plan = text(raw.get("planType") or account.get("planType"), 80)
    profile = None
    if account:
        profile = {"id": text(account.get("id")) or local.get("id"),
                   "name": text(account.get("name")) or local.get("name"),
                   "email": text(account.get("email")), "type": text(account.get("type"), 80),
                   "plan_type": plan,
                   "avatar_url": avatar_url(account.get("picture") or account.get("avatarUrl") or local.get("picture"))}
    windows = {"five_hour": None, "weekly": None}
    # Window duration, not subscription name or primary/secondary position,
    # determines which meter a quota belongs to. Null is never unlimited.
    for key in ("primary", "secondary"):
        value = window(raw.get(key))
        if value:
            if value["minutes"] == 300:
                windows["five_hour"] = value
            elif value["minutes"] == 10080:
                windows["weekly"] = value
    return {"account": profile, "windows": windows, "observed_at": observed_at,
            "limit_id": limit_id, "source": "account/rateLimits/read"}
