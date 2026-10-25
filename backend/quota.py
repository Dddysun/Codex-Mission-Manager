"""Service-authoritative quota windows independent of subscription or slot order.

The original primary/secondary slots remain in persisted samples. Semantic
identities use duration so a service slot reorder cannot change a saved anchor.
No missing field is interpreted as an unlimited allowance.
"""
import math
from collections import Counter


def parse_bucket(payload, limit_id, now, stale_grace=90):
    if not isinstance(payload, dict):
        raise ValueError("requested quota bucket missing")
    buckets = payload.get("rateLimitsByLimitId")
    if isinstance(buckets, dict):
        bucket = buckets.get(limit_id)
    else:
        candidate = payload.get("rateLimits")
        bucket = candidate if isinstance(candidate, dict) and candidate.get("limitId", "codex") == limit_id else None
    if not isinstance(bucket, dict) or bucket.get("limitId", limit_id) != limit_id:
        raise ValueError("requested quota bucket missing")
    for flag in (payload.get("ordinaryUsageAllowed"), bucket.get("spendControlReached")):
        if flag is not None and not isinstance(flag, bool):
            raise ValueError("unknown service permission")
    reached_type = bucket.get("rateLimitReachedType")
    if reached_type is not None and not isinstance(reached_type, str):
        raise ValueError("unknown service permission")
    windows = {}
    for slot in ("primary", "secondary"):
        raw = bucket.get(slot)
        if raw is None:
            continue
        if not isinstance(raw, dict):
            raise ValueError("unknown quota window")
        used, minutes, reset = (raw.get(k) for k in ("usedPercent", "windowDurationMins", "resetsAt"))
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
               for x in (used, minutes, reset)):
            raise ValueError("unknown quota window")
        if (not 0 <= used <= 100 or minutes <= 0 or int(minutes) != minutes
                or reset <= 0 or now > reset + stale_grace):
            raise ValueError("invalid or expired quota window")
        windows[slot] = {"used": used, "remaining": round(100 - used, 3),
                         "minutes": int(minutes), "reset": reset}
    service_allowed = payload.get("ordinaryUsageAllowed") is True
    explicit_no_windows = all(slot in bucket and bucket[slot] is None for slot in ("primary", "secondary"))
    quota_state = "metered" if windows else "service_only" if explicit_no_windows and service_allowed else "unknown"
    return {"limit_id": limit_id, "observed_at": now, "windows": windows,
            "quota_state": quota_state, "service_allowed": service_allowed,
            "blocked": bool(reached_type) or bucket.get("spendControlReached") is True
                or payload.get("ordinaryUsageAllowed") is False}


def window_map(sample):
    """Return stable duration identities, retaining slots for ambiguous duplicates."""
    windows = sample.get("windows") or {}
    counts = Counter(w["minutes"] for w in windows.values())
    return {"duration:" + str(int(w["minutes"])) + (":" + slot if counts[w["minutes"]] > 1 else ""): w
            for slot, w in windows.items()}


def _state(sample):
    # V0.2 persisted samples did not have quota_state, but did have valid windows.
    return sample.get("quota_state") or ("metered" if sample.get("windows") else "unknown")


def _weekly(window):
    return window["minutes"] == 10080


def _limiting(window, config):
    return window["remaining"] <= (0 if _weekly(window) else config["pause_remaining"])


def pause_needed(sample, config):
    return bool(sample.get("blocked")) or any(_limiting(w, config) for w in (sample.get("windows") or {}).values())


def classify(sample, config):
    windows = (sample.get("windows") or {}).values()
    if sample.get("blocked") or any(_weekly(w) and w["remaining"] <= 0 for w in windows):
        return "blocked"
    if _state(sample) == "unknown":
        return "unknown"
    metered = [w for w in windows if not _weekly(w)]
    if any(w["remaining"] <= config["pause_remaining"] for w in metered):
        return "low"
    if any(w["remaining"] <= config["warn_remaining"] for w in metered):
        return "warning"
    return "normal"


def quota_usable(sample, config):
    if sample.get("blocked") or _state(sample) == "unknown":
        return False
    if _state(sample) == "service_only":
        return sample.get("service_allowed") is True
    if not sample.get("service_allowed") and config.get("require_service_allowed"):
        return False
    windows = sample.get("windows") or {}
    return bool(windows) and all(w["remaining"] > 0 if _weekly(w)
        else w["remaining"] >= config["resume_remaining"] for w in windows.values())


def recovered(current, previous, config, now):
    if now - current.get("observed_at", 0) > config["max_sample_age_seconds"] or not quota_usable(current, config):
        return False
    old_windows, new_windows = window_map(previous), window_map(current)
    for key, old in old_windows.items():
        new = new_windows.get(key)
        if new is None or new["minutes"] != old["minutes"]:
            return False  # An omitted old allowance is not proof of recovery.
        if _limiting(old, config) and new["reset"] <= old["reset"]:
            return False
    if previous.get("blocked"):
        if not old_windows:
            # A windowless service has no reset timestamp. A fresh, explicit
            # permission transition is the only available recovery evidence.
            return current.get("service_allowed") is True
        if not any(new_windows[k]["reset"] > old["reset"] for k, old in old_windows.items()):
            return False
    return True


def plan_window(sample):
    """Select the actual timed window for a newly armed one-time instruction."""
    windows = window_map(sample)
    if not windows or _state(sample) == "unknown":
        return None
    key = min(windows, key=lambda k: (0 if windows[k]["minutes"] == 300 else
        2 if _weekly(windows[k]) else 1, windows[k]["minutes"], k))
    return key, windows[key]


def next_reset(sample):
    resets = [w["reset"] for w in (sample.get("windows") or {}).values()]
    return min(resets) if resets else None


def sample_summary(sample):
    parts = []
    for window in (sample.get("windows") or {}).values():
        minutes = window["minutes"]
        label = "五小时额度" if minutes == 300 else "周额度" if minutes == 10080 else str(int(minutes)) + "分钟额度"
        parts.append(label + "剩余 " + str(window["remaining"]) + "%")
    if parts:
        return "；".join(parts)
    if sample.get("blocked"):
        return "服务暂不允许使用，等待重新核验"
    return "服务已允许使用；未提供固定额度窗口" if _state(sample) == "service_only" else "额度信息尚未核实"
