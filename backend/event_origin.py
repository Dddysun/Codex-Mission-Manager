"""Event causality for native history filters; no ledger migration is required.

New writers persist detail.origin. Legacy rows are grouped from narrow evidence;
the automatic fallback means a background processing record, not proof of who
caused an external change. In particular, quota user_reset remains an inference.
Task fields can outlive the action that set them: a manual pause_source must not
classify a later watching/running/review phase as another user operation.
"""

ORIGINS = frozenset(('user', 'automatic'))
USER_SOURCES = frozenset(('local_ui', 'cli', 'manual'))
USER_STATES = frozenset(('plan_armed', 'plan_cancelled', 'rules_updated'))
AUTOMATIC_PLAN_STATES = frozenset(('plan_sending', 'plan_sent', 'plan_needs_review'))
MANUAL_PAUSE_STATES = frozenset(('pause_intent', 'paused'))


def event_origin(state, detail=None):
    """Return user/automatic from persisted provenance or conservative legacy evidence."""
    state = state if isinstance(state, str) else ''
    detail = detail if isinstance(detail, dict) else {}
    explicit = detail.get('origin')
    if isinstance(explicit, str) and explicit in ORIGINS:
        return explicit
    if state == 'quota_restored':
        return 'user' if detail.get('category') == 'user_reset' else 'automatic'
    if state in AUTOMATIC_PLAN_STATES:
        return 'automatic'
    if state in USER_STATES or (isinstance(state, str) and state.startswith('immediate_') and state != 'immediate_'):
        return 'user'
    source = detail.get('source')
    if isinstance(source, str) and source in USER_SOURCES:
        return 'user'
    if type(detail.get('automatic_control_allowed')) is bool:
        return 'user'
    if state in ('held', 'disabled') and type(detail.get('manual_hold')) is bool:
        return 'user'
    if state in MANUAL_PAUSE_STATES and detail.get('pause_source') == 'manual':
        return 'user'
    return 'automatic'


def origin_detail(state, detail=None, origin=None):
    """Copy an event detail and persist its cause without changing task state."""
    result = dict(detail) if isinstance(detail, dict) else {}
    if origin is not None:
        if not isinstance(origin, str) or origin not in ORIGINS:
            raise ValueError('Event origin must be user or automatic')
        result['origin'] = origin
    else:
        result['origin'] = event_origin(state, result)
    return result
