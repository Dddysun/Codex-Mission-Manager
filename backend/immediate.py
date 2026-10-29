"""Explicit manual dispatch through the existing native desktop executor."""
import json
import time
import uuid

from control_policy import active_turn, blocked_input, message_id, quota_usable
from event_origin import origin_detail

PENDING = {"pending", "checking", "sending"}


def latest_dispatches(store, scope=None):
    result = {}
    for row in store.db.execute("SELECT * FROM requests WHERE kind='execute_now' ORDER BY rowid DESC"):
        value = json.loads(row["value"])
        if scope is not None and value.get("scope") != scope:
            continue
        result.setdefault(value["key"], {"id": row["id"], "state": row["state"],
            **json.loads(row["result"] or "{}")})
    return result


def enqueue_dispatch(store, chat, prompt, request_id, revision, sample, config, now=None):
    now = time.time() if now is None else now
    if not chat.get("can_control") or chat.get("kind") != "codex" or chat.get("host_id") != "local":
        raise ValueError("该聊天仅显示目录，不能立刻执行")
    if not isinstance(prompt, str) or not 0 < len(prompt.strip()) <= 8000:
        raise ValueError("请填写1至8000字的执行指令")
    try:
        if str(uuid.UUID(request_id)) != request_id:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ValueError("发送标识无效，请刷新后重试")
    if (not sample.get("scope") or now - sample.get("observed_at", 0) > config["max_sample_age_seconds"]
            or not quota_usable(sample, config)):
        raise ValueError("当前额度或服务许可不足，请在额度可用后点击立刻执行")
    if store.get("stop_requested", False):
        raise ValueError("后台正在停止，未提交指令")
    task = store.get_task(chat["id"])
    if revision != (task or {}).get("control_revision", 0):
        raise ValueError("聊天控制状态已变化，请刷新后重试")
    value = {"key": chat["key"], "thread_id": chat["id"], "name": chat["name"],
        "scope": sample["scope"], "prompt": prompt.strip(), "requested_at": now,
        "expected_turn_id": (chat.get("execution_stage") or {}).get("turn_id")}
    with store.db:
        store.db.execute("BEGIN IMMEDIATE")
        old = store.db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
        if old:
            original = json.loads(old["value"])
            if old["kind"] != "execute_now" or any(original.get(k) != value[k] for k in ("key", "scope", "prompt")):
                raise ValueError("发送标识已被其他指令使用")
            return request_id
        for row in store.db.execute("SELECT value FROM requests WHERE kind='execute_now' AND state IN ('pending','checking','sending')"):
            if json.loads(row[0])["key"] == chat["key"]:
                raise ValueError("此聊天已有指令正在确认，请勿重复提交")
        store.db.execute("INSERT INTO requests VALUES(?,?,?,? ,NULL)",
            (request_id, "execute_now", json.dumps(value), "pending"))
        store.db.execute("INSERT INTO events(created,thread_id,state,detail) VALUES(?,?,?,?)",
            (now, chat["id"], "immediate_pending", json.dumps(origin_detail('immediate_pending',
                {"request_id": request_id}, 'user'))))
    return request_id


