"""Phrase-level cliché evidence, corpus document frequency and contextual caution."""

from __future__ import annotations

from collections import Counter

from .contracts import DEFAULT_AVOID
from .text import lexical_key, lyric_lines, words

SEED_PHRASES = ("kalbim paramparça", "sensiz geceler", "içimde bir yangın", "kaderin oyunu",
                "gözyaşlarım sel oldu", "sensiz bir hiçim", "yarım kalan hikaye", "seni unutamıyorum")


class ClicheDetector:
    def __init__(self, store=None):
        self.phrases = {lexical_key(phrase): {"source": "editorial_seed", "frequency": None} for phrase in SEED_PHRASES}
        self.reference_documents = 0
        if store is not None:
            documents = store.documents()
            self.reference_documents = len(documents)
            frequency = Counter()
            for document in documents:
                found = set()
                for _, line in lyric_lines(document["text"]):
                    tokens = words(line)
                    found.update(" ".join(tokens[i:i+n]) for n in range(2, 6) for i in range(max(0, len(tokens)-n+1)))
                frequency.update(found)
            for phrase, count in frequency.items():
                ratio = count / len(documents) if documents else 0
                if count >= 3 and ratio >= .05:
                    self.phrases[phrase] = {"source": "corpus_document_frequency", "frequency": count,
                                           "document_fraction": ratio}

    def analyze(self, text: str, avoid: tuple[str, ...] = DEFAULT_AVOID) -> dict:
        matches, preference_hits = [], []
        tokens_total = 0
        for number, line in lyric_lines(text):
            token_list = words(line)
            tokens_total += len(token_list)
            normalized = " " + " ".join(token_list) + " "
            contextual_turn = any(t in token_list for t in {"değil", "artık", "oysa", "meğer"})
            for phrase, info in sorted(self.phrases.items()):
                occurrences = normalized.count(" " + phrase + " ")
                if occurrences:
                    matches.append({"line": number, "phrase": phrase, "occurrences": occurrences, **info,
                                    "context": "possible_subversion_requires_critic" if contextual_turn else "unresolved_context",
                                    "weight": .4 if contextual_turn else 1.0})
            for phrase in avoid:
                if " " + lexical_key(phrase) + " " in normalized:
                    preference_hits.append({"line": number, "phrase": phrase})
        weighted = sum(len(words(m["phrase"])) * m["occurrences"] * m["weight"] for m in matches)
        return {"matches": matches, "density_candidate": round(min(1.0, weighted / max(1, tokens_total)), 4),
                "preference_hits": preference_hits, "reference_documents": self.reference_documents,
                "decision": "evidence_for_contextual_critic_not_automatic_blacklist"}
