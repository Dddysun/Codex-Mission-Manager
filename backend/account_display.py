"""Allowlisted public account metadata and quota windows for the loopback UI.

Local ID-token claims supplement display fields only, never authentication or
control decisions. Tokens and arbitrary claims must never leave this module.
"""
import base64
import json
from pathlib import Path
from urllib.parse import urlparse

from quota import parse_bucket, window_map, plan_window


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


def display_snapshot(account_response, quota_response, limit_id, observed_at, auth_path=None):
    account_response = account_response if isinstance(account_response, dict) else {}
    quota_response = quota_response if isinstance(quota_response, dict) else {}
    account = (account_response or {}).get("account") or {}
    account = account if isinstance(account, dict) else {}
    local = local_profile(account, auth_path)
    buckets = quota_response.get("rateLimitsByLimitId")
    raw = (buckets.get(limit_id) if isinstance(buckets, dict) else quota_response.get("rateLimits")) or {}
    if not isinstance(raw, dict) or raw.get("limitId", limit_id) != limit_id:
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
    quota_windows = []
    try:
        sample = parse_bucket(quota_response, limit_id, observed_at)
    except (ValueError, TypeError, AttributeError):
        sample = {"windows": {}, "quota_state": "unknown", "service_allowed": False,
                  "blocked": bool(raw.get("rateLimitReachedType") or raw.get("spendControlReached"))
                    or quota_response.get("ordinaryUsageAllowed") is False}
    # The control parser and display share duration/validity decisions. A plan
    # label never invents percentages or permission to execute.
    for identifier, raw_window in sorted(window_map(sample).items(), key=lambda entry: (entry[1]["minutes"], entry[0])):
        value = {k: raw_window[k] for k in ("remaining", "minutes", "reset")}
        kind = "five_hour" if value["minutes"] == 300 else "weekly" if value["minutes"] == 10080 else "custom"
        quota_windows.append(dict(value, id=identifier, kind=kind))
        if kind in windows and windows[kind] is None:
            windows[kind] = value
    selected = plan_window(sample)
    scheduling_window = next((w for w in quota_windows if selected and w["id"] == selected[0]), None)
    return {"account": profile, "windows": windows, "observed_at": observed_at,
            "quota_windows": quota_windows, "quota_state": sample["quota_state"],
            "service_allowed": sample.get("service_allowed") is True,
            "blocked": sample.get("blocked") is True,
            "scheduling_available": bool(quota_windows),
            "scheduling_window": scheduling_window,
            "limit_id": limit_id, "limit_name": text(raw.get("limitName")),
            "source": "account/rateLimits/read"}
