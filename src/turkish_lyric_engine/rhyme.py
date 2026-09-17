"""Separate repetition/redif from base endings, exposing evidence limitations."""

from __future__ import annotations

from .morphology import AnnotationMorphology, MorphologyProvider
from .text import words


def shared_tail(a: str, b: str) -> str:
    length = 0
    for left, right in zip(reversed(a), reversed(b)):
        if left != right:
            break
        length += 1
    return a[len(a) - length:] if length else ""


def analyze_pair(left_line: str, right_line: str, provider: MorphologyProvider | None = None) -> dict:
    provider = provider or AnnotationMorphology()
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
    candidates_a, candidates_b = provider.analyze(a), provider.analyze(b)
    result["morphology_candidate_counts"] = [len(candidates_a), len(candidates_b)]
    if len(candidates_a) != 1 or len(candidates_b) != 1:
        result["reason"] = "missing_or_ambiguous_morphology"
        return result
    parsed_a, parsed_b = candidates_a[0], candidates_b[0]
    result["evidence"] = [parsed_a.evidence, parsed_b.evidence]
    # A repeated affix is redif only when its surface AND function match.
    removed = []
    for sa, sb in zip(reversed(parsed_a.suffixes), reversed(parsed_b.suffixes)):
        if sa != sb:
            break
        removed.append(sa.surface)
    redif = "".join(reversed(removed))
    result["redif_surface"] = redif
    result["suffix_redif"] = redif
    residual_a = a[:-len(redif)] if redif else a
    residual_b = b[:-len(redif)] if redif else b
    # Remaining affixes are not root evidence. V1 refuses partial stripping.
    if len(removed) != len(parsed_a.suffixes) or len(removed) != len(parsed_b.suffixes):
        result["reason"] = "remaining_non_equivalent_suffixes"
        return result
    tail = shared_tail(residual_a, residual_b)
    result["base_tail"] = tail
    if tail:
        result["status"] = "base_ending_match"
        result["rhyme_class_candidate"] = "yarım" if len(tail) == 1 else "tam" if len(tail) == 2 else "zengin"
    elif redif or repeated:
        result["status"] = "redif_only"
    else:
        result["status"] = "no_base_ending_match"
    result["reason"] = "reviewed_surface_analyses"
    return result
