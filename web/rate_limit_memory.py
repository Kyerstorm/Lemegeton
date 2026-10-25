"""Bound memory used by per-client rate-limit tracking maps."""
from collections import deque
from typing import Deque, Dict, Hashable


def record_event(buckets: Dict[Hashable, Deque[float]], key: Hashable, window: float,
                 now: float, max_tracked: int) -> None:
    """Append an event while keeping the tracking map bounded under rotating-key floods.

    Expired entries are reclaimed first. If all entries are still active, the least-recently
    used key is evicted; callers must pair this memory bound with an upstream/global limit.
    """
    bucket = buckets.get(key)
    if bucket is None:
        limit = max(1, max_tracked)
        if len(buckets) >= limit:
            cutoff = now - window
            stale = [candidate for candidate, events in buckets.items()
                     if not events or events[-1] <= cutoff]
            for candidate in stale:
                del buckets[candidate]
        if len(buckets) >= limit:
            oldest = min(buckets, key=lambda candidate: buckets[candidate][-1] if buckets[candidate] else 0)
            del buckets[oldest]
        bucket = buckets.setdefault(key, deque())
    bucket.append(now)
