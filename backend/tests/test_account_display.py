import base64
import json
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from account_display import avatar_url, display_snapshot


class AccountDisplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "auth.json"
        claims = {"name": "Ada Example", "email": "ada@example.test", "sub": "private-sub",
                  "https://api.openai.com/auth": {"chatgpt_account_id": "account-a", "chatgpt_plan_type": "free"}}
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        self.path.write_text(json.dumps({"tokens": {"id_token": "header." + payload + ".signature",
            "access_token": "secret-access", "refresh_token": "secret-refresh", "account_id": "account-a"}}))

    def tearDown(self):
        self.temp.cleanup()

    def view(self, plan="plus", raw=None, email="ada@example.test"):
        if raw is None:
            raw = {"primary": {"usedPercent": 92, "windowDurationMins": 300, "resetsAt": 2000000000},
                   "secondary": {"usedPercent": 80, "windowDurationMins": 10080, "resetsAt": 2000500000}}
        return display_snapshot({"account": {"type": "chatgpt", "email": email, "planType": plan}},
            {"rateLimitsByLimitId": {"codex": raw}}, "codex", 1900000000, self.path)

    def test_public_profile_and_remaining_windows_without_secrets(self):
        view = self.view()
        self.assertEqual(view["account"]["id"], "account-a")
        self.assertEqual(view["account"]["name"], "Ada Example")
        self.assertEqual(view["account"]["plan_type"], "plus")
        self.assertEqual(view["windows"]["five_hour"]["remaining"], 8)
        self.assertEqual(view["windows"]["weekly"]["remaining"], 20)
        for secret in ("secret-access", "secret-refresh", "private-sub", "signature", "id_token"):
            self.assertNotIn(secret, json.dumps(view))

    def test_free_plus_and_pro_keep_real_percentages(self):
        for plan in ("free", "plus", "pro"):
            with self.subTest(plan=plan):
                view = self.view(plan)
                self.assertEqual(view["account"]["plan_type"], plan)
                self.assertEqual(view["windows"]["five_hour"]["remaining"], 8)

    def test_upgrade_uses_bucket_plan_over_cached_account_plan(self):
        view = self.view(raw={"planType": "pro"})
        self.assertEqual(view["account"]["plan_type"], "pro")
        self.assertIsNone(view["windows"]["five_hour"])

    def test_switched_account_cannot_inherit_previous_name_or_id(self):
        view = self.view(plan="pro", email="other@example.test")
        self.assertIsNone(view["account"]["id"])
        self.assertIsNone(view["account"]["name"])
        self.assertEqual(view["account"]["plan_type"], "pro")

    def test_missing_weekly_and_different_primary_duration_are_not_guessed(self):
        view = self.view(raw={"primary": {"usedPercent": 10, "windowDurationMins": 15, "resetsAt": 2000000000}})
        self.assertIsNone(view["windows"]["five_hour"])
        self.assertIsNone(view["windows"]["weekly"])

    def test_window_mapping_uses_duration_and_preserves_zero(self):
        view = self.view(raw={"secondary": {"usedPercent": 100, "windowDurationMins": 300, "resetsAt": 2000000000}})
        self.assertEqual(view["windows"]["five_hour"]["remaining"], 0)
        self.assertIsNone(view["windows"]["weekly"])

    def test_invalid_quota_is_unavailable(self):
        for used in (None, True, -1, 101, float("nan")):
            view = self.view(raw={"primary": {"usedPercent": used, "windowDurationMins": 300, "resetsAt": 2000000000}})
            self.assertIsNone(view["windows"]["five_hour"])

    def test_missing_or_invalid_local_token_keeps_rpc_plan(self):
        self.path.write_text("not json")
        self.assertEqual(self.view()["account"]["plan_type"], "plus")
        self.assertIsNone(self.view()["account"]["id"])

    def test_signed_out_does_not_expose_previous_local_profile(self):
        view = display_snapshot({"account": None}, {}, "codex", 1900000000, self.path)
        self.assertIsNone(view["account"])

    def test_avatar_accepts_only_https_without_embedded_credentials(self):
        self.assertEqual(avatar_url("https://example.test/avatar.png"), "https://example.test/avatar.png")
        for value in ("javascript:alert(1)", "data:image/svg+xml,test", "http://example.test/a", "https://u:p@example.test/a", "https://["):
            self.assertIsNone(avatar_url(value))
