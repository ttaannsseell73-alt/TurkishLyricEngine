"""Separate repetition/redif from base endings, exposing evidence limitations."""

from __future__ import annotations

from .morphology import AnnotationMorphology, MorphologyProvider
from .text import words
from .phonology import near_tail_score, phonemes, tail_match
from .redif import strip_equivalent_suffixes


def shared_tail(a: str, b: str) -> str:
    length = 0
    for left, right in zip(reversed(a), reversed(b)):
        if left != right:
            break
        length += 1
    return a[len(a) - length:] if length else ""


def analyze_pair(left_line: str, right_line: str, provider: MorphologyProvider | None = None,
                 *, pronunciations: dict[str, list[str]] | None = None) -> dict:
    provider = provider or AnnotationMorphology()
    pronunciations = pronunciations or {}
    left, right = words(left_line), words(right_line)
    result = {
        "left_ending": left[-1] if left else None,
        "right_ending": right[-1] if right else None,
        "repeated_words": [],
        "redif_surface": "",
        "base_tail": "",
        "surface_tail": "",
        "status": "unresolved",
        "method": "orthographic_surface_segmentation",
        "phonetic_status": "not_evaluated",
        "evidence": [],
        "word_redif": "",
        "suffix_redif": "",
        "rhyme_class_candidate": None,
        "word_redif_status": "none",
        "morphology_candidate_counts": [0, 0],
    }
    if not left or not right:
        result["reason"] = "missing_ending"
        return result
    repeated = []
    while left and right and left[-1] == right[-1]:
        repeated.append(left.pop())
        right.pop()
    result["repeated_words"] = list(reversed(repeated))
    result["word_redif"] = " ".join(result["repeated_words"])
    if repeated:
        result["word_redif_status"] = "candidate_requires_same_meaning_and_function"
    if not left or not right:
        result.update(status="repetition_only", reason="no_distinct_ending_before_repetition")
        return result
    a, b = left[-1], right[-1]
    result["surface_tail"] = shared_tail(a, b)
    surface_a, surface_b = phonemes(a, pronunciations.get(a)), phonemes(b, pronunciations.get(b))
    result["surface_phonetic_candidate"] = {
        "left": surface_a, "right": surface_b,
        "shared_phonemes": tail_match(surface_a["phonemes"], surface_b["phonemes"]),
        "near_tail_score": near_tail_score(surface_a["phonemes"], surface_b["phonemes"]),
        "redif_not_removed": True,
    }
    candidates_a, candidates_b = provider.analyze(a), provider.analyze(b)
    result["morphology_candidate_counts"] = [len(candidates_a), len(candidates_b)]
    if len(candidates_a) != 1 or len(candidates_b) != 1:
        result["reason"] = "missing_or_ambiguous_morphology"
        return result
    parsed_a, parsed_b = candidates_a[0], candidates_b[0]
    result["evidence"] = [parsed_a.evidence, parsed_b.evidence]
    # A repeated affix is redif only when its surface AND function match.
    separation = strip_equivalent_suffixes(parsed_a, parsed_b)
    redif = separation["surface"]
    result["redif_segments"] = separation["segments"]
    result["redif_surface"] = redif
    result["suffix_redif"] = redif
    residual_a, residual_b = separation["left_residual"], separation["right_residual"]
    # Remaining affixes are not root evidence. V1 refuses partial stripping.
    if not separation["all_suffixes_removed"]:
        result["reason"] = "remaining_non_equivalent_suffixes"
        return result
    tail = shared_tail(residual_a, residual_b)
    result["base_tail"] = tail
    phones_a, phones_b = phonemes(residual_a, pronunciations.get(residual_a)), phonemes(residual_b, pronunciations.get(residual_b))
    common_phones = tail_match(phones_a["phonemes"], phones_b["phonemes"])
    result["phonetic_analysis"] = {"left": phones_a, "right": phones_b, "shared_phonemes": common_phones,
                                  "near_tail_score": near_tail_score(phones_a["phonemes"], phones_b["phonemes"])}
    result["phonetic_status"] = "supplied_base_pronunciations" if residual_a in pronunciations and residual_b in pronunciations else "grapheme_to_phoneme_estimate_or_partial_override"
    if common_phones:
        result["status"] = "base_ending_match"
        short, long = sorted((phones_a["phonemes"], phones_b["phonemes"]), key=len)
        result["rhyme_class_candidate"] = ("tunç" if len(short) >= 2 and short != long and long[-len(short):] == short else
                                            "yarım" if len(common_phones) == 1 else "tam" if len(common_phones) == 2 else "zengin")
    elif redif or repeated:
        result["status"] = "redif_only"
    else:
        result["status"] = "no_base_ending_match"
        if result["phonetic_analysis"]["near_tail_score"] >= 0.75 and min(len(phones_a["phonemes"]), len(phones_b["phonemes"])) >= 3:
            result["rhyme_class_candidate"] = "yakın"
            result["status"] = "near_phonetic_candidate"
    result["reason"] = "reviewed_surface_analyses"
    return result
