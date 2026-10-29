"""Durable, once-only instructions explicitly scheduled by the local UI."""
import json
import math
import time
import uuid

from control_policy import active_turn, blocked_input, message_id, quota_usable
from quota import plan_window, window_map, restoration_details
from event_origin import origin_detail

ACTIVE = {"armed", "sending"}
DEFAULT_PROMPT = "继续任务"


def get_plan(store, key):
    row = store.db.execute("SELECT value FROM plans WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def all_plans(store):
    return [json.loads(row[0]) for row in store.db.execute("SELECT value FROM plans")]


def save_plan(store, plan, expected_revision=None):
    with store.db:
        store.db.execute("BEGIN IMMEDIATE")
        old = get_plan(store, plan["key"])
        if expected_revision is not None and (old or {}).get("revision", 0) != expected_revision:
            return False
        store.db.execute("INSERT OR REPLACE INTO plans VALUES(?,?)", (plan["key"], json.dumps(plan)))
        if not old or old["state"] != plan["state"]:
            store.db.execute("INSERT INTO events(created,thread_id,previous_state,state,detail) VALUES(?,?,?,?,?)",
                (time.time(), plan["thread_id"], "plan_" + old["state"] if old else None,
                 "plan_" + plan["state"], json.dumps(origin_detail("plan_" + plan["state"],
                    {"reason": plan.get("reason"), "plan_id": plan["id"],
                    "recovery_reason": plan.get('recovery_reason'),
                    "recovery_evidence": plan.get('recovery_evidence')}))))
    return True


def set_plan(store, chat, enabled, prompt, revision, sample, now=None):
    now = time.time() if now is None else now
    if not chat.get("can_control") or chat.get("kind") != "codex" or chat.get("host_id") != "local":
        raise ValueError("该聊天本次仅显示目录，未启用自动执行")
    if not isinstance(enabled, bool) or not isinstance(prompt, str) or not 0 < len(prompt.strip()) <= 8000:
        raise ValueError("请填写1至8000字的执行指令")
    old = get_plan(store, chat["key"])
    if (old or {}).get("revision", 0) != revision:
        raise ValueError("计划已变化，请刷新后重试")
    if old and old["state"] == "sending":
        raise ValueError("指令已提交发送，正在确认结果，暂不能修改")
    selected = plan_window(sample)
    if enabled and selected is None:
        raise ValueError("当前账号未提供可预约的额度刷新窗口，请使用立刻执行。")
    editing = (enabled and old and old["state"] == "armed"
               and old.get("scope") == sample.get("scope")
               and PlanRunner.anchor_window(old, sample) is not None)
    plan = dict(old) if editing or (not enabled and old) else {"id": str(uuid.uuid4()), "key": chat["key"],
        "thread_id": chat["id"], "name": chat["name"], "kind": chat["kind"], "host_id": chat["host_id"],
        "scope": sample.get("scope"), "armed_at": now,
        "armed_window_key": selected[0] if selected else None,
        "armed_window_minutes": selected[1]["minutes"] if selected else None,
        "armed_window_reset": selected[1]["reset"] if selected else None,
        "armed_window_remaining": selected[1]["remaining"] if selected else None,
        "armed_limit_id": sample.get('limit_id'), "armed_windows": window_map(sample)}
    plan.update(state="armed" if enabled else "cancelled", prompt=prompt.strip(), revision=revision + 1,
                updated_at=now, recovery_first_seen=None, reason=None)
    if not save_plan(store, plan, revision):
        raise ValueError("计划已变化，请刷新后重试")
    return plan


def has_plan(store, thread_id):
    return any(p["thread_id"] == thread_id and p["state"] in ACTIVE | {"needs_review"} for p in all_plans(store))


class PlanRunner:
    def __init__(self, controller):
        self.controller = controller
        self.store, self.rpc, self.config = controller.store, controller.rpc, controller.config

    @staticmethod
    def anchor_window(plan, sample):
        windows = window_map(sample)
        key = plan.get("armed_window_key")
        if key:
            value = windows.get(key)
            return value if value and value["minutes"] == plan.get("armed_window_minutes") else None
        # V0.2 plans always used a five-hour primary. Never reinterpret that
        # scalar timestamp as a newly returned weekly or custom window.
        minutes = plan.get("armed_window_minutes") or 300
        values = [w for w in windows.values() if w["minutes"] == minutes]
        return values[0] if len(values) == 1 else None

    def ready(self, plan, sample):
        return self.recovery_reason(plan, sample) is not None

    def recovery_reason(self, plan, sample):
        target = self.anchor_window(plan, sample)
        reset = plan.get("armed_window_reset")
        valid = (sample.get("scope", self.controller.identity) == plan["scope"]
                and self.controller.clock() - sample["observed_at"] <= self.config["max_sample_age_seconds"]
                and target is not None and not isinstance(reset, bool) and isinstance(reset, (int, float))
                and math.isfinite(reset)
                and quota_usable(sample, self.config))
        if not valid or (plan.get('armed_limit_id') and plan['armed_limit_id'] != sample.get('limit_id')):
            return None
        current = window_map(sample)
        if any(key not in current or current[key]['minutes'] != old['minutes']
               for key, old in plan.get('armed_windows', {}).items()):
            return None
        if target['reset'] > reset:
            return 'window_advanced'
        remaining = plan.get('armed_window_remaining')
        if type(remaining) in (int, float) and math.isfinite(remaining):
            low = remaining <= (0 if target['minutes'] == 10080 else self.config['pause_remaining'])
            required = max(5, self.config['resume_remaining'] - self.config['pause_remaining']) if low else 20
            if target['remaining'] - remaining >= required:
                return 'balance_restored'
        return None

    def finish(self, plan, state, reason=None, turn_id=None):
        plan.update(state=state, reason=reason, finished_at=self.controller.clock(), resumed_turn_id=turn_id)
        return save_plan(self.store, plan, plan["revision"])

    def track_sent(self, plan, turn_id):
        if not self.finish(plan, "sent", turn_id=turn_id):
            return
        task = self.store.get_task(plan["thread_id"])
        if task and task["state"] not in ("disabled", "held", "needs_review") and task.get("auto_resume", True):
            task.update(state="running", resumed_turn_id=turn_id, resumed_at=self.controller.clock())
            self.store.save_task(task)

    async def view(self, plan, load=False):
        if load and hasattr(self.rpc, "ensure_loaded"):
            await self.rpc.ensure_loaded(plan["thread_id"])
        return await self.controller.view(plan["thread_id"])

    async def tick(self, sample):
        if self.controller.cancelled():
            return
        for plan in all_plans(self.store):
            if plan["state"] not in ACTIVE:
                continue
            if plan["scope"] != self.controller.identity:
                self.finish(plan, "needs_review", "登录账号已变化，计划未执行")
                continue
            catalog = self.store.get("chat_catalog")
            if catalog and catalog.get("local_error"):
                continue  # Do not reopen a chat while archive/account membership is unknown.
            if catalog and not catalog.get("local_error") and not any(c["key"] == plan["key"] for c in catalog.get("items", [])):
                self.finish(plan, "needs_review", "聊天已从当前目录移除或归档，计划未执行")
                continue
            try:
                if plan["state"] == "sending":
                    view = await self.view(plan)
                    latest = view["turns"][0] if view["turns"] else {}
                    if message_id(view) == plan.get("action_id") and latest.get("status") in ("inProgress", "completed"):
                        self.track_sent(plan, latest.get("id"))
                    else:
                        self.finish(plan, "needs_review", "上次发送结果未确认，不重复发送")
                    continue
                managed = self.store.get_task(plan['thread_id'])
                if managed and managed.get('manual_hold'):
                    continue
                if (sample.get("quota_state") in ("metered", "service_only")
                        and self.anchor_window(plan, sample) is None):
                    self.finish(plan, "needs_review", "额度窗口已变化，请重新确认预约")
                    continue
                if not self.ready(plan, sample):
                    if plan.get("recovery_first_seen") is not None:
                        plan["recovery_first_seen"] = None
                        save_plan(self.store, plan, plan["revision"])
                    continue
                if plan.get("recovery_first_seen") is None:
                    plan["recovery_first_seen"] = self.controller.clock()
                    save_plan(self.store, plan, plan["revision"])
                if self.controller.clock() - plan["recovery_first_seen"] < self.config.get("recovery_confirm_seconds", 5):
                    continue
                view = await self.view(plan, load=True)
                latest = view["turns"][0] if view["turns"] else {}
                # Finishing the same running turn is expected. A new turn after
                # arming means the human has supplied newer instructions.
                if (latest.get("started_at_ms", 0) > plan["armed_at"] * 1000
                        or plan.get("anchor_turn_id") and latest.get("id") != plan["anchor_turn_id"]):
                    self.finish(plan, "needs_review", "设置计划后聊天出现新回合，请确认最新指令")
                    continue
                if active_turn(view) or blocked_input(view) or view["thread"]["status"]["type"] == "active":
                    plan["anchor_turn_id"] = latest.get("id")
                    save_plan(self.store, plan, plan["revision"])
                    continue
                if view["goal"] is not None:
                    self.finish(plan, "needs_review", "该聊天包含Goal，请先确认目标与预算后再执行自定指令")
                    continue
                from guardian import parse_bucket
                fresh = parse_bucket(await self.rpc.call("account/rateLimits/read"), self.config["limit_id"], self.controller.clock())
                fresh["scope"] = self.controller.identity
                if not self.ready(plan, fresh):
                    plan["recovery_first_seen"] = None
                    save_plan(self.store, plan, plan["revision"])
                    continue
                plan['recovery_reason'] = self.recovery_reason(plan, fresh)
                plan['recovery_evidence'] = restoration_details(fresh, plan.get('armed_windows', {}), plan['recovery_reason'])
                if self.controller.identity_check and await self.controller.identity_check() != plan["scope"]:
                    self.finish(plan, "needs_review", "发送前账号已变化")
                    continue
                if hasattr(self.rpc, "verify_latest") and not await self.rpc.verify_latest(plan["thread_id"], latest.get("id")):
                    self.finish(plan, "needs_review", "本机聊天记录比桌面快照更新，请重新确认指令")
                    continue
                again = await self.view(plan)
                if (active_turn(again) or blocked_input(again)
                        or (again["turns"][0]["id"] if again["turns"] else None) != latest.get("id")):
                    continue
                current = get_plan(self.store, plan["key"])
                if self.controller.cancelled() or current["revision"] != plan["revision"] or current["state"] != "armed":
                    continue
                managed = self.store.get_task(plan['thread_id'])
                if managed and managed.get('manual_hold'):
                    continue
                plan.update(state="sending", action_id=str(uuid.uuid4()))
                if not save_plan(self.store, plan, plan["revision"]):
                    continue
                reply = await self.rpc.call("turn/start", {"threadId": plan["thread_id"],
                    "clientUserMessageId": plan["action_id"], "input": [{"type": "text", "text":
                    plan["prompt"] + "\n\n（榨汁机：这是你手动安排的额度恢复后执行指令；请先核对已有进度，避免重复执行。计划标识：" + plan["action_id"] + "）", "text_elements": []}],
                    **({"_guardian_expected_turn_id": latest.get("id")} if getattr(self.rpc, "supports_expected_previous_turn", False) else {})})
                if reply["turn"].get("status") not in ("inProgress", "completed"):
                    raise RuntimeError("start not confirmed")
                turn_id = reply["turn"]["id"]
                self.track_sent(plan, turn_id)
                self.store.notice("plan-sent:" + plan["id"], "榨汁机：已发送预约指令", plan["name"])
                break  # One confirmed manual dispatch per tick, before automatic resumes.
            except Exception as exc:
                if plan["state"] == "sending":
                    self.finish(plan, "needs_review", "发送结果未确认，不会重复发送")
                else:
                    plan["last_error"] = type(exc).__name__
                    save_plan(self.store, plan, plan["revision"])
