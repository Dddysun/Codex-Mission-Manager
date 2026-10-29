"""Real HTTP controls against an isolated ledger; never touches desktop tasks."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid
from unittest import mock

from platform_support import open_lock, lock_file
from guardian import Store
from test_guardian import CONFIG, sample
from ui import make_server
from catalog import entry


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        platform = mock.patch("ui.IS_WINDOWS", False)
        platform.start()
        self.addCleanup(platform.stop)
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        config = dict(CONFIG, state_dir=str(root / "state"))
        self.config_path = root / "config.json"
        self.config_path.write_text(json.dumps(config))
        self.store = Store(root / "state")
        self.store.save_task({"id": "task-1", "name": "GUI 验收任务 <script>", "state": "watching", "scope": "test"})
        self.store.put("task_runtime", {"task-1": {"status": {"type": "active", "activeFlags": []}, "observed_at": time.time()}})
        (root / "state/status.json").write_text(json.dumps({"observed_at": time.time(), "phase": "normal", "quota": {"internal_only": True}}))
        self.lease = open_lock(root / "state/daemon.lock")
        lock_file(self.lease)
        self.server = make_server(self.config_path, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.origin = "http://127.0.0.1:%s" % self.port
        self.cookie = "guardian_ui=" + self.server.session

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.lease.close()
        self.store.close()
        self.temp.cleanup()

    def request(self, method="GET", path="/api/state", body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        selected = {"Cookie": self.cookie}
        if method == "POST":
            selected.update({"Origin": self.origin, "X-Guardian-UI": "1", "Content-Type": "application/json"})
        if headers:
            selected.update(headers)
        connection.request(method, path, json.dumps(body) if body is not None else None, selected)
        response = connection.getresponse()
        status, result_headers, data = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return status, result_headers, data

    def test_live_state_exposes_allowlisted_account_readout(self):
        self.store.put("account_display", {"account": {"id": "account-1", "plan_type": "plus"},
            "observed_at": time.time(), "windows": {"five_hour": {"remaining": 8, "minutes": 300, "reset": 2000000000}, "weekly": None}})
        status, _, body = self.request()
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertTrue(data["healthy"])
        self.assertEqual(data["quota_phase"], "normal")
        self.assertEqual(data["tasks"][0]["runtime"]["type"], "active")
        self.assertNotIn("quota", data)
        self.assertEqual(data["usage"]["windows"]["five_hour"]["remaining"], 8)
        self.assertEqual(data["usage"]["account"]["id"], "account-1")
        self.assertFalse(data["usage"]["stale"])

    def test_control_enabled_uses_shared_compatibility_status(self):
        self.store.put('supervisor_paused',False)
        for supported in (False,True):
            status={'build':'fixture','supported':supported,'status':'supported' if supported else 'update_required'}
            with mock.patch('ui.desktop_compatibility',return_value=status):
                data=json.loads(self.request()[2])
            self.assertEqual(data['compatibility'],status)
            self.assertEqual(data['control_enabled'],supported)

    def test_old_usage_is_explicitly_stale(self):
        self.store.put("account_display", {"account": {"plan_type": "pro"}, "windows": {}, "observed_at": 1})
        data = json.loads(self.request()[2])
        self.assertTrue(data["usage"]["stale"])

    def test_profile_not_sampled_is_unknown(self):
        data = json.loads(self.request()[2])
        self.assertIsNone(data["usage"]["account"])
        self.assertIsNone(data["usage"]["windows"]["weekly"])

    def test_global_controls_persist_and_are_audited(self):
        for revision, action, expected in ((0, "pause", True), (1, "enable", False)):
            status, _, _ = self.request("POST", "/api/action", {"action": action, "revision": revision})
            self.assertEqual(status, 200)
            self.assertEqual(self.store.get("supervisor_paused"), expected)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM events WHERE thread_id IS NULL").fetchone()[0], 2)

    def test_quota_recovery_without_chats_is_visible_only_for_current_account_and_bucket(self):
        self.prepare_catalog()
        self.store.db.execute('DELETE FROM tasks')
        self.store.put('chat_catalog', {'scope': 'test', 'items': []})
        for scope, bucket in [('test', 'codex'), ('another-account', 'codex'), ('test', 'other')]:
            detail = {'scope': scope, 'limit_id': bucket, 'category': 'official_independent_reset',
                      'windows': [{'minutes': 10080, 'previous_remaining': 5, 'remaining': 99}]}
            self.store.db.execute('INSERT INTO events(created,state,detail) VALUES(?,?,?)',
                                  (time.time(), 'quota_restored', json.dumps(detail)))
        self.store.db.commit()
        data = json.loads(self.request()[2])
        records = [e for e in data['events'] if e['state'] == 'quota_restored']
        self.assertEqual(data['tasks'], [])
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0]['thread_id'])
        self.assertEqual(records[0]['detail']['windows'][0]['previous_remaining'], 5)
        self.assertNotIn('another-account', json.dumps(data['events']))

    def test_quota_history_is_hidden_until_account_identity_is_known(self):
        self.store.db.execute('INSERT INTO events(created,state,detail) VALUES(?,?,?)',
            (time.time(), 'quota_restored', json.dumps({'scope': 'test', 'limit_id': 'codex'})))
        self.store.db.commit()
        data = json.loads(self.request()[2])
        self.assertFalse(any(e['state'] == 'quota_restored' for e in data['events']))

    def test_task_controls_and_stale_revision(self):
        self.assertEqual(self.request("POST", "/api/action", {"action": "hold", "thread_id": "task-1", "revision": 0})[0], 200)
        self.assertTrue(self.store.get_task("task-1")["manual_hold"])
        self.assertEqual(self.request("POST", "/api/action", {"action": "release", "thread_id": "task-1", "revision": 0})[0], 409)
        self.assertTrue(self.store.get_task("task-1")["manual_hold"])
        self.assertEqual(self.request("POST", "/api/action", {"action": "release", "thread_id": "task-1", "revision": 1})[0], 200)
        self.assertFalse(self.store.get_task("task-1")["manual_hold"])

    def test_cross_origin_write_is_rejected(self):
        status, _, _ = self.request("POST", "/api/action", {"action": "pause", "revision": 0}, {"Origin": "https://unrelated.example"})
        self.assertEqual(status, 403)
        self.assertFalse(self.store.get("supervisor_paused", False))

    def test_wrong_host_is_rejected(self):
        self.assertEqual(self.request(headers={"Host": "unrelated.example"})[0], 403)

    def test_no_session_cannot_read_or_write(self):
        self.assertEqual(self.request(headers={"Cookie": ""})[0], 401)
        self.assertEqual(self.request("POST", "/api/action", {"action": "pause", "revision": 0}, {"Cookie": ""})[0], 403)

    def test_native_handshake_has_session_and_security_headers(self):
        status, headers, body = self.request(path="/")
        self.assertEqual(status, 200)
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(json.loads(body)["name"], "榨汁机")
        self.assertEqual(json.loads(body)["service"], "TokenMax")
        self.assertEqual(json.loads(body)['interface'], 'native')
        for asset in ('/app.js', '/style.css', '/favicon.svg'):
            self.assertEqual(self.request(path=asset)[0], 404)

    def test_static_path_cannot_read_runtime_files(self):
        self.assertEqual(self.request(path="/../config.json")[0], 404)
        self.assertEqual(self.request(path="/config.json")[0], 404)

    def test_missing_or_unapproved_action_is_not_executed(self):
        self.assertEqual(self.request("POST", "/api/action", {"action": "execute", "command": "anything"})[0], 409)
        self.assertEqual(self.request("POST", "/api/action", {"action": "hold", "thread_id": "missing", "revision": 0})[0], 409)

    def test_stale_sample_is_visible(self):
        (Path(self.temp.name) / "state/status.json").write_text(json.dumps({"observed_at": 1, "quota": {"internal_only": True}}))
        _, _, body = self.request()
        data = json.loads(body)
        self.assertTrue(data["stale"])
        self.assertFalse(data["healthy"])

    def prepare_catalog(self):
        now=time.time()
        report={"observed_at":now,"phase":"normal","quota":{"observed_at":now,"scope":"test","windows":{"primary":{"remaining":8,"minutes":300,"reset":2000000000}}}}
        (Path(self.temp.name)/"state/status.json").write_text(json.dumps(report))
        self.store.put("last_report",report)
        local=entry("task-1","Renamed chat")
        cloud=entry("cloud-chat","ChatGPT chat","chatgpt","chatgpt")
        self.store.put("chat_catalog",{"scope":"test","items":[local,cloud],"observed_at":now})
        return local,cloud

    def test_catalog_hides_cloud_sources_and_allows_only_local_controls(self):
        local,cloud=self.prepare_catalog()
        data=json.loads(self.request()[2])
        self.assertEqual(len(data["tasks"]),1)
        self.assertEqual(data["tasks"][0]["name"],"Renamed chat")
        self.assertNotIn(cloud['key'], json.dumps(data['tasks']))
        status,_,_=self.request("POST","/api/action",{"action":"set_plan","key":cloud["key"],"enabled":True,"prompt":"继续任务","revision":0})
        self.assertEqual(status,409)

    def test_plan_save_cancel_and_stale_revision_do_not_change_auto_control(self):
        local,_=self.prepare_catalog()
        payload={"action":"set_plan","key":local["key"],"enabled":True,"prompt":"请生成交付清单","revision":0}
        self.assertEqual(self.request("POST","/api/action",payload)[0],200)
        data=json.loads(self.request()[2]);task=data["tasks"][0]
        self.assertEqual(task["plan"]["prompt"],"请生成交付清单")
        self.assertEqual(task["plan"]["state"],"armed")
        self.assertTrue(task["auto_resume"])
        self.assertEqual(self.request("POST","/api/action",payload)[0],409)
        payload.update(enabled=False,revision=1)
        self.assertEqual(self.request("POST","/api/action",payload)[0],200)
        self.assertEqual(json.loads(self.request()[2])["tasks"][0]["plan"]["state"],"cancelled")

    def test_new_auto_toggle_and_scheduled_toggle_are_independent(self):
        local,_=self.prepare_catalog()
        self.assertEqual(self.request("POST","/api/action",{"action":"set_plan","key":local["key"],"enabled":True,"prompt":"继续任务","revision":0})[0],200)
        self.assertEqual(self.request("POST","/api/action",{"action":"set_auto","key":local["key"],"enabled":False,"revision":0})[0],200)
        t=json.loads(self.request()[2])["tasks"][0]
        self.assertFalse(t["auto_resume"])
        self.assertEqual(t["plan"]["state"],"armed")

    def prepare_unmanaged_chat(self):
        self.prepare_catalog()
        chat = entry("unmanaged-chat", "Pending chat")
        catalog = self.store.get("chat_catalog")
        catalog["items"].append(chat)
        self.store.put("chat_catalog", catalog)
        return chat

    def chat_state(self, key):
        return next(t for t in json.loads(self.request()[2])["tasks"] if t["key"] == key)

    def test_pending_auto_control_waits_for_global_enable_and_can_be_cancelled(self):
        chat = self.prepare_unmanaged_chat()
        self.store.put("supervisor_paused", True)
        payload = {"action":"set_auto", "key":chat["key"], "enabled":True, "revision":0}
        status, _, body = self.request("POST", "/api/action", payload)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["message"], "已登记，请点击开始榨汁")
        self.assertEqual(json.loads(body)["message_en"], "Saved. Select Start Juicing to begin.")
        task = self.chat_state(chat["key"])
        self.assertEqual(task["auto_connection"], "waiting_global")
        self.assertTrue(task["auto_pending"])
        self.assertTrue(task["auto_resume"])
        self.assertEqual(self.request("POST", "/api/action", dict(payload, enabled=False))[0], 200)
        task = self.chat_state(chat["key"])
        self.assertEqual(task["auto_connection"], "off")
        self.assertFalse(task["auto_pending"])
        self.assertFalse(task["auto_resume"])
        row = self.store.db.execute("SELECT state FROM requests WHERE kind='adopt'").fetchone()
        self.assertEqual(row["state"], "cancelled")
        self.assertTrue(self.store.get("supervisor_paused"))

    def test_pending_auto_control_is_idempotent_and_uses_correct_connection_phase(self):
        chat = self.prepare_unmanaged_chat()
        payload = {"action":"set_auto", "key":chat["key"], "enabled":True, "revision":0}
        for _ in range(2):
            self.assertEqual(self.request("POST", "/api/action", payload)[0], 200)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM requests WHERE kind='adopt'").fetchone()[0], 1)
        self.assertEqual(self.chat_state(chat["key"])["auto_connection"], "queued")
        with self.store.db:
            self.store.db.execute("UPDATE requests SET state='processing' WHERE kind='adopt'")
        self.assertEqual(self.chat_state(chat["key"])["auto_connection"], "connecting")

    def test_failed_adoption_exposes_failure_reason_and_allows_retry(self):
        chat = self.prepare_unmanaged_chat()
        request_id = self.store.enqueue("adopt", {"thread_id":chat["id"]})
        with self.store.db:
            self.store.db.execute("UPDATE requests SET state='failed',result=? WHERE id=?", (json.dumps({"error":"Client connection timed out"}),request_id))
        task = self.chat_state(chat["key"])
        self.assertEqual(task["auto_connection"], "failed")
        self.assertEqual(task["auto_error"], "Client connection timed out")
        self.assertFalse(task["auto_pending"])
        self.assertEqual(self.request("POST", "/api/action", {"action":"set_auto", "key":chat["key"], "enabled":True, "revision":0})[0], 200)
        task = self.chat_state(chat["key"])
        self.assertEqual(task["auto_connection"], "queued")
        self.assertIsNone(task["auto_error"])

    def test_bulk_pause_freezes_only_opted_in_managed_tasks_and_stops_automation(self):
        self.prepare_catalog()
        self.store.save_task({"id":"opted-out", "name":"Held", "state":"watching", "scope":"test", "auto_resume":False})
        self.store.save_task({"id":"held", "name":"Held", "state":"held", "scope":"test", "manual_hold":True})
        self.store.save_task({"id":"review", "name":"Review", "state":"needs_review", "scope":"test"})
        self.store.put("supervisor_paused",False)
        status, _, body = self.request("POST", "/api/action", {"action":"pause_all", "revision":0})
        self.assertEqual(status,200)
        self.assertTrue(self.store.get("supervisor_paused"))
        self.assertEqual(self.store.get("control_revision"),1)
        row = self.store.db.execute("SELECT value,state FROM requests WHERE kind='pause_all'").fetchone()
        self.assertEqual(row["state"],"pending")
        self.assertEqual(json.loads(row["value"]),{"ids":["task-1"],"scope":"test"})
        self.assertEqual(self.store.get("bulk_pause_result")["total"],1)
        self.assertEqual(self.request("POST", "/api/action", {"action":"pause_all", "revision":1})[0],409)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM requests WHERE kind='pause_all'").fetchone()[0],1)
        self.assertIn("message_en",json.loads(body))

    def test_cancel_during_connection_hides_inflight_and_subsequent_failure(self):
        chat = self.prepare_unmanaged_chat()
        payload = {"action":"set_auto", "key":chat["key"], "enabled":True, "revision":0}
        self.assertEqual(self.request("POST", "/api/action", payload)[0],200)
        with self.store.db:self.store.db.execute("UPDATE requests SET state='processing' WHERE kind='adopt'")
        self.assertEqual(self.request("POST", "/api/action", dict(payload,enabled=False))[0],200)
        task=self.chat_state(chat["key"])
        self.assertEqual(task["auto_connection"],"off")
        self.assertFalse(task["auto_pending"])
        with self.store.db:self.store.db.execute("UPDATE requests SET state='failed',result=? WHERE kind='adopt'",(json.dumps({"error":"Cancelled by user"}),))
        task=self.chat_state(chat["key"])
        self.assertEqual(task["auto_connection"],"off")
        self.assertIsNone(task["auto_error"])

    def test_bulk_pause_requires_control_mode(self):
        self.prepare_catalog()
        cfg=json.loads(self.config_path.read_text());cfg['mode']='notify';self.config_path.write_text(json.dumps(cfg))
        self.assertEqual(self.request("POST", "/api/action", {"action":"pause_all", "revision":0})[0],409)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM requests WHERE kind='pause_all'").fetchone()[0],0)
        self.assertFalse(self.store.get('supervisor_paused',False))

    def test_bulk_pause_requires_running_backend(self):
        self.prepare_catalog()
        self.lease.close()
        self.assertEqual(self.request("POST", "/api/action", {"action":"pause_all", "revision":0})[0],409)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM requests WHERE kind='pause_all'").fetchone()[0],0)

    def test_bulk_pause_requires_fresh_usable_backend_status(self):
        self.prepare_catalog()
        path=Path(self.temp.name)/'state/status.json'
        report=json.loads(path.read_text())
        for update in ({'observed_at':1},{'observed_at':time.time(),'phase':'unknown'}):
            report.update(update);path.write_text(json.dumps(report))
            self.assertEqual(self.request("POST", "/api/action", {"action":"pause_all", "revision":0})[0],409)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM requests WHERE kind='pause_all'").fetchone()[0],0)

    def test_bulk_pause_stale_revision_has_no_partial_effect(self):
        self.prepare_catalog()
        self.store.put("control_revision",3)
        self.store.put("supervisor_paused",False)
        self.assertEqual(self.request("POST", "/api/action", {"action":"pause_all", "revision":2})[0],409)
        self.assertFalse(self.store.get("supervisor_paused"))
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM requests WHERE kind='pause_all'").fetchone()[0],0)

    def test_immediate_request_is_durable_idempotent_and_has_separate_receipt(self):
        local, _ = self.prepare_catalog()
        report = {"phase": "normal", "observed_at": time.time(), "quota": sample(remaining=70)}
        report["quota"].update(observed_at=time.time(), scope="test")
        (Path(self.temp.name)/"state/status.json").write_text(json.dumps(report))
        payload = {"action": "execute_now", "key": local["key"], "prompt": "只回复：即时执行验证成功",
                   "revision": 0, "request_id": str(uuid.uuid4())}
        for _ in range(2):
            status, _, body = self.request("POST", "/api/action", payload)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["request_id"], payload["request_id"])
        task = json.loads(self.request()[2])["tasks"][0]
        self.assertEqual(task["immediate"]["state"], "pending")
        self.assertEqual(task["plan"]["state"], "off")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM requests WHERE kind='execute_now'").fetchone()[0], 1)

    def test_immediate_low_quota_is_rejected_and_no_request_is_enqueued(self):
        local, _ = self.prepare_catalog()
        report = {"phase": "low", "observed_at": time.time(), "quota": sample(remaining=8)}
        report["quota"].update(observed_at=time.time(), scope="test")
        (Path(self.temp.name)/"state/status.json").write_text(json.dumps(report))
        status, _, body = self.request("POST", "/api/action", {"action": "execute_now", "key": local["key"],
            "prompt": "继续任务", "revision": 0, "request_id": str(uuid.uuid4())})
        self.assertEqual(status, 409)
        self.assertIn("额度", json.loads(body)["error"])
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM requests WHERE kind='execute_now'").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
