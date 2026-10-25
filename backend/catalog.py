"""Metadata-only chat directory; cloud ChatGPT entries are explicitly read-only."""
import json
import os
from pathlib import Path
import sqlite3
import time
from stages import from_history
from platform_support import sqlite_ro_uri


def chat_key(kind, host, thread_id):
    return "%s:%s:%s" % (kind, host, thread_id)


def entry(thread_id, title, kind="codex", host="local", status="notLoaded", updated_at=None):
    local = kind == "codex" and host == "local"
    return {"key": chat_key(kind, host, thread_id), "id": thread_id, "name": title or thread_id,
            "kind": kind, "host_id": host, "category": "codex" if local else "chatgpt",
            "status": status, "updated_at": updated_at, "can_control": local,
            "capability_note": None if local else "本次仅显示目录，未启用自动执行",
            "source_label": "Codex · 本机" if local else "ChatGPT Work · 云端" if kind == "codex" else "ChatGPT"}


async def refresh_catalog(rpc, store, config, scope):
    now = time.time()
    account_id = ((store.get("account_display") or {}).get("account") or {}).get("id")
    items, error = {}, None
    seed_path = Path(config["state_dir"]) / "chat-catalog-seed.json"
    seed = {}
    try:
        seed = json.loads(seed_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if seed.get("account_id") != account_id or not account_id:
        seed = {}
    for item in seed.get("items", []):
        if item.get("kind") not in ("codex", "chatgpt"):
            continue
        row = entry(item["id"], item.get("title"), item["kind"], item.get("host_id", "local"),
                    item.get("status", "unknown"), item.get("updated_at"))
        if row["category"] == "codex":
            continue  # Local SQLite is authoritative for archive/delete state.
        row["status_observed_at"] = seed.get("observed_at", 0)
        items[row["key"]] = row
    path = Path(config.get("desktop_database", str(Path.home() / ".codex/state_5.sqlite")))
    local_ids = set()
    try:
        db = sqlite3.connect(sqlite_ro_uri(path), uri=True, timeout=1)
        try:
            for tid, title, updated, owner, rollout in db.execute(
                    "SELECT id,coalesce(nullif(name,''),title),updated_at,creator_account_id,rollout_path FROM threads "
                    "WHERE archived=0 AND source IN ('vscode','cli') ORDER BY updated_at DESC"):
                if owner and owner != account_id:
                    continue
                row = entry(tid, title, updated_at=updated)
                row["execution_stage"] = from_history(rollout, tid, config.get("desktop_sessions_dir"))
                local_ids.add(tid)
                row["status_observed_at"] = now
                items[row["key"]] = row
        finally:
            db.close()
    except sqlite3.Error as exc:
        error = type(exc).__name__
    # A metadata read never opens a dormant conversation or starts inference.
    for tid in getattr(rpc, "available", []):
        if not error and tid not in local_ids:
            continue
        key = chat_key("codex", "local", tid)
        try:
            view = (await rpc.call("thread/read", {"threadId": tid}))["thread"]
            row = items.get(key) or entry(tid, view.get("name"))
            row.update(status=view["status"]["type"], runtime=view["status"], status_observed_at=now)
            live, saved = view.get("execution_stage"), row.get("execution_stage")
            if live:
                # A new turn with no public message must not inherit an old result.
                row["execution_stage"] = (saved if saved and saved.get("turn_id") == live.get("turn_id")
                    and live.get("phase") == "waiting" else live)
            items[key] = row
        except Exception:
            if key in items:
                items[key].update(status="unknown", status_observed_at=now)
    result = {"scope": scope, "account_id": account_id, "observed_at": now,
              "items": sorted(items.values(), key=lambda x: x.get("updated_at") or 0, reverse=True),
              "local_error": error, "cloud_observed_at": seed.get("observed_at"),
              "cloud_snapshot": True, "cloud_auto_execute": False}
    if os.name == 'nt' and not config.get('control_available', False):
        for row in result['items']:
            if row['category'] == 'codex':
                row['can_control'] = False
                row['capability_note'] = 'Windows 客户端控制连接尚未通过核验；当前仅显示目录与执行阶段'
    store.put("chat_catalog", result)
    return result
