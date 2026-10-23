"""Cryptographically secure random selection helpers for Lemegeton.

Each draw starts with fresh operating-system CSPRNG entropy, hashes it with
SHA-512, and uses rejection sampling to avoid modulo bias.
"""
import hashlib
import secrets
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")
_SHA512_MAX = 1 << (hashlib.sha512().digest_size * 8)


def secure_randbelow(upper_bound: int) -> int:
    """Return an unbiased integer in range(upper_bound) using SHA-512 and OS entropy."""
    if not isinstance(upper_bound, int) or isinstance(upper_bound, bool) or upper_bound <= 0:
        raise ValueError("upper_bound must be a positive integer")
    if upper_bound > _SHA512_MAX:
        raise ValueError("upper_bound cannot exceed the SHA-512 output range")
    if upper_bound == 1:
        return 0

    bit_length = (upper_bound - 1).bit_length()
    byte_length = (bit_length + 7) // 8
    mask = (1 << bit_length) - 1

    while True:
        entropy = secrets.token_bytes(64)
        digest = hashlib.sha512(b"Lemegeton.Random.v1\x00" + entropy).digest()
        candidate = int.from_bytes(digest[:byte_length], "big") & mask
        if candidate < upper_bound:
            return candidate


def secure_choice(items: Sequence[T]) -> T:
    """Select one item uniformly using the SHA-512-backed secure integer helper."""
    if not items:
        raise IndexError("Cannot choose from an empty sequence")
    return items[secure_randbelow(len(items))]
