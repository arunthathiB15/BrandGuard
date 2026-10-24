"""Regression tests: duplicate findings, active-claim false positives, tone/accessibility checks."""
import sqlite3
import unittest
from datetime import date, timedelta

from app.main import DEFAULT_RULES, review_content


def make_db(rules=DEFAULT_RULES, claims=None):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE rules(id TEXT PRIMARY KEY, title TEXT, body TEXT, category TEXT, severity TEXT, created_at TEXT);
        CREATE TABLE claims(id TEXT PRIMARY KEY, claim TEXT, source TEXT, expires TEXT, owner TEXT, status TEXT, created_at TEXT);
    """)
    for r in rules:
        db.execute("INSERT INTO rules VALUES(?,?,?,?,?,?)", (*r, "2026-01-01"))
    future = (date.today() + timedelta(days=200)).isoformat()
    past = (date.today() - timedelta(days=200)).isoformat()
    claims = claims if claims is not None else [
        ("CL-001", "Reduces processing time by 40%", "Pilot report", future, "Ops", "active"),
        ("CL-002", "Trusted by 10,000 customers", "Q3 report", past, "Marketing", "expired"),
    ]
    for cl in claims:
        db.execute("INSERT INTO claims VALUES(?,?,?,?,?,?,?)", (*cl, "2026-01-01"))
    return db


def excerpts(findings):
    return [f["excerpt"].lower() for f in findings]


class DuplicateFindings(unittest.TestCase):
    def test_expired_claim_is_reported_once(self):
        fs = review_content("We are Trusted by 10,000 customers.", make_db())
        self.assertEqual(excerpts(fs).count("trusted by 10,000 customers"), 1)


class ActiveClaimSupport(unittest.TestCase):
    def test_figure_backed_by_active_claim_is_not_flagged(self):
        fs = review_content("Our tool reduces processing time by 40% for teams.", make_db())
        self.assertEqual([f for f in fs if f["category"] == "claims"], [])

    def test_same_figure_about_something_else_is_still_flagged(self):
        fs = review_content("Save 40% on lunch today.", make_db())
        self.assertIn("40%", excerpts(fs))

    def test_unbacked_figure_is_flagged(self):
        fs = review_content("We cut costs by 90% for every team.", make_db())
        self.assertIn("90%", excerpts(fs))


class ToneAndAccessibility(unittest.TestCase):
    BAD = "Hey guys!!! This is AWESOME 🔥🔥🔥 click here now!!!"

    def test_tone_and_link_text_findings_cite_their_rules(self):
        fs = review_content(self.BAD, make_db())
        by_source = {}
        for f in fs:
            by_source.setdefault(f["source_id"], []).append(f["excerpt"].lower())
        self.assertIn("guys", by_source["VOICE-01"])
        self.assertIn("awesome", by_source["VOICE-01"])
        self.assertIn("click here", by_source["ACCESS-01"])
        self.assertTrue(any(f["category"] == "tone" and "exclamation" in f["reason"].lower() for f in fs))
        self.assertTrue(any("emoji" in f["reason"].lower() for f in fs))

    def test_no_source_no_finding(self):
        rules = [r for r in DEFAULT_RULES if r[0] not in ("VOICE-01", "ACCESS-01")]
        fs = review_content(self.BAD, make_db(rules=rules))
        self.assertEqual([f for f in fs if f["category"] in ("tone", "accessibility")], [])

    def test_clean_text_has_no_findings(self):
        fs = review_content("Meet the new dashboard. It helps customers see their work clearly.", make_db())
        self.assertEqual(fs, [])


if __name__ == "__main__":
    unittest.main()
