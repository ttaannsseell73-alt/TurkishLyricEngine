"""CSV/TSV/JSONL/text rhyme dictionaries with provenance and optional analyses."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
from pathlib import Path

from .morphology import AnnotationMorphology, AutoMorphology, MorphAnalysis, Segment
from .phonology import near_tail_score, phonemes
from .prosody import count_syllables
from .rhyme import analyze_pair, shared_tail
from .text import LETTERS, lower_tr


@dataclass(frozen=True)
class Lexeme:
    word: str
    source: str
    rights: str = "unknown"
    definition: str = ""
    base_surface: str | None = None
    lemma: str | None = None
    suffixes: tuple[Segment, ...] = ()
    pronunciation: tuple[str, ...] | None = None
    stress_syllable: int | None = None

    def __post_init__(self):
        if not self.word or any(c not in LETTERS for c in self.word) or self.word != lower_tr(self.word):
            raise ValueError("lexicon word must be one normalized Turkish word")
        if not isinstance(self.source, str) or not self.source.strip() or self.rights not in {"owned", "public_domain", "permission", "restricted", "unknown"}:
            raise ValueError("lexicon requires source and valid rights metadata")
        if (self.base_surface is None) != (self.lemma is None):
            raise ValueError("base_surface and lemma must be supplied together")
        if self.base_surface is not None:
            self.analysis()
        elif self.suffixes:
            raise ValueError("suffix segmentation requires a base surface")
        if self.pronunciation is not None:
            phonemes(self.word, list(self.pronunciation))
        if self.stress_syllable is not None and (type(self.stress_syllable) is not int or not 1 <= self.stress_syllable <= count_syllables(self.word)):
            raise ValueError("stress index must be within the word's syllables")

    def analysis(self) -> MorphAnalysis | None:
        if self.base_surface is None:
            return None
        return MorphAnalysis(self.word, self.base_surface, self.lemma or self.base_surface,
                             self.suffixes, "reviewed_lexicon:" + self.source)


class RhymeLexicon:
    def __init__(self, entries: list[Lexeme]):
        self.entries = entries
        self._tails: dict[str, set[int]] = {}
        for i, entry in enumerate(entries):
            for size in range(1, min(8, len(entry.word)) + 1):
                self._tails.setdefault(entry.word[-size:], set()).add(i)
        self.annotations = AnnotationMorphology([analysis for e in entries if (analysis := e.analysis()) is not None])
        self.pronunciations = {e.word: list(e.pronunciation) for e in entries if e.pronunciation}

    @classmethod
    def from_file(cls, path: str | Path, source: str | None = None) -> RhymeLexicon:
        file = Path(path)
        text = file.read_text(encoding="utf-8-sig")
        if file.suffix.lower() in {".csv", ".tsv"}:
            rows = list(csv.DictReader(text.splitlines(), delimiter="\t" if file.suffix.lower() == ".tsv" else ","))
        elif file.suffix.lower() == ".jsonl":
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        elif file.suffix.lower() == ".json":
            rows = json.loads(text)
        else:
            rows = [{"word": line.strip()} for line in text.splitlines() if line.strip()]
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty or invalid rhyme dictionary")
        entries = []
        allowed = set(Lexeme.__dataclass_fields__)
        for number, row in enumerate(rows, 1):
            try:
                if not isinstance(row, dict) or set(row) - allowed:
                    raise ValueError("invalid dictionary fields")
                row = dict(row)
                row["word"] = lower_tr(row["word"].strip())
                row["source"] = row.get("source") or source or str(file.name)
                if isinstance(row.get("suffixes"), str):
                    row["suffixes"] = json.loads(row["suffixes"]) if row["suffixes"] else []
                row["suffixes"] = tuple(Segment(**seg) for seg in row.get("suffixes", []) or [])
                if not row.get("rights"):
                    row["rights"] = "unknown"
                if row.get("pronunciation"):
                    if isinstance(row["pronunciation"], str):
                        row["pronunciation"] = json.loads(row["pronunciation"])
                    row["pronunciation"] = tuple(row["pronunciation"])
                else:
                    row.pop("pronunciation", None)
                if row.get("stress_syllable"):
                    row["stress_syllable"] = int(row["stress_syllable"])
                else:
                    row.pop("stress_syllable", None)
                for nullable in ("base_surface", "lemma"):
                    if row.get(nullable) == "":
                        row.pop(nullable)
                entries.append(Lexeme(**row))
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(f"invalid dictionary entry {number}: {exc}") from exc
        return cls(entries)

    def family(self, word: str, *, syllables: int | None = None, limit: int = 20, near: bool = True) -> list[dict]:
        token = lower_tr(word)
        if not token or any(c not in LETTERS for c in token) or not 1 <= limit <= 100:
            raise ValueError("invalid rhyme query or result bound")
        if syllables is not None and (type(syllables) is not int or syllables < 1):
            raise ValueError("syllable filter must be positive")
        candidates = set(self._tails.get(token[-1:], set()))
        # Near matches differ at the final phoneme, so they need a broader scan.
        if near:
            candidates.update(range(len(self.entries)))
        provider = AutoMorphology(self.annotations, use_zeyrek=False)
        query = next((entry for entry in self.entries if entry.word == token), None)
        query_phones = phonemes(token, list(query.pronunciation) if query and query.pronunciation else None)["phonemes"]
        results = []
        for i in sorted(candidates):
            entry = self.entries[i]
            if entry.word == token or (syllables is not None and count_syllables(entry.word) != syllables):
                continue
            analysis = analyze_pair(token, entry.word, provider, pronunciations=self.pronunciations)
            if analysis["status"] == "redif_only":
                continue
            tail = shared_tail(token, entry.word)
            candidate_phones = phonemes(entry.word, list(entry.pronunciation) if entry.pronunciation else None)["phonemes"]
            proximity = near_tail_score(query_phones, candidate_phones)
            if not tail and (not near or proximity < .75):
                continue
            results.append({"word": entry.word, "syllables": count_syllables(entry.word), "definition": entry.definition,
                            "source": entry.source, "rights": entry.rights, "analysis": analysis,
                            "surface_shared_tail": tail, "near_phonetic_score": proximity,
                            "pronunciation_status": "supplied" if entry.pronunciation else "estimated"})
        results.sort(key=lambda r: (-(r["analysis"]["status"] == "base_ending_match"),
                                  -len(r["analysis"]["base_tail"]), -len(r["surface_shared_tail"]),
                                  -r["near_phonetic_score"], r["word"]))
        return results[:limit]
