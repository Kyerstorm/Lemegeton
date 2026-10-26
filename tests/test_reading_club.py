"""Unit tests for Reading Club URL and scheduling validation."""
import unittest
from datetime import datetime, timezone

from cogs_test.general_commands.reading_club import parse_schedule_time, validate_source_url


class ReadingClubValidationTests(unittest.TestCase):
    def test_optional_source_url(self):
        self.assertIsNone(validate_source_url(None))
        self.assertIsNone(validate_source_url("  "))
        self.assertEqual(validate_source_url("https://example.org/title"), "https://example.org/title")

    def test_rejects_non_https_and_credential_urls(self):
        with self.assertRaises(ValueError):
            validate_source_url("http://example.org/title")
        with self.assertRaises(ValueError):
            validate_source_url("https://user:pass@example.org/title")

    def test_schedule_requires_timezone(self):
        with self.assertRaises(ValueError):
            parse_schedule_time("2026-11-02T18:30", datetime(2026, 10, 26, tzinfo=timezone.utc))

    def test_schedule_must_be_future_and_normalizes_to_utc(self):
        now = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
        parsed = parse_schedule_time("2026-10-26T18:30+00:00", now)
        self.assertEqual(parsed, datetime(2026, 10, 26, 18, 30, tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            parse_schedule_time("2026-10-26T11:00+00:00", now)


if __name__ == "__main__":
    unittest.main()
