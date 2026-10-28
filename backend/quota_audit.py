"""Quota-only observations, independent of task control and notifications.

First observations/account switches only establish a baseline. A restoration is
an observed increase of >=5 percentage points, or a smaller positive increase
with a credible deadline advance. Crossing the old deadline with a complete
period advance also records a new cycle when new consumption masks any increase.
Deadline jitter tolerance is 2% of the window, bounded to 5..60 seconds. Due
means the old deadline was actually reached; the preceding tolerance band is
unattributed. Gaps
over min(6 hours, one window + tolerance) and changed/ambiguous window identities
never receive an independent/scheduled attribution. Credit attribution is an
observation, never proof of a human action or an official campaign: counts must
be present and inventories comparable. A complete, non-expiring available-ID
removal plus a matching count decrease can support observed consumption. It
cannot do so when grants, expirations, caps, field loss or counts disagree.
No credit is consumed by this module.

Credit metadata changes are sticky for 120 seconds, including across restarts:
an adjacent stable count during that period cannot establish an official source.
This module logs immediately, so a credit change first observed AFTER a quota
event cannot retroactively establish that event's cause. All categories are
observational inferences; official_reason and consumption confirmation stay null
and false respectively.
"""
import hashlib
import json
import math
import time
from collections import Counter

MIN_INCREASE = 5
MAX_GAP_SECONDS = 6 * 60 * 60
CREDIT_CAP = 32
CREDIT_CHANGE_SECONDS = 120
ACTIVE_KEY = 'quota_audit_active_v1'
ANCHOR_PREFIX = 'quota_audit_anchor_v1:'


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _credits(value):
    value = value if isinstance(value, dict) else {}
    count = value.get('available_count')
    known = value.get('supported') is True and type(count) is int and count >= 0
    rows = value.get('credits')
    records = []
    for row in rows[:CREDIT_CAP] if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        record = {}
        for key in ('id', 'status', 'resetType'):
            if isinstance(row.get(key), str) and len(row[key]) <= 160:
                record[key] = row[key]
        for key in ('grantedAt', 'expiresAt'):
            if key in row and (row[key] is None or _number(row[key])):
                record[key] = row[key]
        records.append(record)
    return {'supported': known, 'available_count': count if known else None,
            'credits': records, 'capped': isinstance(rows, list) and len(rows) >= CREDIT_CAP}


def _sample(sample, config, now):
    if not isinstance(sample, dict):
        return None
    scope, limit, observed = (sample.get(k) for k in ('scope', 'limit_id', 'observed_at'))
    if not isinstance(scope, str) or not 0 < len(scope) <= 256 or not isinstance(limit, str) or not 0 < len(limit) <= 128:
        return None
    if config.get('limit_id', limit) != limit or not _number(observed):
        return None
    age = config.get('max_sample_age_seconds', 90)
    if not _number(age) or age < 0 or observed > now + 5 or now - observed > age:
        return None
    raw = sample.get('windows')
    if not isinstance(raw, dict) or len(raw) > 8:
        return None
    windows = []
    for row in raw.values():
        if not isinstance(row, dict):
            return None
        minutes, remaining, reset = (row.get(k) for k in ('minutes', 'remaining', 'reset'))
        if (type(minutes) is not int or minutes <= 0 or not _number(remaining) or not 0 <= remaining <= 100
                or not _number(reset) or reset <= 0):
            return None
        windows.append({'minutes': minutes, 'remaining': remaining, 'reset': reset})
    counts = Counter(row['minutes'] for row in windows)
    return {'scope': scope, 'limit_id': limit, 'observed_at': observed,
            'windows': {str(row['minutes']): row for row in windows if counts[row['minutes']] == 1},
            'ambiguous_windows': any(value > 1 for value in counts.values()),
            'reset_credits': _credits(sample.get('reset_credits'))}


def _inventory(snapshot):
    credits = snapshot['reset_credits']
    rows, available = {}, set()
    complete = credits['supported'] and not credits['capped']
    for row in credits['credits']:
        identity, status = row.get('id'), row.get('status')
        if not identity or identity in rows or status not in ('available', 'consumed', 'expired'):
            complete = False
            continue
        rows[identity] = row
        if status == 'available':
            available.add(identity)
            expiry = row.get('expiresAt')
            if 'expiresAt' not in row or (expiry is not None and expiry <= snapshot['observed_at']):
                complete = False
    return rows, available, bool(complete and len(available) == credits['available_count'])


