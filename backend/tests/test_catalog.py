import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalog import refresh_catalog
from guardian import Store


class CatalogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.store = Store(self.path / "state")
        self.store.put("account_display", {"account": {"id": "account-a"}})
        self.db = sqlite3.connect(str(self.path / "source.sqlite"))
        self.db.execute("CREATE TABLE threads (id,name,title,updated_at,creator_account_id,archived,source,rollout_path)")
        self.db.executemany("INSERT INTO threads VALUES(?,?,?,?,?,?,?,?)", [
            ("one", "Renamed", "Old title", 10, "account-a", 0, "vscode", None),
            ("archived", None, "Archived", 20, "account-a", 1, "vscode", None),
            ("other", None, "Other account", 30, "account-b", 0, "vscode", None),
            ("subagent", None, "Not a human chat", 40, "account-a", 0, "subagent", None)])
        self.db.commit()
        self.config = {"state_dir":str(self.store.directory),"desktop_database":str(self.path / "source.sqlite")}

    async def asyncTearDown(self):
        self.db.close()
        self.store.close()
        self.temp.cleanup()

    async def test_all_local_user_chats_without_loading_or_exposing_messages(self):
        class Rpc:
            available=[]
        result=await refresh_catalog(Rpc(), self.store, self.config, "scope")
        self.assertEqual([x["id"] for x in result["items"]],["one"])
        self.assertEqual(result["items"][0]["name"],"Renamed")
        self.assertEqual(result["items"][0]["status"],"notLoaded")
        self.assertNotIn("first_user_message",json.dumps(result))

    async def test_cloud_seed_is_account_scoped_and_readonly(self):
        p=self.store.directory/'chat-catalog-seed.json'
        seed={"account_id":"account-a","observed_at":1,"items":[{"id":"cloud","title":"A ChatGPT chat","kind":"chatgpt","host_id":"chatgpt"}]}
        p.write_text(json.dumps(seed))
        class Rpc: available=[]
        result=await refresh_catalog(Rpc(), self.store, self.config, "scope")
        cloud=next(x for x in result["items"] if x["id"]=="cloud")
        self.assertFalse(cloud["can_control"])
        self.assertEqual(cloud["category"],"chatgpt")
        self.store.put("account_display",{"account":{"id":"other-account"}})
        result=await refresh_catalog(Rpc(),self.store,self.config,"other-scope")
        self.assertFalse(any(x["id"]=="cloud" for x in result["items"]))

    async def test_live_status_overrides_persisted_unloaded_metadata(self):
        class Rpc:
            available=['one']
            async def call(self, method, params):
                return {"thread":{"status":{"type":"active","activeFlags":[]}}}
        result=await refresh_catalog(Rpc(),self.store,self.config,"scope")
        self.assertEqual(result["items"][0]["status"],"active")

    async def test_live_new_turn_clears_previous_history_progress(self):
        rollout = self.path / "one.jsonl"
        rollout.write_text(json.dumps({"type": "event_msg", "payload": {"type": "item_completed",
            "turn_id": "old", "item": {"type": "AgentMessage", "content": "Old result", "phase": "final_answer"}}}) + "\n")
        self.db.execute("UPDATE threads SET rollout_path=? WHERE id='one'", (str(rollout),))
        self.db.commit()
        self.config["desktop_sessions_dir"] = str(self.path)
        class Rpc:
            available = ['one']
            async def call(self, method, params):
                return {"thread": {"status": {"type": "active"}, "execution_stage": {
                    "turn_id": "new", "phase": "waiting", "text": "本回合尚未发布执行进展"}}}
        result = await refresh_catalog(Rpc(), self.store, self.config, "scope")
        stage = result["items"][0]["execution_stage"]
        self.assertEqual(stage["phase"], "waiting")
        self.assertNotIn("Old result", json.dumps(stage))
