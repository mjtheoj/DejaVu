import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main


class LostLinkWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = main.DB_PATH
        self.old_upload = main.UPLOAD_DIR
        self.old_data = main.DATA_DIR
        self.old_demo = main.DEMO_MODE

        root = Path(self.temp.name)
        main.DATA_DIR = root
        main.DB_PATH = root / "test.sqlite"
        main.UPLOAD_DIR = root / "uploads"
        main.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        main.DEMO_MODE = False
        main.initialise_db()

        with main.connect_db() as conn:
            conn.execute(
                "INSERT INTO users(email, display_name, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                ("finder@example.test", "Finder Student", "student", main.hash_password("finder-password"), main.now_iso()),
            )
            conn.execute(
                "INSERT INTO users(email, display_name, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                ("claimant@example.test", "Claimant Student", "student", main.hash_password("claimant-password"), main.now_iso()),
            )
            conn.execute(
                "INSERT INTO users(email, display_name, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                ("office@example.test", "Campus Office", "office", main.hash_password("office-password"), main.now_iso()),
            )
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        main.DB_PATH = self.old_db
        main.UPLOAD_DIR = self.old_upload
        main.DATA_DIR = self.old_data
        main.DEMO_MODE = self.old_demo
        self.temp.cleanup()

    def login(self, email, password):
        response = self.client.post("/api/login", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 200, response.text)

    def logout(self):
        response = self.client.post("/api/logout")
        self.assertEqual(response.status_code, 200, response.text)

    def report_body(self, report_type, title, description):
        return {
            "report_type": report_type,
            "title": title,
            "description": description,
            "category": "bags_wallets",
            "occurred_at": "2026-10-13T12:00:00",
            "location_block": "Block A",
            "location_floor": "1",
            "location_room": "A-101",
            "location_area": "Library",
        }

    def test_report_intake_match_claim_handover_and_rewards(self):
        # A student first reports a lost item.
        self.login("claimant@example.test", "claimant-password")
        lost_response = self.client.post(
            "/api/reports",
            json=self.report_body("lost", "Dark blue backpack", "Dark blue backpack with two front pockets and a small stitched mark."),
        )
        self.assertEqual(lost_response.status_code, 200, lost_response.text)
        lost_report_id = lost_response.json()["report"]["id"]
        self.logout()

        # The finder reports the object. It is not public until physical intake.
        self.login("finder@example.test", "finder-password")
        found_response = self.client.post(
            "/api/reports",
            json=self.report_body("found", "Navy backpack", "Navy backpack with two front pockets and a small stitched mark."),
        )
        self.assertEqual(found_response.status_code, 200, found_response.text)
        found_report_id = found_response.json()["report"]["id"]
        self.assertEqual(found_response.json()["report"]["status"], "awaiting_intake")
        self.logout()

        # Office staff confirm receipt, assign a tag and award verified intake points.
        self.login("office@example.test", "office-password")
        intake = self.client.post(
            f"/api/reports/{found_report_id}/intake",
            json={
                "confirmed_physical_receipt": True,
                "private_detail": "Tiny stitch mark on the inside left strap.",
                "value_band": "medium",
                "sensitivity_level": 1,
            },
        )
        self.assertEqual(intake.status_code, 200, intake.text)
        tag_id = intake.json()["report"]["tag_id"]
        self.assertTrue(tag_id.startswith("LL-CVR-"))
        self.assertEqual(intake.json()["report"]["status"], "available")
        self.logout()

        # Student listings intentionally hide internal tag and verification details.
        self.login("claimant@example.test", "claimant-password")
        browse = self.client.get("/api/reports")
        self.assertEqual(browse.status_code, 200, browse.text)
        found_public = next(item for item in browse.json()["reports"] if item["id"] == found_report_id)
        self.assertNotIn("tag_id", found_public)
        self.assertNotIn("private_verification_detail", found_public)

        matches = self.client.get(f"/api/reports/{lost_report_id}/matches")
        self.assertEqual(matches.status_code, 200, matches.text)
        self.assertTrue(matches.json()["matches"])
        notifications = self.client.get("/api/notifications")
        self.assertEqual(notifications.status_code, 200, notifications.text)
        self.assertTrue(any("possible item match" in item["title"].lower() for item in notifications.json()["notifications"]))

        # The reverse order must also alert: a lost report created after intake should match items already held.
        later_lost = self.client.post(
            "/api/reports",
            json=self.report_body("lost", "Navy backpack with pockets", "Navy backpack with two front pockets and a small stitched mark."),
        )
        self.assertEqual(later_lost.status_code, 200, later_lost.text)
        notifications_after = self.client.get("/api/notifications")
        match_alerts = [
            item for item in notifications_after.json()["notifications"]
            if "possible item match" in item["title"].lower()
        ]
        self.assertGreaterEqual(len(match_alerts), 2)

        claim_response = self.client.post(
            "/api/claims",
            json={
                "report_id": found_report_id,
                "evidence": "The inside left strap has a tiny stitched mark that matches my item, and I can confirm its contents in person.",
            },
        )
        self.assertEqual(claim_response.status_code, 200, claim_response.text)
        claim_id = claim_response.json()["claim"]["id"]
        self.logout()

        self.login("office@example.test", "office-password")
        decision = self.client.post(
            f"/api/claims/{claim_id}/decision",
            json={"action": "approve", "note": "Evidence checked against the physical item."},
        )
        self.assertEqual(decision.status_code, 200, decision.text)
        self.assertEqual(decision.json()["claim"]["status"], "approved_for_collection")

        # Incorrect physical tag must not complete the handover.
        bad_handover = self.client.post(
            f"/api/claims/{claim_id}/handover",
            json={
                "confirmed_physical_handover": True,
                "claimant_identity_checked": True,
                "tag_id": "LL-CVR-WRONG",
            },
        )
        self.assertEqual(bad_handover.status_code, 422)

        handover = self.client.post(
            f"/api/claims/{claim_id}/handover",
            json={
                "confirmed_physical_handover": True,
                "claimant_identity_checked": True,
                "tag_id": tag_id,
                "note": "Physical item and claimant identity checked.",
            },
        )
        self.assertEqual(handover.status_code, 200, handover.text)
        self.assertEqual(handover.json()["status"], "returned")
        repeated = self.client.post(
            f"/api/claims/{claim_id}/handover",
            json={
                "confirmed_physical_handover": True,
                "claimant_identity_checked": True,
                "tag_id": tag_id,
            },
        )
        self.assertEqual(repeated.status_code, 409)
        self.logout()

        # Verified intake + verified return is 15 points and is visible only to the contributor.
        self.login("finder@example.test", "finder-password")
        activity = self.client.get("/api/activity/me")
        self.assertEqual(activity.status_code, 200, activity.text)
        self.assertEqual(activity.json()["total_points"], 15)
        self.assertEqual(len(activity.json()["ledger"]), 2)
        self.assertEqual(activity.json()["certificates"], [])

        # Claimant gets their own state update, not the reviewer's private note.
        self.logout()
        self.login("claimant@example.test", "claimant-password")
        claims = self.client.get("/api/claims")
        own_claim = next(item for item in claims.json()["claims"] if item["id"] == claim_id)
        self.assertEqual(own_claim["status"], "returned")
        self.assertNotIn("reviewer_note", own_claim)
        self.assertNotIn("evidence", own_claim)

if __name__ == "__main__":
    unittest.main()