def _credit_evidence(previous, current):
    before, after = previous['reset_credits'], current['reset_credits']
    old_count, new_count = before['available_count'], after['available_count']
    delta = new_count - old_count if old_count is not None and new_count is not None else None
    old, old_available, old_complete = _inventory(previous)
    new, new_available, new_complete = _inventory(current)
    start, end = previous['observed_at'], current['observed_at']
    expired, consumed, granted, removed = set(), set(), set(), set()
    lost_fields = False
    ambiguous = False
    for identity in old_available:
        old_row, new_row = old[identity], new.get(identity)
        expiry = old_row.get('expiresAt')
        has_expired = _number(expiry) and start < expiry <= end
        if has_expired:
            expired.add(identity)
        if new_row:
            for key in ('expiresAt', 'grantedAt', 'resetType'):
                if key in old_row and (key not in new_row or old_row[key] != new_row[key]):
                    lost_fields = True
            if new_row.get('status') == 'consumed' and not has_expired:
                consumed.add(identity)
            elif new_row.get('status') == 'expired' and not has_expired:
                ambiguous = True
        elif not has_expired:
            if 'expiresAt' in old_row and (expiry is None or expiry > end + 60):
                removed.add(identity)
            else:
                ambiguous = True
    for identity, row in new.items():
        if identity in old:
            continue
        when = row.get('grantedAt')
        if not _number(when) or not start < when <= end:
            ambiguous = True
            continue
        granted.add(identity)
        if row.get('status') == 'consumed':
            consumed.add(identity)
        elif row.get('status') == 'expired':
            expiry = row.get('expiresAt')
            if _number(expiry) and when <= expiry <= end:
                expired.add(identity)
            else:
                ambiguous = True
    complete = old_complete and new_complete and not lost_fields and not ambiguous
    reconciled = complete and delta == len(granted) - len(consumed) - len(expired) - len(removed)
    inferred_removal = bool(reconciled and removed and delta < 0 and not granted and not expired)
    observed = bool(reconciled and consumed and not removed) or inferred_removal
    stable = bool(reconciled and delta == 0 and not consumed and not expired and not granted and not removed
                  and old_available == new_available)
    return {'previous_available_count': old_count, 'available_count': new_count, 'delta': delta,
            'consumption_evidence': {'observed': observed, 'confirmed': False,
                'basis': ('available_inventory_removed_and_count_decreased' if inferred_removal else
                          'observed_status_and_count_reconciliation' if observed else 'no_confirmed_consumption'),
                'consumed_ids': sorted(consumed), 'expired_ids': sorted(expired), 'newly_granted_ids': sorted(granted),
                'removed_nonexpired_available_ids': sorted(removed),
                'inventory_complete': bool(complete), 'counts_reconciled': bool(reconciled),
                'lists_capped': before['capped'] or after['capped'], 'fields_changed_or_lost': lost_fields},
            'stable_without_observed_consumption': stable}


def _changes(previous, current):
    changed = []
    gap = current['observed_at'] - previous['observed_at']
    same_windows = (set(previous['windows']) == set(current['windows'])
                    and not previous['ambiguous_windows'] and not current['ambiguous_windows'])
    for identity in sorted(set(previous['windows']) & set(current['windows']), key=int):
        old, new = previous['windows'][identity], current['windows'][identity]
        seconds = old['minutes'] * 60
        tolerance = min(60, max(5, seconds * .02))
        increase = new['remaining'] - old['remaining']
        advance = new['reset'] - old['reset']
        due = current['observed_at'] >= old['reset']
        early = current['observed_at'] < old['reset'] - tolerance
        unused = old['remaining'] == 100 and new['remaining'] == 100
        credible_advance = advance > tolerance
        cycle = (previous['observed_at'] < old['reset'] <= current['observed_at']
                 and abs(advance - seconds) <= 2 * tolerance)
        if not (increase >= MIN_INCREASE or (increase > 0 and credible_advance)
                or (unused and due and credible_advance) or cycle):
            continue
        recent = gap <= min(MAX_GAP_SECONDS, seconds + tolerance)
        if not same_windows:
            pattern = 'window_set_changed'
        elif not recent:
            pattern = 'observation_gap_too_long'
        elif cycle:
            pattern = 'scheduled_window_rollover_observed'
        elif early and increase >= MIN_INCREASE:
            pattern = 'balance_increased_before_previous_deadline'
        elif increase < MIN_INCREASE:
            pattern = 'small_balance_increase_with_deadline_advance'
        else:
            pattern = 'balance_increased_without_scheduled_rollover_evidence'
        changed.append({'minutes': old['minutes'], 'previous_remaining': old['remaining'],
            'remaining': new['remaining'], 'previous_reset': old['reset'], 'reset': new['reset'],
            'remaining_delta': increase, 'net_balance_increased': increase > 0,
            'classification': 'unattributed', 'classification_basis': pattern})
    return changed