class ImmediateRunner:
    def __init__(self, controller):
        self.controller = controller
        self.store, self.rpc, self.config = controller.store, controller.rpc, controller.config

    def finish(self, row, state, message, turn_id=None):
        value = json.loads(row["value"])
        result = {"message": message, "turn_id": turn_id, "updated_at": self.controller.clock()}
        with self.store.db:
            self.store.db.execute("UPDATE requests SET state=?,result=? WHERE id=?",
                (state, json.dumps(result), row["id"]))
            self.store.db.execute("INSERT INTO events(created,thread_id,state,detail) VALUES(?,?,?,?)",
                (self.controller.clock(), value["thread_id"], "immediate_" + state,
                 json.dumps(origin_detail('immediate_' + state,
                    {"reason": message, "request_id": row["id"], "turn_id": turn_id}, 'user'))))
        if state in ("failed", "unknown"):
            self.store.notice("immediate:" + row["id"], "榨汁机：即时发送需要处理", value["name"] + "；" + message)

    async def view(self, value):
        return await self.controller.view(value["thread_id"])

    @staticmethod
    def idle(view):
        return (not active_turn(view) and not blocked_input(view)
                and view["thread"]["status"]["type"] in ("idle", "systemError"))

    def sent(self, row, turn_id):
        value = json.loads(row["value"])
        self.finish(row, "sent", "已确认发送到原聊天", turn_id)
        task = self.store.get_task(value["thread_id"])
        if (task and task.get("scope") == value["scope"] and task.get("auto_resume", True)
                and not task.get("manual_hold") and task["state"] not in ("disabled", "held", "needs_review")):
            task.update(state="running", resumed_turn_id=turn_id, resumed_at=self.controller.clock())
            self.store.save_task(task, origin='user')
        # Keep an independently armed future instruction, acknowledging this
        # explicitly authorized new turn without replacing its prompt/window.
        from plans import get_plan, save_plan
        plan = get_plan(self.store, value["key"])
        if plan and plan["state"] == "armed" and plan["scope"] == value["scope"]:
            plan.update(anchor_turn_id=turn_id, armed_at=self.controller.clock(), recovery_first_seen=None)
            save_plan(self.store, plan, plan["revision"])

    async def tick(self, sample):
        # Global automatic-control pause does not revoke an explicit manual click.
        if self.config["mode"] != "control" or self.store.get("stop_requested", False):
            return
        rows = self.store.db.execute("SELECT * FROM requests WHERE kind='execute_now' AND state IN ('pending','checking','sending') ORDER BY rowid").fetchall()
        for row in rows:
            value = json.loads(row["value"])
            sending = row["state"] == "sending"
            try:
                if value["scope"] != self.controller.identity:
                    raise ValueError("登录账号已变化，未发送指令")
                if sending:
                    view = await self.view(value)
                    latest = view["turns"][0] if view["turns"] else {}
                    if message_id(view) == row["id"] and latest.get("status") in ("inProgress", "completed"):
                        self.sent(row, latest.get("id"))
                    else:
                        self.finish(row, "unknown", "发送结果未确认，不会重复发送；请核对原聊天")
                    continue
                if row["state"] == "checking":
                    raise ValueError("上次发送前的检查被中止，请重新点击立刻执行")
                if self.controller.clock() - value["requested_at"] > 90:
                    raise ValueError("即时请求已过期，未延后执行；请重新点击")
                catalog = self.store.get("chat_catalog") or {}
                if catalog.get("scope") != value["scope"] or catalog.get("local_error") or not any(
                        c["key"] == value["key"] and c.get("can_control") for c in catalog.get("items", [])):
                    raise ValueError("当前聊天目录或账号未核实，未发送指令")
                with self.store.db:
                    changed = self.store.db.execute("UPDATE requests SET state='checking' WHERE id=? AND state='pending'", (row["id"],)).rowcount
                if not changed:
                    continue
                if hasattr(self.rpc, "ensure_loaded"):
                    await self.rpc.ensure_loaded(value["thread_id"])
                view = await self.view(value)
                latest = view["turns"][0] if view["turns"] else {}
                if not self.idle(view):
                    raise ValueError("聊天正在执行或等待审批，未打断任务；请空闲后再点击")
                if view["goal"] is not None:
                    raise ValueError("该聊天包含Goal，请先核对目标与预算")
                if (latest.get("started_at_ms", 0) > value["requested_at"] * 1000
                        or value.get("expected_turn_id") and latest.get("id") != value["expected_turn_id"]):
                    raise ValueError("点击后聊天出现新回合，未发送旧指令；请刷新后重试")
                from guardian import parse_bucket
                fresh = parse_bucket(await self.rpc.call("account/rateLimits/read"), self.config["limit_id"], self.controller.clock())
                if not quota_usable(fresh, self.config):
                    raise ValueError("发送前复核额度或服务许可不足，未发送指令")
                if self.controller.identity_check and await self.controller.identity_check() != value["scope"]:
                    raise ValueError("发送前登录账号已变化，未发送指令")
                if hasattr(self.rpc, "verify_latest") and not await self.rpc.verify_latest(value["thread_id"], latest.get("id")):
                    raise ValueError("聊天记录比桌面快照更新，请刷新后重试")
                again = await self.view(value)
                if not self.idle(again) or again["goal"] is not None or (
                        again["turns"][0]["id"] if again["turns"] else None) != latest.get("id"):
                    raise ValueError("发送前聊天状态已变化，未发送指令")
                if self.store.get("stop_requested", False):
                    raise ValueError("后台正在停止，未发送指令")
                if not self.controller.rules_current():
                    raise ValueError('运行规则已变化，未按旧规则发送；请刷新后重新确认')
                if self.controller.clock() - value["requested_at"] > 90:
                    raise ValueError("即时检查耗时过长，未延后发送；请重新点击")
                with self.store.db:
                    self.store.db.execute("UPDATE requests SET state='sending' WHERE id=?", (row["id"],))
                sending = True
                reply = await self.rpc.call("turn/start", {"threadId": value["thread_id"],
                    "clientUserMessageId": row["id"], "input": [{"type": "text", "text": value["prompt"] +
                    "\n\n（榨汁机：这是你点击“立刻执行”发送的指令；请先核对已有进度，避免重复执行。发送标识：" + row["id"] + "）", "text_elements": []}],
                    **({"_guardian_expected_turn_id": latest.get("id")} if getattr(self.rpc, "supports_expected_previous_turn", False) else {})})
                if reply["turn"].get("status") not in ("inProgress", "completed"):
                    raise RuntimeError("unconfirmed dispatch")
                self.sent(row, reply["turn"]["id"])
            except Exception as exc:
                self.finish(row, "unknown" if sending else "failed", "发送结果未确认，不会重复发送；请核对原聊天" if sending
                    else str(exc) if isinstance(exc, ValueError) else "连接检查失败，未发送指令：" + type(exc).__name__)
