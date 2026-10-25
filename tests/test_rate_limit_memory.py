"""Regression tests for bounded in-memory rate-limit tracking."""
import unittest
from collections import deque

from web.rate_limit_memory import record_event


class RateLimitMemoryTests(unittest.TestCase):
    def test_rotating_keys_cannot_grow_tracking_map_without_bound(self):
        buckets = {}
        for index in range(5000):
            record_event(buckets, f"client-{index}", 600, 10.0, 32)
        self.assertLessEqual(len(buckets), 32)
        self.assertIn("client-4999", buckets)

    def test_expired_entries_are_removed_before_active_entries(self):
        buckets = {"expired": deque([1.0]), "active": deque([9.0])}
        record_event(buckets, "new", 5, 10.0, 2)
        self.assertEqual(set(buckets), {"active", "new"})

    def test_tracking_keeps_at_least_one_bucket_for_zero_config(self):
        buckets = {"previous": deque([9.0])}
        record_event(buckets, "new", 60, 10.0, 0)
        self.assertEqual(set(buckets), {"new"})
        self.assertEqual(list(buckets["new"]), [10.0])


if __name__ == "__main__":
    unittest.main()