def _detail(previous, current):
    windows = _changes(previous, current)
    if not windows:
        return None
    credits = _credit_evidence(previous, current)
    changed_at = current.get('credit_change_observed_at')
    recent_credit_change = (_number(changed_at)
                            and 0 <= current['observed_at'] - changed_at <= CREDIT_CHANGE_SECONDS)
    credits['consumption_evidence']['recent_metadata_change'] = recent_credit_change
    credits['consumption_evidence']['metadata_changed_at'] = changed_at if _number(changed_at) else None
    if recent_credit_change:
        credits['stable_without_observed_consumption'] = False
    for window in windows:
        pattern = window['classification_basis']
        eligible = pattern not in ('window_set_changed', 'observation_gap_too_long')
        if credits['consumption_evidence']['observed'] and eligible and window['net_balance_increased']:
            window['classification'] = 'user_reset'
        elif credits['stable_without_observed_consumption']:
            if pattern == 'scheduled_window_rollover_observed':
                window['classification'] = 'official_scheduled_reset'
            elif pattern == 'balance_increased_before_previous_deadline':
                window['classification'] = 'official_independent_reset'
    categories = {row['classification'] for row in windows}
    category = next(iter(categories)) if len(categories) == 1 else 'unattributed'
    inferred = credits['consumption_evidence']['basis'] == 'available_inventory_removed_and_count_decreased'
    basis = {'user_reset': ('available_credit_decreased_with_balance_restoration' if inferred else
                           'observed_credit_consumption_correlated_with_balance_restoration'),
             'official_scheduled_reset': 'observed_due_window_rollover_and_stable_credit_inventory',
             'official_independent_reset': 'observed_early_balance_increase_and_stable_credit_inventory'}
    unknown = ('reset_credit_statistics_missing' if credits['delta'] is None
               else 'recent_reset_credit_metadata_changed' if recent_credit_change
               else 'mixed_or_insufficient_observation_evidence')
    return {'category': category, 'scope': current['scope'], 'limit_id': current['limit_id'],
            'source': 'account/rateLimits/read', 'official_reason': None,
            'previous_observed_at': previous['observed_at'], 'observed_at': current['observed_at'],
            'classification_basis': basis.get(category, unknown), 'reset_credits': credits, 'windows': windows}


def observe_quota(store, sample, config):
    """Atomically advance a namespace baseline and append at most one event.

    Returns the inserted detail or None. Does not inspect last_report, notices,
    mode, tasks or plans; does not mutate the caller's sample or permissions.
    Transaction failure rolls back BOTH the baseline and event, so retry is safe.
    """
    current = _sample(sample, config, time.time())
    if current is None:
        return None
    if store.db.in_transaction:
        raise RuntimeError('Quota audit requires a committed caller transaction')
    namespace = hashlib.sha256((current['scope'] + '\0' + current['limit_id']).encode()).hexdigest()
    key = ANCHOR_PREFIX + namespace
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        active = store.get(ACTIVE_KEY, {})
        if (isinstance(active, dict) and _number(active.get('observed_at'))
                and current['observed_at'] <= active['observed_at']):
            return None
        previous = store.get(key)
        same_active = isinstance(active, dict) and active.get('namespace') == namespace
        comparable = (same_active and isinstance(previous, dict)
                  and previous.get('scope') == current['scope'] and previous.get('limit_id') == current['limit_id']
                  and previous.get('observed_at', current['observed_at']) < current['observed_at'])
        if comparable:
            if previous.get('reset_credits') != current['reset_credits']:
                current['credit_change_observed_at'] = current['observed_at']
            elif _number(previous.get('credit_change_observed_at')):
                current['credit_change_observed_at'] = previous['credit_change_observed_at']
        detail = _detail(previous, current) if comparable else None
        store.db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)', (key, json.dumps(current)))
        store.db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)', (ACTIVE_KEY, json.dumps(
            {'namespace': namespace, 'observed_at': current['observed_at']})))
        if detail is not None:
            store.db.execute('INSERT INTO events(created,thread_id,state,detail) VALUES(?,NULL,?,?)',
                             (current['observed_at'], 'quota_restored', json.dumps(detail)))
        return detail
