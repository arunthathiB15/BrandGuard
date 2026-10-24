"""Regression tests for BrandGuard Claim Ledger expiry validation."""
import sqlite3
import unittest
from datetime import date, timedelta

from app.main import claim_expiry_state, review_content


def in_memory_db(claim_text, expires, status="active"):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE rules(
            id TEXT PRIMARY KEY, title TEXT, body TEXT, category TEXT,
            severity TEXT, created_at TEXT
        );
        CREATE TABLE claims(
            id TEXT PRIMARY KEY, claim TEXT, source TEXT, expires TEXT,
            owner TEXT, status TEXT, created_at TEXT
        );
    """)
    db.execute(
        "INSERT INTO rules VALUES(?,?,?,?,?,?)",
        ("CLAIM-01", "Claims policy", "Claims require approved evidence.",
         "claims", "high", "2026-01-01T00:00:00"),
    )
    db.execute(
        "INSERT INTO claims VALUES(?,?,?,?,?,?,?)",
        ("CL-TEST", claim_text, "Approved test source", expires,
         "Marketing", status, "2026-01-01T00:00:00"),
    )
    return db


class ClaimExpiryTests(unittest.TestCase):
    claim_text = "Trusted by 10,000 customers"
    draft = "We are Trusted by 10,000 customers."

    def test_active_status_does_not_override_past_expiry(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        db = in_memory_db(self.claim_text, yesterday, status="active")
        try:
            findings = review_content(self.draft, db)
            expiry_findings = [f for f in findings if f["source_id"] == "CL-TEST"]
            self.assertEqual(len(expiry_findings), 1)
            self.assertIn("expired", expiry_findings[0]["reason"].lower())
        finally:
            db.close()

    def test_future_dated_active_claim_is_not_flagged_as_expired(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        db = in_memory_db(self.claim_text, tomorrow, status="active")
        try:
            findings = review_content(self.draft, db)
            self.assertFalse(any(f["source_id"] == "CL-TEST" for f in findings))
        finally:
            db.close()

    def test_expired_status_remains_expired_even_with_future_date(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        state = claim_expiry_state(
            {"status": "expired", "expires": tomorrow}, today=date.today()
        )
        self.assertEqual(state, "expired")

    def test_invalid_expiry_date_is_flagged_for_human_verification(self):
        db = in_memory_db(self.claim_text, "not-a-date", status="active")
        try:
            findings = review_content(self.draft, db)
            expiry_findings = [f for f in findings if f["source_id"] == "CL-TEST"]
            self.assertEqual(len(expiry_findings), 1)
            self.assertIn("invalid", expiry_findings[0]["reason"].lower())
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
