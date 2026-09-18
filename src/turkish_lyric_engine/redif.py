"""Redif requires equivalent affix surface AND grammatical function."""
from dataclasses import asdict


def strip_equivalent_suffixes(left, right):
    removed = []
    for a, b in zip(reversed(left.suffixes), reversed(right.suffixes)):
        if a != b:
            break
        removed.append(a)
    segments = list(reversed(removed))
    surface = "".join(segment.surface for segment in segments)
    return {"surface": surface, "segments": [asdict(s) for s in segments],
            "left_residual": left.word[:-len(surface)] if surface else left.word,
            "right_residual": right.word[:-len(surface)] if surface else right.word,
            "all_suffixes_removed": len(removed) == len(left.suffixes) == len(right.suffixes)}


def analyze_redif(left_line, right_line, provider=None):
    from .rhyme import analyze_pair
    result = analyze_pair(left_line, right_line, provider)
    return {name: result.get(name) for name in ("status", "reason", "word_redif", "word_redif_status",
            "suffix_redif", "redif_segments", "repeated_words", "morphology_candidate_counts", "evidence")}
