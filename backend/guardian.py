#!/usr/bin/env python3
"""Usage Guardian: deterministic quota watchdog, persistent task ledger, native CLI."""
import argparse
import asyncio
import contextlib
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))

from platform_support import (lock_file, open_lock, private_directory,
                              private_file_permissions, process_alive, python_command)
from rpc import Rpc
from mission_version import VERSION
from quota import (parse_bucket, classify, recovered, restoration_reason, restoration_details,
                   next_reset, sample_summary, window_map)
from quota_audit import observe_quota
from event_origin import origin_detail
from rules import effective_config, effective_rules
from control_policy import (active_turn, blocked_input, checkpoint_matches, decision, message_id,
                            quota_interrupted, quota_usable, same_goal, valid_goal)

ROOT = Path(__file__).resolve().parent
IS_WINDOWS = os.name == 'nt'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def atomic_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    private_file_permissions(temp)
    os.replace(str(temp), str(path))


def local_time(stamp):
    zone = dt.timezone(dt.timedelta(hours=4))
    return dt.datetime.fromtimestamp(stamp, zone).strftime("%Y-%m-%d %H:%M:%S UTC+04")


def load_config(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text(encoding="utf-8"))
    for key in ("state_dir",):
        config[key] = str((path.parent / config[key]).resolve())
    if not 0 <= config["pause_remaining"] < config["resume_remaining"] <= 100:
        raise ValueError("pause_remaining must be below resume_remaining")
    if not config["pause_remaining"] <= config["warn_remaining"] <= 100:
        raise ValueError("warn_remaining must be >= pause_remaining")
    if config["mode"] not in ("notify", "control"):
        raise ValueError("mode must be notify or control")
    if config["poll_seconds"] < 5 or config["max_sample_age_seconds"] < 5:
        raise ValueError("poll/stale intervals must be >= 5 seconds")
    config["_path"] = str(path)
    return config


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        private_directory(self.directory, enforce_mode=True)
        self.db = sqlite3.connect(str(self.directory / "guardian.sqlite3"), timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS notices (key TEXT PRIMARY KEY, title TEXT, body TEXT,
                created REAL NOT NULL, delivered INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, kind TEXT NOT NULL,
                value TEXT NOT NULL, state TEXT NOT NULL, result TEXT);
            CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, created REAL NOT NULL,
                thread_id TEXT, previous_state TEXT, state TEXT, detail TEXT);
            CREATE TABLE IF NOT EXISTS plans (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        self.db.commit()
        private_file_permissions(self.directory / "guardian.sqlite3")

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (key, json.dumps(value)))

    def tasks(self):
        return [json.loads(row[0]) for row in self.db.execute("SELECT value FROM tasks")]

    def save_task(self, task, origin=None):
        with self.db:
            old = self.db.execute("SELECT value FROM tasks WHERE id=?", (task["id"],)).fetchone()
            if old and task.get("control_revision", 0) != json.loads(old[0]).get("control_revision", 0):
                return False
            if old and json.loads(old[0])["state"] == "disabled" and task["state"] != "disabled":
                return False  # A user revocation wins over an in-flight RPC callback.
            self.db.execute("INSERT OR REPLACE INTO tasks VALUES (?,?)", (task["id"], json.dumps(task)))
            previous = json.loads(old[0])["state"] if old else None
            if previous != task["state"]:
                self.db.execute("INSERT INTO events(created,thread_id,previous_state,state,detail) VALUES(?,?,?,?,?)",
                    (time.time(), task["id"], previous, task["state"], json.dumps(origin_detail(task['state'], {k: task[k]
                     for k in ("reason", "turn_id", "action_id", "pause_source", "last_control_error",
                               "recovery_reason", "recovery_evidence") if k in task}, origin))))
        return True

    def permission(self, thread_id, enabled, expected_revision=None):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            task = self.get_task(thread_id)
            if task is None:
                raise ValueError("task is not registered")
            if expected_revision is not None and expected_revision != task.get("control_revision", 0):
                raise ValueError("任务状态已变化，请刷新后重试")
            task.update(auto_resume=bool(enabled), manual_hold=not enabled)
            task["control_revision"] = task.get("control_revision", 0) + 1
            if enabled and task["state"] in ("disabled", "held", "needs_review"):
                task.update(state="watching", reason=None, recovery_first_seen=None)
            self.db.execute("UPDATE tasks SET value=? WHERE id=?", (json.dumps(task), thread_id))
            self.db.execute("INSERT INTO events(created,thread_id,state,detail) VALUES(?,?,?,?)",
                (time.time(), thread_id, task["state"], json.dumps(origin_detail(task['state'],
                    {"automatic_control_allowed": bool(enabled)}, 'user'))))

    def get_task(self, thread_id):
        row = self.db.execute("SELECT value FROM tasks WHERE id=?", (thread_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def notice(self, key, title, body):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO notices(key,title,body,created) VALUES (?,?,?,?)",
                            (key, title, body, time.time()))

    def enqueue(self, kind, value):
        request_id = str(uuid.uuid4())
        with self.db:
            self.db.execute("INSERT INTO requests VALUES (?,?,?,?,NULL)",
                            (request_id, kind, json.dumps(value), "pending"))
        return request_id

    def close(self):
        self.db.close()



class Controller:
    def __init__(self, rpc, store, config, identity, clock=time.time, identity_check=None):
        self.rpc, self.store, self.config, self.identity, self.clock = rpc, store, config, identity, clock
        self.identity_check = identity_check
        self.rules_revision = effective_rules(store, config)['revision']

    def rules_current(self):
        return effective_rules(self.store, self.config)['revision'] == self.rules_revision

    def cancelled(self):
        return (self.store.get("supervisor_paused", False) or self.store.get("stop_requested", False)
                or not self.rules_current())

    async def view(self, thread_id):
        thread = (await self.rpc.call("thread/read", {"threadId": thread_id}))["thread"]
        turns = (await self.rpc.call("thread/turns/list", {
            "threadId": thread_id, "limit": 2, "sortDirection": "desc", "itemsView": "summary"}))["data"]
        goal = (await self.rpc.call("thread/goal/get", {"threadId": thread_id})).get("goal")
        return {"thread": thread, "turns": turns, "goal": goal}

    @staticmethod
    def anchor(view):
        return fingerprint({"updated": view["thread"].get("updatedAt"),
                            "turns": view["turns"], "goal": view["goal"]})

    async def adopt(self, thread_id, priority=100, origin='automatic'):
        if getattr(self.rpc, 'hosts', {}).get(thread_id, 'local') != 'local':
            raise ValueError('Only local Codex chats can be managed')
        # Do not reopen an arbitrary saved desktop session in a second executor.
        loaded, cursor = [], None
        while True:
            result = await self.rpc.call("thread/loaded/list", {"cursor": cursor})
            loaded.extend(result["data"])
            cursor = result.get("nextCursor")
            if not cursor:
                break
        if thread_id not in loaded:
            raise ValueError("thread is not loaded in the connected server; control unverified")
        view = await self.view(thread_id)
        if view["goal"] is not None and (not self.config.get("goal_control_enabled") or not valid_goal(view["goal"])):
            raise ValueError("goal control is unavailable or goal identity is incomplete")
        existing = next((t for t in self.store.tasks() if t["id"] == thread_id), None)
        if existing and existing["state"] != "watching":
            raise ValueError("task has an unresolved ledger entry")
        task = {"id": thread_id, "name": view["thread"].get("name") or thread_id,
                "scope": self.identity, "host_id": 'local', "state": "watching", "auto_resume": True, "priority": int(priority)}
        if self.store.get("auto_preferences", {}).get(thread_id) is False:
            raise ValueError("用户已撤销此聊天的自动控制")
        self.store.save_task(task, origin=origin)
        return {"id": thread_id, "state": "watching"}

    def review(self, task, reason, origin='automatic'):
        task.update(state="needs_review", reason=reason)
        self.store.save_task(task, origin=origin)
        self.store.notice("review:" + task["id"] + ":" + str(task.get("action_id", "")),
                          "榨汁机：任务需要检查", task["name"] + "；" + reason)

    async def pause(self, task, sample, manual=False):
        origin = 'user' if manual else 'automatic'
        if self.clock() - sample["observed_at"] > self.config["max_sample_age_seconds"]:
            return
        view = await self.view(task["id"])
        status = view["thread"]["status"]
        goal = view["goal"]
        if goal is not None and (not self.config.get("goal_control_enabled") or not valid_goal(goal)):
            return self.review(task, "Goal 控制不可用或目标身份不完整", origin=origin)
        paused_for_goal = bool(goal and goal.get("status") == "active")
        if status.get("activeFlags"):
            return  # Never interrupt a task waiting for the user's decision.
        active = active_turn(view)
        if not active and not paused_for_goal:
            return
        turn_id = active["id"] if active else None
        task.update(state="pause_intent", turn_id=turn_id, pause_sample=sample,
                    baseline_message_id=message_id(view), pause_source="manual" if manual else "monitor",
                    paused_for_goal=paused_for_goal, paused_goal=goal if paused_for_goal else None,
                    recovery_first_seen=None,
                    action_id=str(uuid.uuid4()), checkpoint={"time": self.clock(),
                        "cwd": view["thread"].get("cwd"), "recent_turns": view["turns"]},
                    **({"manual_hold": True, "auto_resume": False} if manual else {}))
        if (self.store.get('stop_requested',False) if manual else self.cancelled()) or not self.store.save_task(task, origin=origin):
            return  # Intent is durable before any side effect.
        try:
            # Expected turn ID prevents interrupting a newer turn after a race.
            await self.rpc.call("turn/interrupt", {"threadId": task["id"], "turnId": turn_id,
                **({"goal": True} if paused_for_goal else {})})
            deadline = asyncio.get_running_loop().time() + self.config["interrupt_timeout_seconds"]
            while True:
                view = await self.view(task["id"])
                latest = view["turns"][0] if view["turns"] else {}
                if paused_for_goal and not same_goal(view["goal"], task["paused_goal"]):
                    return self.review(task, "暂停期间 Goal 已变化", origin=origin)
                if not paused_for_goal and latest.get("id") != turn_id:
                    return self.review(task, "中断期间会话已变化", origin=origin)
                confirmed = ((view["goal"] or {}).get("status") == "paused" if paused_for_goal
                             else latest.get("status") == "interrupted")
                if confirmed and view["thread"]["status"]["type"] == "idle":
                    task.update(state="paused", pause_anchor=self.anchor(view), paused_at=self.clock(),
                                baseline_message_id=message_id(view),
                                paused_goal_updated_at=(view["goal"] or {}).get("updatedAt"))
                    self.store.save_task(task, origin=origin)
                    self.store.notice("paused:" + task["action_id"], "榨汁机：已暂停任务", task["name"])
                    return
                if not paused_for_goal and latest.get("status") in ("completed", "failed"):
                    return self.review(task, "回合已完成或失败，不自动续做", origin=origin)
                if asyncio.get_running_loop().time() >= deadline:
                    return self.review(task, "未收到可靠的中断确认；后台进程状态也需核对", origin=origin)
                await asyncio.sleep(0.1)
        except Exception as exc:
            task["last_control_error"] = {"type": type(exc).__name__, "detail": str(exc)[:400]}
            self.review(task, "中断结果不确定；不重试以免影响新任务", origin=origin)

    def recovery_allowed(self, task, sample):
        baseline = task.get('pause_sample') or {}
        if sample.get('limit_id', self.config['limit_id']) != baseline.get('limit_id', self.config['limit_id']):
            return False
        if sample.get('scope') and sample['scope'] != task['scope']:
            return False
        if not quota_usable(sample, self.config):
            return False
        if task.get("pause_source") == "quota":
            return (self.clock() - sample["observed_at"] <= self.config["max_sample_age_seconds"]
                    and quota_usable(sample, self.config))
        return recovered(sample, task["pause_sample"], self.config, self.clock())

    async def register_quota_interruption(self, task, view, sample):
        goal = view.get("goal")
        if goal is not None and (not self.config.get("goal_control_enabled") or not valid_goal(goal)):
            return self.review(task, "额度中断的 Goal 尚不能可靠控制")
        task.update(state="paused", turn_id=view["turns"][0]["id"], pause_source="quota",
                    baseline_message_id=message_id(view), pause_sample=sample,
                    pause_anchor=self.anchor(view), paused_at=self.clock(), recovery_first_seen=None,
                    paused_for_goal=bool(goal), paused_goal=goal,
                    paused_goal_updated_at=(goal or {}).get("updatedAt"))
        self.store.save_task(task)
        self.store.notice("quota-interruption:" + task["id"] + ":" + task["turn_id"],
                          "榨汁机：已登记额度中断", task["name"])

    async def resume(self, task):
        if self.cancelled():
            return
        from plans import has_plan
        if has_plan(self.store, task["id"]):
            return  # An explicitly scheduled custom instruction takes precedence.
        view = await self.view(task["id"])
        if view["thread"]["status"]["type"] != "idle" or not checkpoint_matches(task, view):
            return self.review(task, "暂停后会话或用户指令已变化，保留你的最新操作")
        if not task.get("auto_resume", True) or task.get("manual_hold"):
            return
        first = task.get("recovery_first_seen")
        if first is None:
            task["recovery_first_seen"] = self.clock()
            self.store.save_task(task)
            first = task["recovery_first_seen"]
        if self.clock() - first < self.config.get("recovery_confirm_seconds", 5):
            return
        # A second fresh quota read immediately before dispatch, not only a timer.
        fresh = parse_bucket(await self.rpc.call("account/rateLimits/read"),
                             self.config["limit_id"], self.clock())
        fresh['scope'] = self.identity
        if (fresh.get("quota_state") in ("metered", "service_only")
                and not set(window_map(task.get("pause_sample") or {})).issubset(window_map(fresh))):
            return self.review(task, "额度窗口已变化，请重新确认自动续接")
        if not self.recovery_allowed(task, fresh):
            task["recovery_first_seen"] = None
            self.store.save_task(task)
            return
        task['recovery_reason'] = (restoration_reason(fresh, task.get('pause_sample', {}), self.config, self.clock())
                                   or 'quota_available')
        task['recovery_evidence'] = restoration_details(fresh, window_map(task.get('pause_sample', {})), task['recovery_reason'])
        if self.identity_check and await self.identity_check() != self.identity:
            return self.review(task, "恢复前账户身份已变化")
        # Recheck after awaited network calls: a newer user turn must win.
        latest_view = await self.view(task["id"])
        if latest_view["thread"]["status"]["type"] != "idle" or not checkpoint_matches(task, latest_view):
            return self.review(task, "额度复查期间会话已变化")
        current_task = self.store.get_task(task["id"])
        if not current_task or current_task["state"] != "paused" or self.cancelled():
            return
        if current_task.get("manual_hold") or not current_task.get("auto_resume", True):
            return
        task.update(state="resume_intent", action_id=str(uuid.uuid4()))
        if not self.store.save_task(task):
            return
        message = ("榨汁机：可用额度已重新核验恢复。继续本会话原有任务，遵从用户最新指令。"
                   "先核对工作区、文件修改及仍在运行的命令，避免重复执行已完成步骤；"
                   "若原任务已完成、被取消或需要用户决定，请停止并说明。"
                   "本次续做标识：" + task["action_id"] + self.config.get("resume_message_suffix", ""))
        try:
            if task.get("paused_for_goal"):
                current = (await self.rpc.call("thread/goal/get", {"threadId": task["id"]})).get("goal")
                if not same_goal(current, task["paused_goal"]) or current.get("updatedAt") != task["paused_goal_updated_at"]:
                    return self.review(task, "恢复前 Goal 已变化")
                reply = await self.rpc.call("thread/goal/set", {"threadId": task["id"], "status": "active"})
                if not same_goal(reply.get("goal"), task["paused_goal"]) or reply["goal"].get("status") != "active":
                    return self.review(task, "Goal 激活未得到可靠确认")
                view = await self.view(task["id"])
                if active_turn(view):
                    task.update(state="running", resumed_turn_id=active_turn(view)["id"], resumed_at=self.clock())
                    self.store.save_task(task)
                    return
            result = await self.rpc.call("turn/start", {"threadId": task["id"],
                "clientUserMessageId": task["action_id"],
                "input": [{"type": "text", "text": message, "text_elements": []}],
                **({"_guardian_expected_turn_id": latest_view["turns"][0]["id"] if latest_view["turns"] else None}
                   if getattr(self.rpc, "supports_expected_previous_turn", False) else {})})
            if result["turn"].get("status") not in ("inProgress", "completed"):
                return self.review(task, "续做回合启动失败，请核对状态")
            task.update(state="running", resumed_turn_id=result["turn"]["id"],
                        resumed_at=self.clock())
            self.store.save_task(task)
            label = '新额度窗口' if task['recovery_reason'] == 'window_advanced' else '可用余额已恢复；重置原因未知'
            self.store.notice("resumed:" + task["action_id"], "榨汁机：已恢复任务", task["name"] + '；' + label)
        except Exception as exc:
            task["last_control_error"] = {"type": type(exc).__name__, "detail": str(exc)[:400]}
            self.review(task, "续做请求结果不确定；不会自动重复发送")

    async def tick(self, sample):
        if self.cancelled():
            return
        intent_errors = {}
        tasks = sorted(self.store.tasks(), key=lambda t: (t["priority"], t["id"]))
        for task in tasks:
            if getattr(self.rpc, 'hosts', {}).get(task['id'], task.get('host_id', 'local')) != 'local':
                continue
            if task["state"] in ("disabled", "needs_review"):
                continue
            if task["scope"] != self.identity:
                self.review(task, "登录账户或工作区身份已变化")
                continue
            if task["state"] in ("pause_intent", "resume_intent"):
                try:
                    view = await self.view(task["id"])
                    latest = view["turns"][0] if view["turns"] else {}
                    marker = message_id(view)
                    if (task["state"] == "resume_intent" and task.get("action_id")
                            and marker == task["action_id"] and latest.get("status") in ("inProgress", "completed")):
                        task.update(state="running", resumed_turn_id=latest["id"], resumed_at=self.clock())
                        self.store.save_task(task)
                    elif (task["state"] == "pause_intent" and view["thread"]["status"]["type"] == "idle"
                            and ((task.get("paused_for_goal") and same_goal(view["goal"], task.get("paused_goal"))
                                  and view["goal"].get("status") == "paused")
                                 or (not task.get("paused_for_goal") and latest.get("id") == task.get("turn_id")
                                     and latest.get("status") == "interrupted"))):
                        task.update(state="paused", pause_anchor=self.anchor(view), paused_at=self.clock(),
                            baseline_message_id=marker, paused_goal_updated_at=(view["goal"] or {}).get("updatedAt"))
                        self.store.save_task(task)
                    else:
                        self.review(task, "上次动作未确认；重启后禁止重复发送")
                except Exception as exc:
                    intent_errors[task["id"]] = {"type": type(exc).__name__, "detail": str(exc)[:300]}
        errors, views, resume_busy = dict(intent_errors), {}, False
        tasks = sorted(self.store.tasks(), key=lambda t: (t["priority"], t["id"]))
        for task in tasks:
            if getattr(self.rpc, 'hosts', {}).get(task['id'], task.get('host_id', 'local')) != 'local':
                continue
            if task["state"] in ("disabled", "needs_review", "held") or task["scope"] != self.identity:
                continue
            try:
                view = await self.view(task["id"])
                views[task["id"]] = view
                if task["state"] == "running":
                    latest = view["turns"][0] if view["turns"] else {}
                    if quota_interrupted(view):
                        await self.register_quota_interruption(task, view, sample)
                    elif latest.get("id") != task["resumed_turn_id"]:
                        self.review(task, "恢复后出现了其他回合")
                    elif latest.get("status") == "inProgress":
                        resume_busy = True
                    elif latest.get("status") == "completed":
                        task["state"] = "watching"
                        self.store.save_task(task)
                    else:
                        self.review(task, "恢复的回合已被中断或失败")
            except Exception as exc:
                errors[task["id"]] = {"type": type(exc).__name__, "detail": str(exc)[:300]}
        for task in sorted(self.store.tasks(), key=lambda t: (t["priority"], t["id"])):
            view = views.get(task["id"])
            if view is None or task["state"] in ("disabled", "needs_review", "held"):
                continue
            try:
                action = decision(task, view, sample, self.config)
                if action == "pause":
                    await self.pause(task, sample)
                elif action == "quota_interrupted":
                    await self.register_quota_interruption(task, view, sample)
                elif action == "user_changed":
                    self.review(task, "暂停后会话或用户指令已变化，保留你的最新操作")
                elif action == "completed":
                    task.update(state="watching", recovery_first_seen=None)
                    self.store.save_task(task)
                elif action == "recovery_ready" and not resume_busy and self.recovery_allowed(task, sample):
                    await self.resume(task)
                    if (self.store.get_task(task["id"]) or {}).get("state") == "running":
                        resume_busy = True
                elif task["state"] == "paused" and task.get("recovery_first_seen") is not None:
                    task["recovery_first_seen"] = None
                    self.store.save_task(task)
            except Exception as exc:
                errors[task["id"]] = {"type": type(exc).__name__, "detail": str(exc)[:300]}
        self.store.put("task_errors", errors)
        self.store.put("task_runtime", {tid: {
            "status": view["thread"]["status"], "goal": bool(view.get("goal")),
            "observed_at": self.clock()} for tid, view in views.items()})


async def identity_for(rpc, store=None):
    account = (await rpc.call("account/read", {"refreshToken": False})).get("account")
    if not account or account.get("type") != "chatgpt":
        raise ValueError("Codex CLI requires a subscription account sign-in")
    # Only identity metadata is hashed; tokens never enter logs, reports or our DB.
    auth_path = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "auth.json"
    workspace = None
    if auth_path.exists():
        auth = json.loads(auth_path.read_text(encoding="utf-8"))
        workspace = (auth.get("tokens") or {}).get("account_id") or auth.get("account_id")
    if not account.get("email") and not workspace:
        raise ValueError("stable account identity unavailable")
    from identity_scope import stable_account_scope
    return stable_account_scope({"type": account["type"], "email": account.get("email"),
                                 "workspace": workspace, "plan": account.get("planType")}, store)


def server_command(config):
    if config.get("server_command"):
        return config["server_command"]
    if IS_WINDOWS:
        from compatibility import windows_client
        client = windows_client(force=True)
        executable = (client or {}).get('cli')
        if not executable:
            raise ValueError('Open the compatible desktop client or install the official Codex CLI')
    else:
        executable = shutil.which("codex")
    bundled = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"
    if not executable and Path(bundled).exists():
        executable = bundled
    if not executable:
        raise ValueError("Codex CLI not found")
    runtime = Path(config["state_dir"]) / "codex-runtime"
    log = Path(config["state_dir"]) / "codex-log"
    return [executable, "-c", "sqlite_home=" + json.dumps(str(runtime)),
            "-c", "log_dir=" + json.dumps(str(log)), "app-server", "--listen", "stdio://"]


async def deliver_notices(store, config):
    if config.get("native_notifications"):
        rows = store.db.execute("SELECT key,title,body,created FROM notices ORDER BY created DESC LIMIT 60").fetchall()
        atomic_json(store.directory / "native-notices.json", [dict(row) for row in rows])
        return
    rows = store.db.execute("SELECT * FROM notices WHERE delivered=0 ORDER BY created LIMIT 20").fetchall()
    for row in rows:
        if config.get("system_notifications") and sys.platform == "darwin":
            script = ('on run argv\n display notification (item 2 of argv) with title '
                      '(item 1 of argv)\nend run')
            process = await asyncio.create_subprocess_exec("/usr/bin/osascript", "-e", script,
                row["title"], row["body"], stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            try:
                code = await asyncio.wait_for(process.wait(), 10)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                code = -1
            if code:
                continue
        print(json.dumps({"notice": row["title"], "body": row["body"]}, ensure_ascii=False), flush=True)
        with store.db:
            store.db.execute("UPDATE notices SET delivered=1 WHERE key=?", (row["key"],))


async def requests(controller):
    store = controller.store
    # In-progress requests from a crash are never silently reissued.
    with store.db:
        store.db.execute("UPDATE requests SET state='failed',result=? WHERE state='processing' AND kind='adopt'",
                         (json.dumps({"error": "previous result unknown; inspect task ledger"}),))
    rows = store.db.execute("SELECT * FROM requests WHERE state='pending' AND kind='adopt'").fetchall()
    for row in rows:
        with store.db:
            store.db.execute("UPDATE requests SET state='processing' WHERE id=?", (row["id"],))
        try:
            value = json.loads(row["value"])
            if store.get("auto_preferences", {}).get(value["thread_id"]) is False:
                raise ValueError("用户已撤销此聊天的自动控制")
            if hasattr(controller.rpc, "ensure_loaded"):
                await controller.rpc.ensure_loaded(value["thread_id"])
                if value["thread_id"] not in controller.rpc.available:
                    controller.rpc.available.append(value["thread_id"])
            if store.get("auto_preferences", {}).get(value["thread_id"]) is False:
                raise ValueError("用户已撤销此聊天的自动控制")
            existing = store.get_task(value["thread_id"])
            if existing:
                store.permission(value["thread_id"], True)
                result = {"id": value["thread_id"], "state": "watching"}
            else:
                result = await controller.adopt(value["thread_id"], value.get("priority", 100), origin='user')
            state = "done"
        except Exception as exc:
            result, state = {"error": str(exc) if isinstance(exc, ValueError) else type(exc).__name__}, "failed"
        with store.db:
            store.db.execute("UPDATE requests SET state=?,result=? WHERE id=?",
                             (state, json.dumps(result), row["id"]))


async def run(config, once=False):
    base_config = dict(config)
    store = Store(config["state_dir"])
    lock = open_lock(store.directory / "daemon.lock")
    try:
        lock_file(lock)
    except BlockingIOError:
        raise SystemExit("榨汁机已在运行；使用 status 查看。")
    store.put("stop_requested", False)
    power_guard = None
    if sys.platform == "darwin" and config.get("power_guard_enabled", True):
        try:
            power_guard = subprocess.Popen(["/usr/bin/caffeinate", "-i", "-s", "-w", str(os.getpid())],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                close_fds=True)
            store.put("power_guard", {"pid": power_guard.pid, "guardian_pid": os.getpid()})
        except OSError as exc:
            store.notice("power-guard-unavailable", "榨汁机：防睡眠保护未启动", type(exc).__name__)
    rpc = None
    failures, identity = 0, None
    try:
        while True:
            config = effective_config(store, base_config)
            rules_revision = effective_rules(store, base_config)['revision']
            if config.get("host_pid") and not process_alive(config["host_pid"]):
                return 0
            if store.get("stop_requested", False):
                return 0
            started = time.time()
            stage = "connect"
            try:
                if rpc is None:
                    rpc = Rpc(server_command(config), config["rpc_timeout_seconds"])
                    if config.get("desktop_control_enabled") or os.name == 'nt':
                        from desktop import DesktopAdapter
                        rpc = DesktopAdapter(rpc, config)
                    await rpc.start()
                stage = "account_identity"
                new_identity = await identity_for(rpc, store)
                if identity is not None and new_identity != identity:
                    store.put("supervisor_paused", True)
                identity = new_identity
                stage = "quota_read"
                quota_response = await rpc.call("account/rateLimits/read")
                if getattr(rpc, "account_display", None) is not None:
                    store.put("account_display", rpc.account_display)
                sample = parse_bucket(quota_response, config["limit_id"], started)
                sample["scope"] = identity
                # Audit every successful service sample, even without managed
                # tasks, pending plans, notifications, or control permission.
                observe_quota(store, sample, config)
                phase = classify(sample, config)
                if os.name == 'nt' and hasattr(rpc, 'refresh_control'):
                    await rpc.refresh_control()
                control_available = (config.get('desktop_control_enabled', False) and getattr(rpc, 'control_available', False)
                                     if os.name == 'nt' else True)
                if os.name == 'nt' and control_available:
                    # Showing current status is independent of permission to
                    # interrupt or resume a conversation.
                    try:
                        await rpc.discover()
                    except Exception as exc:
                        store.put('catalog_discovery_error', type(exc).__name__)
                key = identity + ":" + config["limit_id"] + ":" + fingerprint({k: w["reset"] for k, w in window_map(sample).items()})
                summary = sample_summary(sample)
                if phase in ("low", "blocked"):
                    mode = ("仅提醒模式，未中断任务" if config["mode"] == "notify" else
                            "仅监测，客户端控制连接尚未核验" if not control_available else "正在核对并暂停受管任务")
                    if config.get("quota_notifications", True):
                        store.notice(key + ":low", "榨汁机：额度不足", summary + "；" + mode)
                    store.put("last_low", sample)
                elif phase == "warning":
                    if config.get("quota_notifications", True):
                        store.notice(key + ":warning", "榨汁机：额度预警", summary)
                old_low = store.get("last_low")
                if old_low and old_low.get("scope") == identity and recovered(sample, old_low, config, started):
                    if config.get("quota_notifications", True):
                        store.notice(key + ":restored", "榨汁机：额度已恢复", summary + "；已重新核验")
                    store.put("last_low", None)
                supervisor_paused = store.get("supervisor_paused", False)
                controller = Controller(rpc, store, config, identity, identity_check=lambda: identity_for(rpc, store))
                if config.get("desktop_control_enabled") or os.name == 'nt':
                    # Directory faults never stop quota protection for loaded chats.
                    try:
                        from catalog import refresh_catalog
                        await refresh_catalog(rpc, store, dict(config, control_available=control_available), identity)
                    except Exception as exc:
                        store.put("catalog_error", type(exc).__name__)
                if config["mode"] == "control" and control_available:
                    from manual import pause_requests
                    await pause_requests(controller, sample)
                    from immediate import ImmediateRunner
                    await ImmediateRunner(controller).tick(sample)
                if config["mode"] == "control" and not supervisor_paused and control_available:
                    if config.get("desktop_control_enabled") and config.get("desktop_auto_discover"):
                        stage = "desktop_discovery"
                        excluded = set(config.get("desktop_excluded_ids", []))
                        registered = {task["id"] for task in store.tasks()}
                        for task in store.tasks():
                            if task["state"] != "disabled":
                                rpc.hosts.setdefault(task["id"], "local")
                        skipped = {}
                        for tid in (list(rpc.available) if os.name == 'nt' else await rpc.discover()):
                            if getattr(rpc, 'hosts', {}).get(tid, 'local') != 'local':
                                continue
                            if tid in excluded or tid in registered or store.get("auto_preferences", {}).get(tid) is False:
                                continue
                            try:
                                await controller.adopt(tid)
                            except Exception as exc:
                                skipped[tid] = str(exc)[:180]
                        store.put("desktop_unmanaged", skipped)
                    stage = "task_control"
                    await requests(controller)
                    from plans import PlanRunner
                    await PlanRunner(controller).tick(sample)
                    await controller.tick(sample)
                report = {"version": VERSION, "pid": os.getpid(), "observed_at": started,
                          "observed_at_dubai": local_time(started), "mode": config["mode"],
                          "phase": phase, "supervisor_paused": supervisor_paused, "quota": sample,
                          "control_available": control_available,
                          "desktop_connection_error": getattr(rpc, 'control_error', None),
                          "tasks": [{k: t.get(k) for k in ("id", "name", "state", "reason")} for t in store.tasks()],
                          "desktop_control": ("connected to existing native desktop session owners; private version-pinned IPC"
                              if config.get("desktop_control_enabled") and control_available else
                              "Windows read-only monitoring; control connection is not verified" if os.name == 'nt' else
                              "unverified; only explicitly adopted, loaded sessions are controllable"),
                          "desktop_discovery_error": getattr(rpc, "discovery_error", None),
                          "task_errors": store.get("task_errors", {}),
                          "unmanaged_desktop_sessions": store.get("desktop_unmanaged", {})}
                store.put("last_report", report)
                atomic_json(store.directory / "status.json", report)
                await deliver_notices(store, config)
                failures = 0
                if once:
                    print(json.dumps(report, ensure_ascii=False, indent=2))
                    return 0
                from plans import all_plans
                pending_plan = any(p["state"] in ("armed", "sending") for p in all_plans(store))
                delay = config["near_limit_poll_seconds"] if phase in ("warning", "low", "blocked") or pending_plan else config["poll_seconds"]
                reset = next_reset(sample)
                until_reset = reset - time.time() if reset is not None else 0
                if until_reset > 0:
                    delay = min(delay, max(2, until_reset + 2))
            except Exception as exc:
                failures += 1
                error = {"phase": "unknown", "observed_at": time.time(), "error": type(exc).__name__,
                         "stage": stage,
                         "consecutive_failures": failures, "mode": config["mode"],
                         "action": "automatic resume withheld"}
                if isinstance(exc, (sqlite3.Error, OSError)):
                    error["detail"] = str(exc)
                print(json.dumps({"error": error}, ensure_ascii=False), file=sys.stderr, flush=True)
                atomic_json(store.directory / "status.json", error)
                if failures >= 3:
                    store.notice("connection:" + str(int(time.time() // 3600)),
                                 "榨汁机：监测不可用", "连续读取失败；已停止自动恢复，请查看状态。")
                    await deliver_notices(store, config)
                if rpc:
                    await rpc.close()
                    rpc = None
                if once:
                    print(json.dumps(error, ensure_ascii=False, indent=2))
                    return 1
                delay = min(300, 10 * 2 ** min(failures, 5))
            # Wake at most every second to honor user controls without extra quota reads.
            deadline = time.monotonic() + delay
            while time.monotonic() < deadline:
                await asyncio.sleep(min(1, max(0.01, deadline - time.monotonic())))
                if store.get("stop_requested", False):
                    return 0
                if effective_rules(store, base_config)['revision'] != rules_revision:
                    break
                if config.get("host_pid") and not process_alive(config["host_pid"]):
                    return 0
                if store.db.execute("SELECT 1 FROM requests WHERE kind IN ('execute_now','pause_all') AND state='pending' LIMIT 1").fetchone():
                    break  # A manual click wakes the existing executor within a second.
                if not store.get('supervisor_paused',False) and store.db.execute("SELECT 1 FROM requests WHERE kind='adopt' AND state='pending' LIMIT 1").fetchone():
                    break
                if rpc and rpc.changed.is_set():
                    rpc.changed.clear()
                    # Coalesce event bursts; never query in a tight loop.
                    if time.time() - started >= 5:
                        break
    finally:
        if rpc:
            await rpc.close()
        if power_guard is not None and power_guard.poll() is None:
            power_guard.terminate()
            power_guard.wait(timeout=5)
        lock.close()
        store.close()


def make_launch_agent(config, python):
    if os.name == "nt":
        raise ValueError("launchd is not available on Windows; use the native application startup setting")
    import plistlib
    execution_root = Path(config.get("runtime_root", ROOT))
    execution_config = config["_path"]
    value = {"Label": "local.usage-guardian", "ProgramArguments": [str(Path(python).resolve()),
              str(execution_root / "guardian.py"), "--config", execution_config, "run"],
             "WorkingDirectory": str(execution_root), "RunAtLoad": True, "KeepAlive": True,
             "ThrottleInterval": 30, "ProcessType": "Background",
             "StandardOutPath": str(Path(config["state_dir"]) / "daemon.log"),
             "StandardErrorPath": str(Path(config["state_dir"]) / "daemon-error.log"),
             "EnvironmentVariables": {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin"}}
    output = ROOT / "local.usage-guardian.plist"
    output.write_bytes(plistlib.dumps(value))
    return str(output)



def main():
    parser = argparse.ArgumentParser(description="榨汁机：Codex 用量监测与任务控制")
    parser.add_argument("--config", default=str(ROOT / "config.json"))
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "once", "status", "pause", "unpause", "notices", "start", "stop"):
        sub.add_parser(name)
    adopt = sub.add_parser("adopt", help="托管连接服务器中已经加载的会话")
    adopt.add_argument("thread_id")
    adopt.add_argument("--priority", type=int, default=100)
    disable = sub.add_parser("disable", help="撤销任务的自动恢复")
    disable.add_argument("thread_id")
    for command in ("hold", "release"):
        permission = sub.add_parser(command, help="暂停或恢复指定任务的自动控制许可")
        permission.add_argument("thread_id")
    sub.add_parser("launch-agent", help="生成 launchd 配置文件，不安装")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.command in ("run", "once"):
        try:
            return asyncio.run(run(config, args.command == "once"))
        except KeyboardInterrupt:
            return 0
    store = Store(config["state_dir"])
    try:
        if args.command == "status":
            path = store.directory / "status.json"
            report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"phase": "not_started"}
            observed = report.get("observed_at")
            report["sample_stale"] = observed is None or time.time() - observed > config["max_sample_age_seconds"]
            report["supervisor_paused"] = store.get("supervisor_paused", False)
            with open_lock(store.directory / "daemon.lock") as lock:
                try:
                    lock_file(lock)
                    report["daemon_running"] = False
                except BlockingIOError:
                    report["daemon_running"] = True
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif args.command == "start":
            with open_lock(store.directory / "daemon.lock") as lock:
                try:
                    lock_file(lock)
                except BlockingIOError:
                    print("榨汁机已在运行")
                    return 0
            with (store.directory / "daemon.log").open("ab") as out, (store.directory / "daemon-error.log").open("ab") as err:
                execution_root = Path(config.get("runtime_root", ROOT))
                execution_config = config["_path"]
                process = subprocess.Popen(python_command(execution_root / "guardian.py", "--config", execution_config, "run"),
                    stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True, close_fds=True,
                    **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
            print("已发起后台监测，进程 %s；请使用 status 确认新鲜用量与 daemon_running。" % process.pid)
        elif args.command == "stop":
            store.put("control_revision", store.get("control_revision", 0) + 1)
            store.put("stop_requested", True)
            print("已请求停止；最多等待当前 RPC 超时后退出，不会恢复任务")
        elif args.command in ("pause", "unpause"):
            store.put("control_revision", store.get("control_revision", 0) + 1)
            store.put("supervisor_paused", args.command == "pause")
            print("已暂停任务控制" if args.command == "pause" else "已启用任务控制；下次检查时核验额度和会话")
        elif args.command in ("hold", "release"):
            store.permission(args.thread_id, args.command == "release")
            print("已保存任务控制许可；停止标记及会话复核仍优先")
        elif args.command == "adopt":
            if config["mode"] != "control":
                raise SystemExit("先配置并验证共享服务器连接，再将 mode 设为 control。")
            print(store.enqueue("adopt", {"thread_id": args.thread_id, "priority": args.priority}))
        elif args.command == "disable":
            found = False
            for task in store.tasks():
                if task["id"] == args.thread_id:
                    task["state"] = "disabled"
                    store.save_task(task, origin='user')
                    found = True
            if not found:
                raise SystemExit("未找到受管任务")
            print("已撤销自动控制；不会向任务发送继续指令")
        elif args.command == "notices":
            print(json.dumps([dict(r) for r in store.db.execute(
                "SELECT title,body,created,delivered FROM notices ORDER BY created DESC LIMIT 30")], ensure_ascii=False, indent=2))
        elif args.command == "launch-agent":
            print(make_launch_agent(config, sys.executable))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
