"""Transparent lexical baseline, not a copyright verdict or semantic guard."""

from __future__ import annotations

from difflib import SequenceMatcher

from .corpus import CorpusStore
from .text import lexical_key, lyric_lines, words


def ngrams(tokens: list[str], n: int = 3) -> set[tuple[str, ...]]:
    if n < 1:
        raise ValueError("ngram size must be positive")
    return {tuple(tokens[i:i + n]) for i in range(max(0, len(tokens) - n + 1))}


def jaccard(left: set, right: set) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def compare_texts(candidate: str, reference: str) -> dict:
    left, right = words(candidate), words(reference)
    left_lines = [lexical_key(line) for _, line in lyric_lines(candidate)]
    right_lines = [lexical_key(line) for _, line in lyric_lines(reference)]
    # Ignore section headers consistently for all metrics.
    left = " ".join(left_lines).split()
    right = " ".join(right_lines).split()
    best = {"candidate_line": None, "reference_line": None, "ratio": 0.0,
            "candidate_words": 0, "reference_words": 0}
    for i, a in enumerate(left_lines, 1):
        for j, b in enumerate(right_lines, 1):
            ratio = SequenceMatcher(None, a.split(), b.split(), autojunk=False).ratio()
            if ratio > best["ratio"]:
                best = {"candidate_line": i, "reference_line": j, "ratio": round(ratio, 6),
                        "candidate_words": len(a.split()), "reference_words": len(b.split())}
    return {
        "exact_document_match": bool(left) and left_lines == right_lines,
        "trigram_jaccard": round(jaccard(ngrams(left), ngrams(right)), 6),
        "token_sequence_ratio": round(SequenceMatcher(None, left, right, autojunk=False).ratio(), 6),
        "best_line_match": best,
    }


def check_corpus(text: str, store: CorpusStore, *, top_k: int = 5) -> dict:
    if top_k < 1 or top_k > 100:
        raise ValueError("top_k must be between 1 and 100")
    if not words(text):
        raise ValueError("candidate contains no words")
    matches = []
    for document in store.documents():
        metrics = compare_texts(text, document["text"])
        matches.append({"content_hash": document["content_hash"], "metrics": metrics,
                        "provenance": store.provenance(document["content_hash"])})
    matches.sort(key=lambda item: (-int(item["metrics"]["exact_document_match"]),
                 -item["metrics"]["best_line_match"]["ratio"],
                 -item["metrics"]["trigram_jaccard"], item["content_hash"]))
    return {
        "schema_version": 1,
        "status": "checked_lexical_baseline" if matches else "not_checked_empty_corpus",
        "reference_documents": len(matches),
        "matches": matches[:top_k],
        "semantic_similarity_status": "not_evaluated",
        "copyright_verdict": None,
        "limitations": ["only_supplied_corpus", "thresholds_not_calibrated", "lexical_overlap_not_legal_verdict"],
    }
