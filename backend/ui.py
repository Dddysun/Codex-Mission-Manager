#!/usr/bin/env python3
"""Loopback-only control UI for the existing Usage Guardian ledger."""
import argparse
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

from platform_support import lock_file, open_lock, lock_held, python_command
from guardian import ROOT, Store, atomic_json, load_config
from catalog import chat_key, entry
from plans import get_plan, all_plans, set_plan
from immediate import enqueue_dispatch, latest_dispatches
from compatibility import desktop_compatibility
from rules import effective_config, effective_rules, update_rules
from quota import reset_credits
IS_WINDOWS = os.name == 'nt'



class Application:
    def __init__(self, config_path):
        self.config_path = Path(config_path)

    def state(self):
        cfg = load_config(self.config_path)
        store = Store(cfg["state_dir"])
        try:
            rules = effective_rules(store, cfg)
            cfg = effective_config(store, cfg)
            try:
                report = json.loads((store.directory / "status.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                report = {}
            now = time.time()
            compatibility = desktop_compatibility()
            control_available = (bool(report.get('control_available')) and compatibility['supported']
                                 if IS_WINDOWS else compatibility['supported'])
            running = lock_held(store.directory / "daemon.lock")
            observed = report.get("observed_at")
            fresh = observed is not None and now - observed <= cfg["max_sample_age_seconds"]
            healthy = running and fresh and bool(report.get("quota")) and report.get("phase") != "unknown"
            store.db.execute("BEGIN")
            paused = store.get("supervisor_paused", False)
            task_errors = store.get("task_errors", {})
            runtime = store.get("task_runtime", {})
            tasks = []
            catalog = store.get("chat_catalog", {})
            scope = (report.get("quota") or {}).get("scope")
            for task in store.tasks():
                if task.get('host_id', 'local') != 'local':
                    continue
                if scope and task.get("scope") != scope:
                    continue
                current = runtime.get(task["id"], {})
                runtime_fresh = now - current.get("observed_at", 0) <= cfg["max_sample_age_seconds"]
                tasks.append({
                    "id": task["id"], "name": task.get("name", task["id"]),
                    "state": task["state"], "reason": task.get("reason"),
                    "auto_resume": task.get("auto_resume", True) and task["state"] not in ("disabled", "needs_review"),
                    "manual_hold": task.get("manual_hold", False),
                    "revision": task.get("control_revision", 0),
                    "runtime": current.get("status") if runtime_fresh else None,
                    "goal": bool(current.get("goal") or task.get("paused_for_goal")),
                    "connection_error": task_errors.get(task["id"]),
                    "paused_at": task.get("paused_at"), "resumed_at": task.get("resumed_at"),
                    "recovery_first_seen": task.get("recovery_first_seen"),
                })
            managed = {t["id"]: t for t in tasks}
            chats = {x["key"]: dict(x) for x in catalog.get("items", [])
                     if x.get('kind') == 'codex' and x.get('host_id') == 'local'} if catalog.get("scope") == scope else {}
            for t in tasks:
                key = chat_key("codex", "local", t["id"])
                if not catalog or catalog.get("local_error"):
                    chats.setdefault(key, entry(t["id"], t["name"]))
            pending = set()
            adoption = {}
            for record in store.db.execute("SELECT state,value,result FROM requests WHERE kind='adopt' ORDER BY rowid"):
                target = json.loads(record['value']).get('thread_id')
                adoption[target] = {'state':record['state'], 'result':json.loads(record['result'] or '{}')}
            preferences = store.get("auto_preferences", {})
            for row in store.db.execute("SELECT value FROM requests WHERE kind='adopt' AND state IN ('pending','processing')"):
                tid = json.loads(row[0]).get("thread_id")
                if preferences.get(tid) is not False:
                    pending.add(tid)
            tasks = []
            dispatches = latest_dispatches(store, scope)
            for chat in chats.values():
                local = chat["kind"] == "codex" and chat["host_id"] == "local"
                task = managed.get(chat["id"]) if local else None
                observed = chat.get("status_observed_at", 0)
                runtime_fresh = now - observed <= cfg["max_sample_age_seconds"]
                result = {"id": chat["id"], "name": chat["name"], "state": "unmanaged",
                    "reason": None, "auto_resume": False, "manual_hold": False, "revision": 0,
                    "runtime": (chat.get("runtime") or {"type": chat["status"]}) if runtime_fresh else {"type": "unknown"},
                    "goal": False, "connection_error": None, "managed": bool(task), "auto_pending": chat["id"] in pending if local else False}
                if task:
                    result.update(task)
                    result["name"] = chat["name"]
                    if result["runtime"] is None and runtime_fresh:
                        result["runtime"] = chat.get("runtime") or {"type": chat["status"]}
                result.update({k: chat.get(k) for k in ("key", "kind", "host_id", "category", "can_control", "capability_note", "source_label", "execution_stage")})
                if IS_WINDOWS and local and not control_available:
                    result.update(can_control=False, capability_note='Windows 客户端控制连接尚未通过核验；当前仅显示目录与执行阶段')
                intent = adoption.get(chat['id']) if local else None
                opted = preferences.get(chat['id'])
                if not task and opted is True:
                    result['auto_resume'] = True
                if opted is False and not task:
                    result['auto_connection'] = 'off'
                    result['auto_error'] = None
                elif intent and not task:
                    result['auto_connection'] = ('waiting_global' if paused else 'queued') if intent['state'] == 'pending' else ('connecting' if intent['state'] == 'processing' else 'failed' if intent['state'] == 'failed' else 'off')
                    result['auto_error'] = intent['result'].get('error') if intent['state'] == 'failed' else None
                else:
                    result['auto_connection'] = 'connected' if task else 'off'
                    result['auto_error'] = None
                result["immediate"] = dispatches.get(chat["key"])
                plan = get_plan(store, chat["key"])
                result["plan"] = ({k: plan.get(k) for k in ("state", "prompt", "revision", "armed_at", "armed_window_reset", "armed_window_minutes", "armed_window_key", "reason", "finished_at")}
                    if plan and (not scope or plan["scope"] == scope) else {"state": "off", "prompt": "继续任务", "revision": (plan or {}).get("revision", 0)})
                tasks.append(result)
            tasks.sort(key=lambda t: next((x.get("updated_at") or 0 for x in chats.values() if x["key"] == t["key"]), 0), reverse=True)
            names = {task["id"]: task["name"] for task in tasks}
            events = []
            for row in store.db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 200"):
                event = dict(row)
                if event["thread_id"] and event["thread_id"] not in names:
                    continue
                event["detail"] = json.loads(event["detail"] or "{}")
                event["name"] = names.get(event["thread_id"], "全局控制")
                events.append(event)
            global_revision = store.get("control_revision", 0)
            stop_requested = store.get("stop_requested", False)
            usage = store.get("account_display") or {"account": None,
                "windows": {"five_hour": None, "weekly": None}, "quota_windows": [],
                "quota_state": "unknown", "service_allowed": False, "blocked": False,
                "scheduling_available": False, "observed_at": None}
            usage["stale"] = not running or now - (usage.get("observed_at") or 0) > cfg["max_sample_age_seconds"]
            usage.setdefault('reset_credits', reset_credits({}))
            store.db.rollback()
            return {
                "observed_at": report.get("observed_at"), "now": now, "running": running,
                "healthy": healthy, "stale": not fresh, "control_paused": paused,
                "control_enabled": healthy and control_available and not paused and not stop_requested and cfg["mode"] == "control",
                "control_available": control_available,
                "desktop_connection_error": report.get('desktop_connection_error'),
                "control_revision": global_revision,
                "service_error": report.get("stage") if report.get("phase") == "unknown" else None,
                "tasks": tasks, "events": events,
                "usage": usage, "compatibility": compatibility, "rules": rules,
                "bulk_pause": store.get("bulk_pause_result"),
                "catalog": {"observed_at": catalog.get("observed_at"), "local_only": True,
                            "local_error": catalog.get("local_error")},
                "policy": {"pause": cfg["pause_remaining"], "resume": cfg["resume_remaining"],
                           "confirm_seconds": cfg.get("recovery_confirm_seconds", 5)},
                "poll_seconds": cfg["poll_seconds"],
                "near_limit_poll_seconds": cfg["near_limit_poll_seconds"],
                "pid": report.get("pid") if running else None,
            }
        finally:
            store.close()

    def action(self, payload):
        cfg = load_config(self.config_path)
        action = payload.get("action")
        if action not in ("pause", "enable", "hold", "release", "start", "set_plan", "set_auto", "execute_now", "pause_all", "set_rules"):
            raise ValueError("未知操作")
        store = Store(cfg["state_dir"])
        try:
            if action == 'set_rules':
                return {'rules': update_rules(store, cfg, payload.get('rules'), payload.get('rules_revision')),
                        'message': '运行规则已保存', 'message_en': 'Operating rules saved.'}
            cfg = effective_config(store, cfg)
            if action == "start":
                runtime = Path(cfg.get("runtime_root", ROOT))
                result = subprocess.run(python_command(runtime / "guardian.py", "--config", self.config_path, "start"), capture_output=True, text=True, timeout=10)
                if result.returncode:
                    raise ValueError("后台启动失败，请查看服务日志")
                return {"message": "已请求启动后台服务，正在等待首次检查"}
            if IS_WINDOWS:
                disabling = action in ('pause','hold') or (action in ('set_auto','set_plan') and payload.get('enabled') is False)
                if not disabling:
                    try:
                        current = json.loads((store.directory/'status.json').read_text(encoding='utf-8'))
                    except (OSError, ValueError):
                        current = {}
                    if (not cfg.get('desktop_control_enabled') or not current.get('control_available')
                            or not desktop_compatibility()['supported']):
                        raise ValueError('Windows 客户端控制连接尚未通过核验，当前不可发送或启用自动控制')
            revision = payload.get("revision")
            if not isinstance(revision, int) or isinstance(revision, bool):
                raise ValueError("操作缺少当前版本，请刷新后重试")
            if action == "pause_all":
                report = json.loads((store.directory / 'status.json').read_text(encoding="utf-8"))
                if cfg['mode'] != 'control' or not lock_held(store.directory / 'daemon.lock') or report.get('phase') == 'unknown':
                    raise ValueError('后台发送服务尚未就绪，未提交指令')
                if time.time() - report.get('observed_at',0) > cfg['max_sample_age_seconds']:
                    raise ValueError('需要先取得可靠的账号和额度采样')
                with store.db:
                    store.db.execute("BEGIN IMMEDIATE")
                    if revision != store.get('control_revision', 0):
                        raise ValueError('控制状态已变化，请刷新后重试')
                    if store.db.execute("SELECT 1 FROM requests WHERE kind='pause_all' AND state IN ('pending','processing')").fetchone():
                        raise ValueError('暂停请求正在处理，请等待结果')
                    # Freeze precisely the opted-in managed chats, never every catalog item.
                    ids = [t['id'] for t in store.tasks() if t.get('auto_resume',True) and not t.get('manual_hold') and t['state'] not in ('disabled','needs_review')]
                    import uuid
                    request_id = str(uuid.uuid4())
                    store.db.execute('INSERT INTO requests VALUES(?,?,?,?,NULL)',(request_id,'pause_all',json.dumps({'ids':ids,'scope':(store.get('last_report',{}).get('quota') or {}).get('scope')}),'pending'))
                    for key,value in [('supervisor_paused',True),('control_revision',revision+1),('bulk_pause_result',{'state':'pending','total':len(ids),'paused':0,'skipped':0,'failed':0})]:
                        store.db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',(key,json.dumps(value)))
                return {'message':'已提交暂停，正在逐项核对受管任务','message_en':'Pause requested. Checking managed tasks individually.'}
            if action in ("set_plan", "set_auto", "execute_now"):
                try:
                    report = json.loads((store.directory / "status.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    if not (IS_WINDOWS and action in ('set_auto','set_plan') and payload.get('enabled') is False):
                        raise
                    report = {}  # A cached, same-account revocation never dispatches.
                sample = report.get("quota") or (store.get("last_report", {}).get("quota") or {})
                catalog = store.get("chat_catalog", {})
                chat = next((c for c in catalog.get("items", []) if c["key"] == payload.get("key")), None)
                revoking_local = (IS_WINDOWS and chat and chat.get('kind') == 'codex'
                                  and chat.get('host_id') == 'local' and payload.get('enabled') is False
                                  and action in ('set_auto','set_plan') and bool(sample.get('scope'))
                                  and catalog.get('scope') == sample.get('scope'))
                if (IS_WINDOWS and action in ('set_auto','set_plan') and payload.get('enabled') is False
                        and (not sample.get('scope') or catalog.get('scope') != sample.get('scope'))):
                    raise ValueError('登录账号尚未核对，无法修改该聊天的许可或预约')
                if not chat or (not chat.get("can_control") and not revoking_local) or catalog.get("scope") != sample.get("scope"):
                    raise ValueError("该聊天本次仅显示目录，未启用自动执行")
                if action == "execute_now":
                    if (cfg["mode"] != "control" or not lock_held(store.directory / "daemon.lock")
                            or report.get("phase") == "unknown"):
                        raise ValueError("后台发送服务尚未就绪，未提交指令")
                    request_id = enqueue_dispatch(store, chat, payload.get("prompt"), payload.get("request_id"),
                        revision, sample, cfg)
                    return {"message": "已提交立刻执行，正在核对并确认发送结果", "request_id": request_id}
                enabled = payload.get("enabled")
                if not isinstance(enabled, bool):
                    raise ValueError("开关值无效")
                if action == "set_plan":
                    if enabled and (not sample.get("scope") or time.time() - sample.get("observed_at", 0) > cfg["max_sample_age_seconds"]):
                        raise ValueError("需要先取得可靠的账号和额度采样")
                    plan_chat = chat
                    if revoking_local:
                        existing = get_plan(store, chat['key'])
                        if existing and existing.get('scope') != sample.get('scope'):
                            raise ValueError('该预约的登录账号已变化，请先核对')
                        # This ephemeral capability permits cancellation only;
                        # the stored catalog remains read-only and no enable or
                        # dispatch path receives this copy.
                        plan_chat = dict(chat, can_control=True)
                    set_plan(store, plan_chat, enabled, payload.get("prompt", "继续任务"), revision, sample)
                    if not store.get_task(chat["id"]):
                        preferences = store.get("auto_preferences", {})
                        preferences.setdefault(chat["id"], False)
                        store.put("auto_preferences", preferences)
                    return {"message": "已预约下一次额度恢复后执行，发送一次后自动关闭" if enabled else "已取消预约"}
                task = store.get_task(chat["id"])
                if task:
                    if task.get("scope") != sample.get("scope"):
                        raise ValueError("该任务的登录账号已变化，请先核对")
                    store.permission(chat["id"], enabled, expected_revision=revision)
                elif revision != 0:
                    raise ValueError("聊天状态已变化，请刷新后重试")
                preferences = store.get("auto_preferences", {})
                preferences[chat["id"]] = enabled
                store.put("auto_preferences", preferences)
                pending_rows = store.db.execute("SELECT id,value FROM requests WHERE kind='adopt' AND state IN ('pending','processing')").fetchall()
                same = [r for r in pending_rows if json.loads(r['value']).get('thread_id') == chat['id']]
                if enabled and not task and not same:
                    store.enqueue("adopt", {"thread_id": chat["id"], "queued_at":time.time()})
                if not enabled:
                    with store.db:
                        for record in same:
                            store.db.execute("UPDATE requests SET state='cancelled',result=? WHERE id=? AND state='pending'",(json.dumps({'error':'Cancelled by user'}),record['id']))
                if enabled and not task and store.get('supervisor_paused',False):
                    return {'message':'已登记，等待启用全局自动控制','message_en':'Saved. Waiting for global automatic control to be enabled.'}
                return {"message": "已允许自动控制，正在连接原聊天" if enabled else "已关闭自动控制；独立预约计划保留"}
            if action in ("hold", "release"):
                tid = payload.get("thread_id")
                if not isinstance(tid, str) or len(tid) > 100:
                    raise ValueError("无效任务")
                store.permission(tid, action == "release", expected_revision=revision)
                return {"message": "已允许该任务自动控制" if action == "release" else "已保持该任务，暂停其自动控制"}
            with store.db:
                store.db.execute("BEGIN IMMEDIATE")
                if revision != store.get("control_revision", 0):
                    raise ValueError("控制状态已变化，请刷新后重试")
                paused = action == "pause"
                for key, value in (("control_revision", revision + 1), ("supervisor_paused", paused)):
                    store.db.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (key, json.dumps(value)))
                store.db.execute("INSERT INTO events(created,state,detail) VALUES(?,?,?)",
                    (time.time(), "supervisor_paused" if paused else "supervisor_enabled", json.dumps({"source": "local_ui"})))
            return {"message": "已暂停自动控制，当前聊天继续执行" if paused else "已启用自动控制，将按规则检查任务"}
        finally:
            store.close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def allowed_host(self):
        port = self.server.server_address[1]
        return self.headers.get("Host") in ("127.0.0.1:%s" % port, "localhost:%s" % port)

    def authenticated(self):
        jar = cookies.SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie", ""))
            value = jar.get("guardian_ui")
            return value is not None and secrets.compare_digest(value.value, self.server.session)
        except (cookies.CookieError, TypeError):
            return False

    def reply(self, status, content, content_type="application/json; charset=utf-8", session=False):
        body = json.dumps(content, ensure_ascii=False).encode() if isinstance(content, dict) else content
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if session:
            self.send_header("Set-Cookie", "guardian_ui=%s; HttpOnly; SameSite=Strict; Path=/" % self.server.session)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.allowed_host():
            return self.reply(403, {"error": "仅允许本机访问"})
        if self.path == "/api/state":
            if not self.authenticated():
                return self.reply(401, {"error": "请重新打开控制界面"})
            try:
                return self.reply(200, self.server.application.state())
            except Exception:
                return self.reply(503, {"error": "暂时无法读取服务状态，请稍后刷新"})
        if self.path != '/':
            return self.reply(404, {"error": "页面不存在"})
        return self.reply(200, {'service': 'Codex Mission Manager', 'name': '任务管家',
                               'interface': 'native'}, session=True)

    def do_POST(self):
        port = self.server.server_address[1]
        origin = self.headers.get("Origin")
        if (not self.allowed_host() or not self.authenticated()
                or origin not in ("http://127.0.0.1:%s" % port, "http://localhost:%s" % port)
                or self.headers.get("X-Guardian-UI") != "1"):
            return self.reply(403, {"error": "请从本机控制界面操作"})
        if self.path != "/api/action":
            return self.reply(404, {"error": "操作不存在"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 32768 or self.headers.get_content_type() != "application/json":
                raise ValueError("无效请求")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("无效操作")
            self.reply(200, self.server.application.action(payload))
        except ValueError as exc:
            self.reply(409, {"error": str(exc)})
        except Exception:
            self.reply(503, {"error": "操作未完成，请刷新状态后核对"})


def make_server(config_path, port):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.session = secrets.token_urlsafe(32)
    server.application = Application(config_path)
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("start", "serve", "status", "stop"), nargs="?", default="start")
    parser.add_argument("--config", default=str(ROOT / "config.json"))
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    cfg = load_config(args.config)
    args.port = args.port if args.port is not None else cfg.get("ui_port", 8766)
    state = Path(cfg["state_dir"])
    state.mkdir(exist_ok=True, parents=True)
    instance = "ui" if args.port == 8766 else "ui-%s" % args.port
    lock_path, info_path = state / (instance + ".lock"), state / (instance + ".json")
    stop_path = state / (instance + ".stop")
    if args.command == "serve":
        with open_lock(lock_path) as lock:
            lock_file(lock)
            server = make_server(args.config, args.port)
            stop_path.unlink(missing_ok=True)
            server.timeout = .5
            atomic_json(info_path, {"pid": os.getpid(), "url": "http://127.0.0.1:%s" % server.server_address[1]})
            try:
                while not stop_path.exists():
                    server.handle_request()
            finally:
                server.server_close()
                stop_path.unlink(missing_ok=True)
        return
    running = lock_held(lock_path)
    info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else {}
    if args.command == "status":
        print(json.dumps(dict(info, running=running), ensure_ascii=False))
    elif args.command == "stop":
        if running:
            stop_path.touch(mode=0o600)
        print("已请求界面退出；后台任务管家继续运行")
    elif running:
        print(info.get("url", "界面正在启动"))
    else:
        runtime = Path(cfg.get("runtime_root", ROOT))
        with (state / "ui.log").open("ab") as log:
            subprocess.Popen(python_command(runtime / "ui.py", "serve", "--config", args.config, "--port", args.port), stdin=subprocess.DEVNULL,
                stdout=log, stderr=log, start_new_session=True,
                **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
        print("http://127.0.0.1:%s" % args.port)


if __name__ == "__main__":
    main()
