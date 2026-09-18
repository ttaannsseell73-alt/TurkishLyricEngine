"""Orthographic syllable counts, NOT a melody/stress quality score."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re

from .text import LETTERS, VOWELS, lyric_lines, words
from .phonology import articulation


@dataclass(frozen=True)
class ProsodyPolicy:
    target_syllables: int | None = None
    tolerance: int = 1
    long_line_warning: int = 15

    def __post_init__(self) -> None:
        if self.target_syllables is not None and self.target_syllables < 1:
            raise ValueError("target_syllables must be positive or null")
        if self.tolerance < 0 or self.long_line_warning < 1:
            raise ValueError("invalid prosody policy")


def count_syllables(word: str) -> int:
    return sum(char in VOWELS for token in words(word) for char in token)


def analyze_line(line: str, policy: ProsodyPolicy | None = None) -> dict:
    policy = policy or ProsodyPolicy()
    tokens = words(line)
    token_reports = []
    warnings = []
    if re.search(r"\d", line):
        warnings.append("number_pronunciation_unknown")
    for token in tokens:
        count = sum(char in VOWELS for char in token)
        issues = []
        if any(char not in LETTERS and char != "'" for char in token):
            issues.append("foreign_pronunciation_unknown")
        if count == 0:
            issues.append("no_vowel_or_abbreviation")
        if token.replace("'", "") in {"bi", "gelcem", "gidicem", "napıcam", "nolur"}:
            issues.append("colloquial_surface_pronunciation")
        warnings.extend(issues)
        vocal = articulation(token)
        if vocal["consonant_clusters"]:
            warnings.append("difficult_consonant_cluster_review")
        if vocal["long_word_review"]:
            warnings.append("long_word_or_suffix_stack_review")
        token_reports.append({"word": token, "orthographic_syllables": count, "warnings": issues,
                              "articulation": vocal})
    total = sum(t["orthographic_syllables"] for t in token_reports)
    vowel_contacts = [{"left_word": a, "right_word": b, "status": "elision_or_separation_review"}
                      for a, b in zip(tokens, tokens[1:]) if a[-1] in VOWELS and b[0] in VOWELS]
    pronunciation_unknown = bool(set(warnings) & {"number_pronunciation_unknown", "foreign_pronunciation_unknown", "no_vowel_or_abbreviation"})
    if not tokens:
        warnings.append("no_lyric_words")
        pronunciation_unknown = True
    if total >= policy.long_line_warning:
        warnings.append("long_line_review")
    deviation = None if policy.target_syllables is None else total - policy.target_syllables
    if deviation is not None and abs(deviation) > policy.tolerance:
        warnings.append("outside_requested_meter")
    return {
        "text": line,
        "tokens": token_reports,
        "orthographic_syllables": total,
        "pronunciation_status": "uncertain" if pronunciation_unknown else "orthographic_estimate",
        "meter_deviation": deviation,
        "warnings": sorted(set(warnings)),
        "stress_status": "not_evaluated_without_melody",
        "stress_candidates": len([t for t in token_reports if t["orthographic_syllables"]]),
        "vowel_contacts": vowel_contacts,
        "readability": {"words": len(tokens), "clause_boundaries": len(re.findall(r"[,;:.!?]", line)),
                        "words_per_clause": round(len(tokens) / (1 + len(re.findall(r"[,;:.!?]", line))), 2)},
        "articulation_load": {"syllables_per_word": round(total / len(tokens), 3) if tokens else None,
                              "long_word_count": sum(t["articulation"]["long_word_review"] for t in token_reports),
                              "cluster_count": sum(len(t["articulation"]["consonant_clusters"]) for t in token_reports)},
        "word_order_status": "requires_contextual_semantic_critic",
    }


def analyze_text(text: str, policy: ProsodyPolicy | None = None) -> dict:
    policy = policy or ProsodyPolicy()
    lines = [{"line_number": number, **analyze_line(line, policy)} for number, line in lyric_lines(text)]
    counts = [line["orthographic_syllables"] for line in lines]
    return {
        "schema_version": 1,
        "method": "turkish_orthographic_vowel_count",
        "policy": asdict(policy),
        "lines": lines,
        "syllable_range": [min(counts), max(counts)] if counts else None,
        "melodic_prosody_status": "not_evaluated_without_melody",
        "quality_score": None,
    }
