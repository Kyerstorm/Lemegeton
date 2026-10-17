"""Input checks for Lunar Roles: hex colors and the role name filter (spec §4.1)."""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List, Optional, Sequence, Tuple

NAME_MIN = 1
NAME_MAX = 100
WORD_MAX = 50

# On for every server from the start; admins can switch individual words off.
# Matched as whole words (plurals too), ignoring case, leetspeak and separators.
DEFAULT_PROTECTED_WORDS = (
    "admin", "administrator", "mod", "moderator", "staff", "owner", "dev", "developer",
    "helper", "support", "manager", "booster", "server booster", "nitro", "discord",
    "official", "bot", "verified", "partner", "team",
)

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_SEPARATORS = re.compile(r"[\W_]+")

# Characters that render as nothing but aren't whitespace/format category.
_INVISIBLE_EXTRA = {"ᅟ", "ᅠ", "ㅤ", "ﾠ", "⠀"}

_LEET = str.maketrans({
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b",
    "@": "a", "$": "s", "!": "i", "|": "l",
})


def parse_hex(text: str) -> Optional[int]:
    """Parse #RRGGBB, RRGGBB, #RGB or RGB. Returns None if invalid.

    Discord treats 0 as "no color", so pure black becomes #010101.
    """
    match = _HEX_RE.match((text or "").strip())
    if not match:
        return None
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    value = int(digits, 16)
    return value or 0x010101


def format_hex(value: Optional[int]) -> str:
    return f"#{value:06X}" if value is not None else "none"


def code(text: str) -> str:
    """Wrap user text in inline code. Markdown isn't parsed inside, so only backticks need handling."""
    return f"`{(text or '').replace('`', 'ˋ')}`"


def _is_invisible(ch: str) -> bool:
    return ch.isspace() or ch in _INVISIBLE_EXTRA or unicodedata.category(ch) in {"Cf", "Cc", "Mn", "Me"}


def _visible(text: str) -> str:
    return "".join(ch for ch in text if not _is_invisible(ch))


def normalize(text: str) -> str:
    """Casefold, strip accents and invisible characters, undo common leetspeak."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    kept = "".join(ch for ch in decomposed if ch.isspace() or not _is_invisible(ch))
    return kept.casefold().translate(_LEET)


def _tokens(text: str) -> List[str]:
    return [t for t in _SEPARATORS.split(normalize(text)) if t]


def _merge_single_letters(tokens: Sequence[str]) -> List[str]:
    """['a','d','m','i','n'] -> ['admin'] so spaced/dotted letters are caught."""
    merged, run = [], ""
    for token in tokens:
        if len(token) == 1:
            run += token
            continue
        if run:
            merged.append(run)
            run = ""
        merged.append(token)
    if run:
        merged.append(run)
    return merged


def _token_views(name: str) -> List[List[str]]:
    split = _tokens(name)
    joined_per_word = [t for t in (_SEPARATORS.sub("", w) for w in normalize(name).split()) if t]
    return [split, _merge_single_letters(split), joined_per_word]


def _same_word(token: str, word: str) -> bool:
    return token == word or token == word + "s" or token == word + "es"


def contains_word(name: str, word: str) -> bool:
    """Whole-word (or phrase) match, ignoring case, leetspeak and separators."""
    word_tokens = _tokens(word)
    if not word_tokens:
        return False
    phrase = "".join(word_tokens)
    size = len(word_tokens)
    for view in _token_views(name):
        for i in range(len(view) - size + 1):
            window = view[i:i + size]
            if window[:-1] == word_tokens[:-1] and _same_word(window[-1], word_tokens[-1]):
                return True
        if size > 1 and any(_same_word(t, phrase) for t in view):
            return True
    return False


def _squash(text: str) -> str:
    """Letters and digits only, normalized (catches 'b a d', 'b.a.d', 'b4d')."""
    return "".join(ch for ch in normalize(text) if ch.isalnum())


def clean_word(raw: str) -> Optional[str]:
    """Normalize an admin-entered blocked word; None if unusable."""
    word = " ".join((raw or "").casefold().split())
    if not word or len(word) > WORD_MAX or not _squash(word):
        return None
    return word


def check_role_name(
    raw: str,
    reserved_names: Iterable[str] = (),
    blocked_words: Iterable[str] = (),
    protected_words: Iterable[str] = (),
    protected_role_names: Iterable[str] = (),
) -> Tuple[Optional[str], Optional[str]]:
    """Return (clean_name, None) if allowed, else (None, user-facing reason).

    reserved_names:       names of the server's non-custom roles (exact match refused)
    blocked_words:        admin-added words, refused anywhere in the name
    protected_words:      built-in words like "mod", refused as whole words
    protected_role_names: names of roles with moderation permissions, refused as whole words
    """
    name = " ".join((raw or "").split())
    if not _visible(name):
        return None, "Your role name can't be empty or only invisible characters."
    if len(name) > NAME_MAX:
        return None, f"Role names can be at most {NAME_MAX} characters."

    folded = _visible(name).casefold()
    if "@everyone" in folded or "@here" in folded:
        return None, "Role names can't contain `@everyone` or `@here`."

    normalized = " ".join(_tokens(name))
    for reserved in reserved_names:
        if _visible(reserved).casefold() == folded or (normalized and " ".join(_tokens(reserved)) == normalized):
            return None, f"There's already a server role called **{reserved}**, so you can't use that name."

    for role_name in protected_role_names:
        if len(_squash(role_name)) > 1 and contains_word(name, role_name):
            return None, f"Role names can't include **{role_name}** - that's a staff role in this server."

    for word in protected_words:
        if contains_word(name, word):
            return None, f"Role names can't include the word **{word}**."

    squashed = _squash(name)
    for word in blocked_words:
        word_squashed = _squash(word)
        if word_squashed and word_squashed in squashed:
            return None, "That name contains a blocked word. Please choose another."

    return name, None
