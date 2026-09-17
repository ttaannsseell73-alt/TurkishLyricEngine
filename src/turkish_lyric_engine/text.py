"""Turkish Unicode handling. Case-folding must preserve dotted/dotless I."""

from __future__ import annotations

import re
import unicodedata

VOWELS = frozenset("aeıioöuüâîû")
LETTERS = frozenset("abcçdefgğhıijklmnoöprsştuüvyzâîû")
WORD_RE = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*", re.UNICODE)
HEADER_RE = re.compile(
    r"^(?:verse(?:\s*\d+)?|chorus|pre[ -]?chorus|bridge|intro|outro|"
    r"kıta(?:\s*\d+)?|nakarat|köprü|giriş|çıkış|bölüm(?:\s*\d+)?|instrumental)$"
)


def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    for old in ("’", "‘", "ʼ"):
        text = text.replace(old, "'")
    text = text.replace("\ufeff", "").replace("\u200b", "")
    return "\n".join(" ".join(line.split()) for line in text.split("\n")).strip()


def lower_tr(text: str) -> str:
    return unicodedata.normalize("NFC", text).translate(str.maketrans({"I": "ı", "İ": "i"})).lower()


def words(text: str) -> list[str]:
    return WORD_RE.findall(lower_tr(normalize_text(text)))


def is_header(line: str) -> bool:
    stripped = lower_tr(line).strip()
    # Only recognised labels disappear; bracketed lyric content stays intact.
    if stripped.startswith("[") and stripped.endswith("]"):
        stripped = stripped[1:-1].strip()
    elif stripped.endswith(":"):
        stripped = stripped[:-1].strip()
    else:
        return False
    return HEADER_RE.fullmatch(stripped) is not None


def lyric_lines(text: str) -> list[tuple[int, str]]:
    return [(i, line) for i, line in enumerate(normalize_text(text).split("\n"), 1)
            if line and not is_header(line)]


def canonical_lyric(text: str) -> str:
    """Ignore section labels/spacing, preserve stanza content and repetition."""
    return "\n".join(line for _, line in lyric_lines(text))


def lexical_key(text: str) -> str:
    return " ".join(words(text))
