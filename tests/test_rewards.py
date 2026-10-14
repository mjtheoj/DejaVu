import sqlite3
import unittest

from app.main import (
    CERTIFICATE_MILESTONES,
    award_points,
    certificate_pdf,
    points_total,
)


class RewardSystemTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL
            );
            CREATE TABLE audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                details_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE notifications (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                event_key TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                entity_type TEXT,
                entity_id TEXT,
                read_at TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, event_key)
            );
            CREATE TABLE reward_ledger (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                event_key TEXT NOT NULL,
                points INTEGER NOT NULL CHECK(points > 0),
                reason TEXT NOT NULL,
                report_id TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, event_key)
            );
            CREATE TABLE certificates (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                tier TEXT NOT NULL,
                threshold_points INTEGER NOT NULL,
                points_at_issue INTEGER NOT NULL,
                serial TEXT NOT NULL UNIQUE,
                issued_at TEXT NOT NULL,
                UNIQUE(user_id, tier)
            );
            """
        )
        self.conn.execute("INSERT INTO users VALUES (1, 'Demo Student', 'student')")
        self.conn.execute("INSERT INTO users VALUES (2, 'Campus Office', 'office')")

    def tearDown(self):
        self.conn.close()

    def test_reward_is_awarded_once_for_same_event(self):
        first = award_points(
            self.conn, 1, 10, "verified-intake:report-1",
            "Found item accepted by office", "report-1", 2
        )
        retry = award_points(
            self.conn, 1, 10, "verified-intake:report-1",
            "Found item accepted by office", "report-1", 2
        )
        self.assertTrue(first)
        self.assertFalse(retry)
        self.assertEqual(points_total(self.conn, 1), 10)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM reward_ledger").fetchone()[0], 1)

    def test_office_account_does_not_receive_student_activity_points(self):
        changed = award_points(
            self.conn, 2, 10, "verified-intake:report-office",
            "Found item accepted by office", "report-office", 2
        )
        self.assertFalse(changed)
        self.assertEqual(points_total(self.conn, 2), 0)

    def test_milestone_certificates_issue_once(self):
        for index in range(1, 11):
            award_points(
                self.conn, 1, 10, "verified-intake:report-" + str(index),
                "Found item accepted by office", "report-" + str(index), 2
            )
        rows = self.conn.execute(
            "SELECT tier, threshold_points FROM certificates WHERE user_id=1 ORDER BY threshold_points"
        ).fetchall()
        self.assertEqual(
            [(row["tier"], row["threshold_points"]) for row in rows],
            [(tier["tier"], tier["threshold"]) for tier in CERTIFICATE_MILESTONES],
        )
        self.assertEqual(len(rows), 3)

    def test_certificate_pdf_is_generated(self):
        result = certificate_pdf(
            "Demo Student", "Verified Finder", 20, "LL-CERT-2026-AB12CD34", "2026-10-14T09:00:00+00:00"
        )
        self.assertTrue(result.startswith(b"%PDF-"))
        self.assertGreater(len(result), 1000)


if __name__ == "__main__":
    unittest.main()
