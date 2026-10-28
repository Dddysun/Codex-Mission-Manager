"""Account-independent, revisioned local operating preferences."""
import json
import time
from event_origin import origin_detail

BOUNDS = {
    'pause_remaining': {'min': 1, 'max': 50, 'default': 10},
    'resume_remaining': {'min': 5, 'max': 95, 'default': 20},
    'poll_seconds': {'min': 10, 'max': 300, 'default': 30},
    'near_limit_poll_seconds': {'min': 5, 'max': 60, 'default': 10},
    'recovery_confirm_seconds': {'min': 3, 'max': 60, 'default': 5},
    'ui_poll_seconds': {'min': 2, 'max': 30, 'default': 5},
}
CONSTRAINTS = {'resume_pause_gap': 5, 'near_limit_not_above_normal': True,
               'early_balance_restoration_min_drop_percent': 20,
               'server_reset_time_editable': False, 'reset_credits_auto_consume': False}


def validate(values):
    if not isinstance(values, dict) or set(values) != set(BOUNDS):
        raise ValueError('Provide only the six supported operating rules')
    for key, bounds in BOUNDS.items():
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, int) or not bounds['min'] <= value <= bounds['max']:
            raise ValueError('%s must be an integer from %s to %s' % (key, bounds['min'], bounds['max']))
    if values['resume_remaining'] < values['pause_remaining'] + 5:
        raise ValueError('resume_remaining must be at least 5 above pause_remaining')
    if values['near_limit_poll_seconds'] > values['poll_seconds']:
        raise ValueError('near_limit_poll_seconds must not exceed poll_seconds')
    return dict(values)


def effective_rules(store, config):
    base = {}
    for key, bounds in BOUNDS.items():
        value = config.get(key, bounds['default'])
        base[key] = value if type(value) is int and bounds['min'] <= value <= bounds['max'] else bounds['default']
    base['resume_remaining'] = max(base['resume_remaining'], base['pause_remaining'] + 5)
    base['near_limit_poll_seconds'] = min(base['near_limit_poll_seconds'], base['poll_seconds'])
    saved = store.get('runtime_rules', {})
    revision = saved.get('revision', 0) if isinstance(saved, dict) else 0
    if type(revision) is not int or revision < 0:
        revision = 0
    try:
        values = validate(saved['values'])
    except (KeyError, TypeError, ValueError):
        values = base
    return {'revision': revision, 'values': values, 'bounds': BOUNDS, 'constraints': CONSTRAINTS}


def effective_config(store, config):
    result = dict(config)
    result.update(effective_rules(store, config)['values'])
    result['warn_remaining'] = max(result.get('warn_remaining', 20), result['pause_remaining'])
    result['max_sample_age_seconds'] = max(config.get('max_sample_age_seconds', 90),
        result['poll_seconds'] + 2 * result.get('rpc_timeout_seconds', 25) + 10)
    return result


def update_rules(store, config, changes, revision):
    if type(revision) is not int or revision < 0:
        raise ValueError('rules_revision is required')
    if not isinstance(changes, dict) or not changes or set(changes) - set(BOUNDS):
        raise ValueError('Only operating rules may be edited; service quotas and reset times are read-only')
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        current = effective_rules(store, config)
        if revision != current['revision']:
            raise ValueError('Operating rules changed; refresh and try again')
        values = validate(dict(current['values'], **changes))
        saved = {'revision': revision + 1, 'values': values}
        store.db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)', ('runtime_rules', json.dumps(saved)))
        store.db.execute('INSERT INTO events(created,state,detail) VALUES(?,?,?)',
                         (time.time(), 'rules_updated', json.dumps(origin_detail('rules_updated', saved, 'user'))))
    return effective_rules(store, config)
