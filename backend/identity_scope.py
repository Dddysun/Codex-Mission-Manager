"""Account namespaces survive subscription changes without crossing accounts."""
import hashlib
import json


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def stable_account_scope(identity, store=None):
    # Subscription is display/policy metadata, never a different account.
    parts = {key: identity.get(key) for key in ('type', 'email', 'workspace')}
    scope = _fingerprint(dict(parts, scope_version=2))
    if store is None:
        return scope
    old = (store.get('last_report', {}).get('quota') or {}).get('scope')
    if not old or old == scope:
        return scope
    previous = (store.get('account_display') or {}).get('account') or {}
    candidates = [identity.get('plan'), previous.get('plan_type'), None,
                  'free', 'go', 'plus', 'pro', 'team', 'business', 'enterprise', 'edu']
    # Reconstruct a V0.2 scope using the CURRENT verified account/workspace.
    # An unrelated prior account cannot match merely by sharing a plan name.
    if not any(old == _fingerprint(dict(parts, plan=plan)) for plan in candidates):
        return scope

    def replace(value):
        if isinstance(value, dict):
            return {key: scope if key == 'scope' and item == old else replace(item)
                    for key, item in value.items()}
        if isinstance(value, list):
            return [replace(item) for item in value]
        return value

    # Preserve request IDs, states, revisions, prompts and manual holds. No
    # pending action is re-armed or dispatched by this one-time migration.
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        for table, key in (('tasks', 'id'), ('plans', 'key')):
            for row in store.db.execute('SELECT '+key+',value FROM '+table).fetchall():
                value = json.loads(row['value'])
                updated = replace(value)
                if updated != value:
                    store.db.execute('UPDATE '+table+' SET value=? WHERE '+key+'=?',
                                     (json.dumps(updated), row[key]))
        for row in store.db.execute('SELECT id,value,result FROM requests').fetchall():
            value = replace(json.loads(row['value']))
            result = replace(json.loads(row['result'])) if row['result'] else None
            store.db.execute('UPDATE requests SET value=?,result=? WHERE id=?',
                             (json.dumps(value), json.dumps(result) if result is not None else None, row['id']))
        for key in ('last_report', 'last_low', 'chat_catalog'):
            row = store.db.execute('SELECT value FROM kv WHERE key=?', (key,)).fetchone()
            if row:
                store.db.execute('UPDATE kv SET value=? WHERE key=?',
                                 (json.dumps(replace(json.loads(row['value']))), key))
        store.db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',
                         ('account_scope_migration_v2', json.dumps({'from': old, 'to': scope})))
    return scope
