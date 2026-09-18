"""Strict generation contracts and immutable locks; no untyped model output."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any

from .meter import MeterSpec
from .text import lexical_key, words

FORM = (("verse1", 4), ("prechorus", 2), ("chorus", 4), ("verse2", 4), ("prechorus2", 2),
        ("chorus2", 4), ("bridge", 2), ("final_chorus", 4))
DEFAULT_AVOID = ("gece", "duvar", "sokak", "perde", "sigara", "tavan", "boş oda", "nefes",
                 "kalp", "gözyaşı", "kader", "aşk acısı")


def fingerprint(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def string(value: Any, name: str, maximum: int = 2000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be a non-empty string <= {maximum} characters")
    return value.strip()


def exact_fields(value: Any, fields: set[str], name: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{name} has invalid fields; expected {sorted(fields)}")
    return value


def object_schema(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


TEXT = {"type": "string"}
CONCEPT_SCHEMA = object_schema({"id": TEXT, "angle": TEXT, "conflict": TEXT, "turn": TEXT, "mechanism_id": TEXT})
HOOK_SCHEMA = object_schema({"id": TEXT, "concept_id": TEXT, "text": TEXT})
IDEAS_SCHEMA = object_schema({"concepts": {"type": "array", "items": CONCEPT_SCHEMA}})
HOOKS_SCHEMA = object_schema({"hooks": {"type": "array", "items": HOOK_SCHEMA}})
RANK_SCHEMA = object_schema({"rankings": {"type": "array", "items": object_schema({
    "id": TEXT, "score": {"type": "integer"}, "reason": TEXT})}})
STORY_SCHEMA = object_schema({"concept_id": TEXT, "hook_id": TEXT, "arc": TEXT,
    "beats": {"type": "array", "items": object_schema({"section_id": TEXT, "purpose": TEXT, "change": TEXT})}})
SONG_SCHEMA = object_schema({"concept_id": TEXT, "hook_id": TEXT, "story_hash": TEXT, "title": TEXT,
    "sections": {"type": "array", "items": object_schema({"id": TEXT, "lines": {"type": "array", "items": TEXT}})}})
CRITIC_SCHEMA = object_schema({"dimensions": object_schema({name: {"type": "integer"} for name in (
    "idea_adherence", "natural_turkish", "emotional_progression", "hook_strength", "register_consistency",
    "originality", "singability_text")}), "rationale": TEXT,
    "issues": {"type": "array", "items": object_schema({"section_id": TEXT, "line": {"type": "integer"},
        "reason": TEXT, "suggestion": TEXT})}})
PATCH_SCHEMA = object_schema({"patches": {"type": "array", "items": object_schema({
    "section_id": TEXT, "line": {"type": "integer"}, "text": TEXT})}})


@dataclass(frozen=True)
class Brief:
    theme: str
    genre: str = "Türkçe pop ballad"
    mood: str = "dokunaklı, doğal, güçlü"
    meter: int | None = None
    durak: tuple[int, ...] | None = None
    rhyme_scheme: str = "free"
    max_chars: int = 5000
    concept_count: int = 20
    hook_count: int = 50
    writer_count: int = 3
    max_rounds: int = 6
    target_score: int = 80
    max_calls: int = 40
    avoid: tuple[str, ...] = DEFAULT_AVOID
    prefer_nonverb_endings: bool = True

    def __post_init__(self):
        string(self.theme, "theme", 1000)
        string(self.genre, "genre", 100)
        string(self.mood, "mood", 300)
        MeterSpec(self.meter, self.durak)
        for name, low, high in (("max_chars", 200, 5000), ("concept_count", 1, 40), ("hook_count", 1, 100),
                               ("writer_count", 1, 5), ("max_rounds", 0, 6), ("target_score", 0, 100), ("max_calls", 1, 100)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer in [{low}, {high}]")
        if self.rhyme_scheme not in {"free", "AABB", "ABAB", "ABCB"}:
            raise ValueError("unsupported rhyme scheme")
        if type(self.prefer_nonverb_endings) is not bool:
            raise ValueError("prefer_nonverb_endings must be a boolean")
        if not isinstance(self.avoid, (tuple, list)):
            raise ValueError("avoid must be a phrase array")
        for item in self.avoid:
            string(item, "avoid item", 100)
        object.__setattr__(self, "avoid", tuple(self.avoid))
        if self.durak is not None:
            object.__setattr__(self, "durak", tuple(self.durak))

    def to_dict(self) -> dict:
        return asdict(self)


def validate_candidates(payload: dict, key: str, count: int, mechanism_ids: set[str] | None = None,
                        concept_id: str | None = None) -> list[dict]:
    exact_fields(payload, {key}, key)
    rows = payload[key]
    if not isinstance(rows, list) or len(rows) != count:
        raise ValueError(f"{key} requires exactly {count} candidates")
    ids, texts = set(), set()
    for row in rows:
        expected = {"id", "angle", "conflict", "turn", "mechanism_id"} if key == "concepts" else {"id", "concept_id", "text"}
        exact_fields(row, expected, key)
        for name, value in row.items():
            string(value, name, 800)
        if row["id"] in ids:
            raise ValueError("duplicate candidate ID")
        ids.add(row["id"])
        if key == "concepts":
            if row["mechanism_id"] not in (mechanism_ids or set()):
                raise ValueError("unknown mechanism ID")
            signature = lexical_key(row["angle"])
        else:
            if row["concept_id"] != concept_id:
                raise ValueError("hook violated concept lock")
            signature = lexical_key(row["text"])
            if not 4 <= len(words(row["text"])) <= 7:
                raise ValueError("hook must contain 4–7 words")
        if not signature or signature in texts:
            raise ValueError("duplicate or empty candidate text")
        texts.add(signature)
    return rows


def validate_rankings(payload: dict, candidates: list[dict]) -> list[dict]:
    exact_fields(payload, {"rankings"}, "rankings")
    rows = payload["rankings"]
    ids = {candidate["id"] for candidate in candidates}
    if not isinstance(rows, list) or len(rows) != len(ids):
        raise ValueError("judge must evaluate every candidate exactly once")
    seen = set()
    for row in rows:
        exact_fields(row, {"id", "score", "reason"}, "ranking")
        if row["id"] not in ids or row["id"] in seen:
            raise ValueError("judge returned unknown or duplicate candidate ID")
        if type(row["score"]) is not int or not 0 <= row["score"] <= 100:
            raise ValueError("judge score outside [0,100]")
        string(row["reason"], "judge reason")
        seen.add(row["id"])
    return sorted(rows, key=lambda row: (-row["score"], row["id"]))


def validate_story(payload: dict, concept: dict, hook: dict) -> dict:
    exact_fields(payload, {"concept_id", "hook_id", "arc", "beats"}, "story")
    if payload["concept_id"] != concept["id"] or payload["hook_id"] != hook["id"]:
        raise ValueError("story violated concept/hook lock")
    string(payload["arc"], "arc")
    beats = payload["beats"]
    if not isinstance(beats, list) or [beat.get("section_id") for beat in beats if isinstance(beat, dict)] != ["verse1", "prechorus", "verse2", "prechorus2", "bridge"]:
        raise ValueError("story must progress through verses, prechoruses and bridge")
    for beat in beats:
        exact_fields(beat, {"section_id", "purpose", "change"}, "beat")
        string(beat["purpose"], "purpose")
        string(beat["change"], "change")
    return payload


def render_song(song: dict) -> str:
    labels = {"verse1": "Verse 1", "verse2": "Verse 2", "prechorus": "Pre-Chorus", "prechorus2": "Pre-Chorus", "chorus": "Chorus", "chorus2": "Chorus",
              "bridge": "Bridge", "final_chorus": "Chorus"}
    return "\n\n".join("[" + labels[section["id"]] + "]\n" + "\n".join(section["lines"]) for section in song["sections"])


def validate_song(payload: dict, concept: dict, hook: dict, story: dict, max_chars: int = 5000) -> dict:
    exact_fields(payload, {"concept_id", "hook_id", "story_hash", "title", "sections"}, "song")
    if (payload["concept_id"], payload["hook_id"], payload["story_hash"]) != (concept["id"], hook["id"], fingerprint(story)):
        raise ValueError("song violated concept/hook/story lock")
    string(payload["title"], "title", 100)
    sections = payload["sections"]
    if not isinstance(sections, list) or len(sections) != len(FORM):
        raise ValueError("song must contain the locked V4-P2-C4-V4-P2-C4-B2-C4 form")
    for section, (section_id, length) in zip(sections, FORM):
        exact_fields(section, {"id", "lines"}, "section")
        if section["id"] != section_id or not isinstance(section["lines"], list) or len(section["lines"]) != length:
            raise ValueError("invalid section order or line count")
        for line in section["lines"]:
            string(line, "lyric line", 250)
            if "\n" in line or "\r" in line or "[" in line or "]" in line or not words(line):
                raise ValueError("invalid lyric line")
    chorus = sections[2]["lines"]
    if chorus[0] != hook["text"] or sections[5]["lines"] != chorus or sections[7]["lines"] != chorus:
        raise ValueError("chorus hook/repetition lock violated")
    if len(render_song(payload)) > max_chars:
        raise ValueError("rendered lyric exceeds max_chars")
    return payload
