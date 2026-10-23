"""Small, read-only excerpts of public assistant progress; never reasoning/tools."""
from datetime import datetime
from functools import lru_cache
import json
from pathlib import Path


PUBLIC_PHASES = {None, "commentary", "partial_answer", "final_answer", "final"}
TAIL_BYTES = 1024 * 1024


def public_item(item):
    if not isinstance(item, dict):
        return None
    if item.get("type") not in ("agentMessage", "AgentMessage"):
        return None
    phase = item.get("phase")
    if phase not in PUBLIC_PHASES:
        return None
    text = item.get("text", item.get("content"))
    if not isinstance(text, str) or not text.strip():
        return None
    return {"text": " ".join(text.split())[:1200],
            "phase": "result" if phase in ("final_answer", "final") else "progress"}


def from_turn(turn):
    """Only the newest turn is supplied, so old progress cannot cross turns."""
    base = {"turn_id": turn.get("turnId"), "turn_status": turn.get("status"),
            "source": "desktop", "updated_at": None}
    for item in reversed(turn.get("items") or []):
        value = public_item(item)
        if value:
            stamp = (turn.get("agentMessageCompletedAtMsById") or {}).get(item.get("id"))
            return {**base, **value, "updated_at": stamp / 1000 if isinstance(stamp, (int, float)) else None}
    return {**base, "text": "本回合尚未发布执行进展", "phase": "waiting"}


def timestamp(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError, TypeError):
        return None


@lru_cache(maxsize=128)
def _read_tail(path, mtime, size):
    # Cache invalidates on writes. Never load an entire conversation or tool log.
    with open(path, "rb") as stream:
        start = max(0, size - TAIL_BYTES)
        stream.seek(start)
        if start:
            stream.readline()  # Discard a partial JSON record.
        lines = stream.read(TAIL_BYTES).splitlines()
    stage, turn_id, status = None, None, None
    for line in lines:
        try:
            record = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        if not isinstance(record, dict):
            continue
        payload = record.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        kind, event = record.get("type"), payload.get("type")
        incoming = payload.get("turn_id") if kind in ("event_msg", "turn_context") else None
        if incoming and incoming != turn_id:
            turn_id, stage, status = incoming, None, "inProgress"
        if kind == "event_msg" and event == "task_started":
            stage, status = None, "inProgress"
        if kind == "event_msg" and event in ("task_complete", "turn_aborted"):
            status = "completed" if event == "task_complete" else "interrupted"
        item = None
        if kind == "event_msg" and event == "item_completed":
            item = payload.get("item")
        elif kind == "response_item" and event == "message" and payload.get("role") == "assistant":
            phase = payload.get("phase") or payload.get("channel")
            if phase in PUBLIC_PHASES:
                content = payload.get("content") or []
                text = " ".join(x.get("text", "") for x in content
                                if isinstance(x, dict) and x.get("type") == "output_text")
                item = {"type": "agentMessage", "text": text, "phase": phase}
        value = public_item(item) if isinstance(item, dict) else None
        if value:
            stage = {**value, "updated_at": timestamp(record.get("timestamp")), "source": "history"}
    if stage:
        return {**stage, "turn_id": turn_id, "turn_status": status}
    if turn_id:
        return {"text": "最近回合尚无可读取的执行进展", "phase": "waiting", "source": "history",
                "turn_id": turn_id, "turn_status": status, "updated_at": None}
    return None


def from_history(path, thread_id, sessions_root=None):
    if not path:
        return None
    try:
        root = Path(sessions_root or Path.home() / ".codex/sessions").resolve()
        target = Path(path).resolve()
        if not target.is_relative_to(root) or thread_id not in target.name or target.suffix != ".jsonl":
            return None
        info = target.stat()
        value = _read_tail(str(target), info.st_mtime_ns, info.st_size)
        return dict(value) if value else None
    except (OSError, ValueError):
        return None
