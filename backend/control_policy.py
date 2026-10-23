"""Python adaptation of cat2mao/codex-quota-monitor's control decisions.

Upstream: monitor/quota-monitor.ps1, commit 6e3877487fece097a11a9b1ec48fe9832a17fbb2.
Adapted Get-Decision, Get-GoalDecision, Test-SameGoal, Test-QuotaInterrupted.
Copyright (c) 2026 cat2mao. MIT; see third-party/QUOTA-MONITOR-LICENSE.
The macOS service keeps its own persistence and transport implementation.
"""


def same_goal(goal, saved):
    return bool(goal and saved) and all(goal.get(k) == saved.get(k)
        for k in ("createdAt", "objective", "tokenBudget"))


def valid_goal(goal):
    return bool(goal and goal.get("createdAt") is not None and goal.get("objective"))


def active_turn(view):
    turns = [t for t in view["turns"] if t["status"] == "inProgress"]
    if len(turns) > 1 or view["thread"].get("ambiguous_active_turns"):
        raise ValueError("Multiple active turns; refusing ambiguous control")
    return turns[0] if turns else None


def blocked_input(view):
    return bool(view["thread"]["status"].get("activeFlags"))


def message_id(view):
    return view["thread"].get("latest_message_id") or (
        view["turns"][0].get("client_message_id") if view["turns"] else None)


def quota_interrupted(view):
    if active_turn(view) or view["thread"]["status"]["type"] == "active" or blocked_input(view):
        return False
    latest = view["turns"][0] if view["turns"] else {}
    error = latest.get("quota_error")
    return bool(latest.get("id")) and ((view.get("goal") or {}).get("status") == "usageLimited"
        or (latest.get("status") == "failed" and error == "usageLimitExceeded"))


def quota_usable(sample, config):
    weekly = sample["windows"].get("secondary")
    return (not sample["blocked"] and (sample.get("service_allowed") or not config.get("require_service_allowed"))
            and sample["windows"]["primary"]["remaining"] >= config["resume_remaining"]
            and (weekly is None or weekly["remaining"] > 0))


def checkpoint_matches(task, view):
    """Ignore display metadata; preserve task/message/goal identity as upstream does."""
    if task.get("baseline_message_id") is not None:
        if message_id(view) != task["baseline_message_id"]:
            return False
    else:
        if not view["turns"] or view["turns"][0]["id"] != task.get("turn_id"):
            return False
    active = active_turn(view)
    if active and active["id"] != task.get("turn_id"):
        return False
    if task.get("paused_for_goal"):
        goal = view.get("goal")
        status = "usageLimited" if task.get("pause_source") == "quota" else "paused"
        if not same_goal(goal, task.get("paused_goal")) or goal.get("status") != status:
            return False
        if goal.get("updatedAt") != task.get("paused_goal_updated_at"):
            return False
    elif view.get("goal") is not None:
        return False
    # An interrupted/usage-failed checkpoint must remain that same terminal turn.
    latest = view["turns"][0] if view["turns"] else {}
    if not task.get("paused_for_goal") and latest.get("status") != (
            "failed" if task.get("pause_source") == "quota" else "interrupted"):
        return False
    return True


def decision(task, view, sample, config):
    state = task["state"]
    if task.get("manual_hold") or state in ("disabled", "needs_review", "held", "pause_intent", "resume_intent"):
        return "wait"
    active = active_turn(view)
    runtime = view["thread"]["status"]["type"]
    goal = view.get("goal")
    if state == "paused":
        if task.get("paused_for_goal") and (not goal or goal.get("status") == "complete"):
            return "completed"
        if not checkpoint_matches(task, view):
            return "user_changed"
        if active or runtime == "active" or blocked_input(view):
            return "wait"
        if task.get("auto_resume", True) and not task.get("manual_hold") and quota_usable(sample, config):
            return "recovery_ready"
        return "wait"
    if state == "watching" and quota_interrupted(view):
        return "quota_interrupted"
    low = (sample["blocked"] or sample["windows"]["primary"]["remaining"] <= config["pause_remaining"]
           or ((sample["windows"].get("secondary") or {}).get("remaining", 100) <= 0))
    if low and not blocked_input(view) and (active or (goal and goal.get("status") == "active")):
        return "pause"
    return "wait"
