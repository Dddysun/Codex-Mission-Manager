import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop import normalize_state
from stages import from_history, from_turn


class StageTests(unittest.TestCase):
    def test_public_progress_only_never_reasoning_tools_or_user_input(self):
        turn = {"turnId": "new", "status": "inProgress", "items": [
            {"type": "userMessage", "text": "private user instruction"},
            {"type": "agentMessage", "text": "  正在核对\n测试结果。 ", "phase": "commentary"},
            {"type": "agentMessage", "text": "hidden analysis", "phase": "analysis"},
            {"type": "reasoning", "text": "hidden reasoning"},
            {"type": "commandExecution", "aggregatedOutput": "secret tool output"}]}
        stage = from_turn(turn)
        self.assertEqual(stage["text"], "正在核对 测试结果。")
        self.assertEqual(stage["phase"], "progress")
        self.assertNotIn("private", json.dumps(stage))
        self.assertNotIn("hidden", json.dumps(stage))

    def test_new_turn_without_progress_does_not_reuse_previous_result(self):
        result = normalize_state({"id": "one", "turns": [
            {"turnId": "old", "turnStartedAtMs": 1, "items": [
                {"type": "agentMessage", "text": "old result", "phase": "final_answer"}]},
            {"turnId": "new", "turnStartedAtMs": 2, "status": "inProgress", "items": []}]})
        self.assertEqual(result["thread"]["execution_stage"]["phase"], "waiting")
        self.assertEqual(result["thread"]["execution_stage"]["turn_id"], "new")

    def test_result_timestamp_and_length_bound(self):
        stage = from_turn({"turnId": "one", "items": [
            {"id": "m", "type": "agentMessage", "phase": "final_answer", "text": "a" * 9000}],
            "agentMessageCompletedAtMsById": {"m": 123000}})
        self.assertEqual(stage["updated_at"], 123)
        self.assertEqual(stage["phase"], "result")
        self.assertEqual(len(stage["text"]), 1200)

    def test_history_public_formats_cache_invalidation_and_turn_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "rollout-chat-one.jsonl"
            def write(records):
                path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
            start = {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "a"}}
            public = {"type": "event_msg", "timestamp": "2026-10-23T06:00:00Z", "payload": {
                "type": "item_completed", "turn_id": "a", "item": {
                    "type": "AgentMessage", "content": "正在验证页面", "phase": "commentary"}}}
            reasoning = {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                "channel": "analysis", "content": [{"type": "output_text", "text": "hidden"}]}}
            write([start, public, reasoning])
            stage = from_history(path, "chat-one", root)
            self.assertEqual(stage["text"], "正在验证页面")
            self.assertEqual(stage["turn_id"], "a")
            self.assertIsNotNone(stage["updated_at"])
            final = {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                "phase": "final_answer", "content": [{"type": "output_text", "text": "验证完成"}]}}
            write([start, public, final])
            self.assertEqual(from_history(path, "chat-one", root)["phase"], "result")
            write([start, public, {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "b"}}])
            self.assertEqual(from_history(path, "chat-one", root)["phase"], "waiting")

    def test_history_rejects_other_files_and_symlinks_outside_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sessions"
            root.mkdir()
            outside = Path(directory) / "chat-one.jsonl"
            outside.write_text('{}\n')
            link = root / "chat-one.jsonl"
            link.symlink_to(outside)
            self.assertIsNone(from_history(link, "chat-one", root))
            self.assertIsNone(from_history(outside, "chat-one", root))
            self.assertIsNone(from_history(link, "different-chat", root))

    def test_oversized_and_truncated_records_are_tolerated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "chat-one.jsonl"
            path.write_text(json.dumps({"type": "tool", "payload": "x" * 1100000}) + '\n' +
                '{invalid}\n' + json.dumps({"type": "event_msg", "payload": {"type": "item_completed",
                "turn_id": "a", "item": {"type": "AgentMessage", "content": "公开进展", "phase": "commentary"}}}) + '\n{"partial":')
            self.assertEqual(from_history(path, "chat-one", root)["text"], "公开进展")
