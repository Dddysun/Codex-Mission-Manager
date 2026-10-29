"""Service-authoritative quota windows independent of subscription or slot order.

The original primary/secondary slots remain in persisted samples. Semantic
identities use duration so a service slot reorder cannot change a saved anchor.
No missing field is interpreted as an unlimited allowance.
"""
import math
from collections import Counter


def finite_number(value):
    """Reject booleans, non-numbers and integers too large for float consumers."""
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def reset_credits(payload):
    """Public, bounded metadata only. This function never redeems a credit."""
    raw = payload.get('rateLimitResetCredits') if isinstance(payload, dict) else None
    result = {'supported': isinstance(raw, dict), 'available_count': None, 'credits': []}
    if not isinstance(raw, dict):
        return result
    count = raw.get('availableCount')
    if type(count) is int and 0 <= count <= 1000000:
        result['available_count'] = count
    credits = raw.get('credits')
    for item in credits[:32] if isinstance(credits, list) else []:
        if not isinstance(item, dict):
            continue
        credit = {}
        for key, limit in (('id', 160), ('resetType', 80), ('status', 80), ('title', 240), ('description', 1000)):
            value = item.get(key)
            if isinstance(value, str):
                credit[key] = ''.join(c for c in value if c >= ' ' or c in '\n\t')[:limit]
            elif value is None and key in ('title', 'description'):
                credit[key] = None
        for key in ('grantedAt', 'expiresAt'):
            value = item.get(key)
            if finite_number(value) and value >= 0:
                credit[key] = value
            elif value is None and key == 'expiresAt':
                credit[key] = None
        if credit:
            result['credits'].append(credit)
    return result


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
        if any(not finite_number(x) for x in (used, minutes, reset)):
            raise ValueError("unknown quota window")
        if (not 0 <= used <= 100 or minutes <= 0 or int(minutes) != minutes
                or reset <= 0 or now > reset + stale_grace):
            raise ValueError("invalid or expired quota window")
        windows[slot] = {"used": used, "remaining": round(100 - used, 3),
                         "minutes": int(minutes), "reset": reset}
    service_allowed = payload.get("ordinaryUsageAllowed") is True
    explicit_no_windows = all(slot in bucket and bucket[slot] is None for slot in ("primary", "secondary"))
    quota_state = "metered" if windows else "service_only" if explicit_no_windows and service_allowed else "unknown"
    plan_type = bucket.get('planType')
    return {"limit_id": limit_id, "observed_at": now, "windows": windows,
            "plan_type": plan_type[:80] if isinstance(plan_type, str) else None,
            "quota_state": quota_state, "service_allowed": service_allowed,
            "reset_credits": reset_credits(payload),
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


MONITOR_WINDOWS = {'auto', 'five_hour', 'weekly'}


def monitoring_state(sample, config=None):
    """Choose an actual duration, never a primary/secondary service slot."""
    config = config or {}
    requested = config.get('monitor_window', 'auto')
    if not isinstance(requested, str) or requested not in MONITOR_WINDOWS:
        requested = 'unavailable'
    windows = window_map(sample)
    pro = str(sample.get('plan_type') or '').lower().split('_')[0] == 'pro'
    five = not pro and any(w['minutes'] == 300 for w in windows.values())
    weekly = any(w['minutes'] == 10080 for w in windows.values())
    candidates = [(key, window) for key, window in windows.items()
                  if not (pro and window['minutes'] == 300)]
    if requested != 'auto':
        duration = {'five_hour': 300, 'weekly': 10080}.get(requested)
        candidates = [(key, window) for key, window in candidates if window['minutes'] == duration]
    selected = min(candidates, key=lambda pair: (0 if pair[1]['minutes'] == 300 else
        2 if _weekly(pair[1]) else 1, pair[1]['minutes'], pair[0])) if candidates else None
    if _state(sample) == 'unknown':
        selected = None
    minutes = selected[1]['minutes'] if selected else None
    return {'requested_window': requested,
            'effective_window': 'five_hour' if minutes == 300 else 'weekly' if minutes == 10080 else 'custom' if minutes else None,
            'minutes': minutes, 'window_key': selected[0] if selected else None,
            'five_hour_available': five, 'weekly_available': weekly,
            'state': 'ready' if selected else 'service_only' if _state(sample) == 'service_only' else 'unavailable'}


def _limiting(window, config, selected_minutes):
    return window['remaining'] <= (config['pause_remaining'] if window['minutes'] == selected_minutes else 0)


def pause_needed(sample, config):
    selected_minutes = monitoring_state(sample, config)['minutes']
    return bool(sample.get("blocked")) or any(_limiting(w, config, selected_minutes)
        for w in (sample.get("windows") or {}).values())


def classify(sample, config):
    windows = (sample.get("windows") or {}).values()
    if sample.get("blocked") or any(w["remaining"] <= 0 for w in windows):
        return "blocked"
    monitoring = monitoring_state(sample, config)
    if _state(sample) == "unknown" or monitoring['state'] == 'unavailable':
        return "unknown"
    metered = [w for w in windows if w['minutes'] == monitoring['minutes']]
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
    monitoring = monitoring_state(sample, config)
    return monitoring['state'] == 'ready' and all(
        w['remaining'] >= config['resume_remaining'] if w['minutes'] == monitoring['minutes']
        else w['remaining'] > 0 for w in windows.values())


def restoration_reason(current, previous, config, now):
    if now - current.get("observed_at", 0) > config["max_sample_age_seconds"] or not quota_usable(current, config):
        return None
    if current.get('limit_id', config.get('limit_id')) != previous.get('limit_id', config.get('limit_id')):
        return None
    if current.get('scope') and previous.get('scope') and current['scope'] != previous['scope']:
        return None
    old_windows, new_windows = window_map(previous), window_map(current)
    early = False
    selected_minutes = monitoring_state(previous, config)['minutes']
    for key, old in old_windows.items():
        new = new_windows.get(key)
        if new is None or new["minutes"] != old["minutes"]:
            return None  # An omitted old allowance is not proof of recovery.
        if _limiting(old, config, selected_minutes) and new["reset"] <= old["reset"]:
            if new['remaining'] - old['remaining'] < max(5, config['resume_remaining'] - config['pause_remaining']):
                return None
            early = True
    if previous.get("blocked"):
        if not old_windows:
            # A windowless service has no reset timestamp. A fresh, explicit
            # permission transition is the only available recovery evidence.
            return 'service_permission_restored' if current.get("service_allowed") is True else None
        if not any(new_windows[k]["reset"] > old["reset"] for k, old in old_windows.items()):
            if not any(new_windows[k]['remaining'] - old['remaining'] >= 20 for k, old in old_windows.items()):
                return None
            early = True
    if not old_windows:
        return None
    advanced = any(new_windows[k]['reset'] > old['reset'] for k, old in old_windows.items())
    return 'balance_restored' if early else 'window_advanced' if advanced else None


def recovered(current, previous, config, now):
    return restoration_reason(current, previous, config, now) is not None


def restoration_details(current, previous_windows, reason):
    windows = window_map(current)
    return {'kind': reason, 'source': 'account/rateLimits/read', 'official_reason': None,
            'observed_at': current.get('observed_at'), 'windows': [
                {'minutes': old['minutes'], 'previous_remaining': old['remaining'],
                 'remaining': windows[key]['remaining'], 'previous_reset': old['reset'],
                 'reset': windows[key]['reset']}
                for key, old in previous_windows.items() if key in windows]}


def plan_window(sample, config=None):
    """Select the actual timed window for a newly armed one-time instruction."""
    windows = window_map(sample)
    if not windows or _state(sample) == "unknown":
        return None
    selected = monitoring_state(sample, config)['window_key']
    return (selected, windows[selected]) if selected else None


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
