"""Explicit surface segmentations; unknown/ambiguous analysis stays unknown.

V1 consumes reviewed annotations. No inferred suffix chopping, no first-parse
selection. An external analyser may later supply multiple candidate analyses.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from importlib.metadata import PackageNotFoundError, version
from typing import Protocol

from .text import LETTERS, lower_tr, normalize_text, words


@dataclass(frozen=True)
class Segment:
    surface: str
    function: str


@dataclass(frozen=True)
class MorphAnalysis:
    word: str
    base_surface: str
    lemma: str
    suffixes: tuple[Segment, ...]
    evidence: str

    def __post_init__(self) -> None:
        fields = [self.word, self.base_surface, self.lemma, self.evidence]
        if any(not isinstance(value, str) or not value.strip() for value in fields):
            raise ValueError("morphology fields must be non-empty strings")
        if self.word != lower_tr(self.word) or self.base_surface != lower_tr(self.base_surface):
            raise ValueError("word/base must use normalized Turkish lower case")
        if any(c not in LETTERS for c in self.word + self.base_surface):
            raise ValueError("only single Turkish surface words are supported")
        for seg in self.suffixes:
            if not seg.surface or not seg.function.strip() or any(c not in LETTERS for c in seg.surface):
                raise ValueError("suffix needs a Turkish surface and a grammatical function")
        if self.base_surface + "".join(s.surface for s in self.suffixes) != self.word:
            raise ValueError("surface segmentation must reconstruct the word exactly")


class MorphologyProvider(Protocol):
    def analyze(self, word: str) -> tuple[MorphAnalysis, ...]: ...


class AnnotationMorphology:
    def __init__(self, analyses: list[MorphAnalysis] | None = None):
        self._entries: dict[str, list[MorphAnalysis]] = {}
        for analysis in analyses or []:
            bucket = self._entries.setdefault(analysis.word, [])
            if analysis not in bucket:
                bucket.append(analysis)

    def analyze(self, word: str) -> tuple[MorphAnalysis, ...]:
        return tuple(self._entries.get(lower_tr(normalize_text(word)), []))

    @classmethod
    def from_file(cls, path: str | Path) -> AnnotationMorphology:
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError("morphology annotations must be a JSON array")
        analyses = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("invalid morphology annotation")
            try:
                suffixes = tuple(Segment(**seg) for seg in row["suffixes"])
                analyses.append(MorphAnalysis(
                    word=row["word"], base_surface=row["base_surface"],
                    lemma=row["lemma"], suffixes=suffixes, evidence=row["evidence"]))
            except (KeyError, TypeError) as exc:
                raise ValueError("invalid morphology annotation fields") from exc
        return cls(analyses)


class ZeyrekMorphology:
    """Pinned 0.1.3 adapter; intentionally isolates the internal surface API.

    Zeyrek's public Parse loses segment surfaces. Its rule-based single-word
    API supplies them without downloading sentence tokenizers. Private API use
    is version-guarded and covered by real integration regression cases.
    Ambiguity is preserved, never resolved by choosing the first parse.
    """

    def __init__(self):
        try:
            installed = version("zeyrek")
        except PackageNotFoundError as exc:
            raise ValueError("Zeyrek unavailable; install the [morphology] extra or use annotations") from exc
        if installed != "0.1.3":
            raise ValueError(f"Zeyrek adapter requires 0.1.3; found {installed}")
        import zeyrek
        self._analyzer = zeyrek.MorphAnalyzer()
        self._cache: dict[str, tuple[MorphAnalysis, ...]] = {}

    def analyze(self, word: str) -> tuple[MorphAnalysis, ...]:
        token = lower_tr(normalize_text(word))
        if token in self._cache:
            return self._cache[token]
        if not token or any(c not in LETTERS for c in token):
            return ()
        # Circumflex and apostrophe normalization could change the rhyme sound;
        # refuse an altered reconstruction rather than implicitly flattening it.
        analyses = []
        for candidate in self._analyzer._parse(token):
            morphemes = candidate.morphemes
            if not morphemes:
                continue
            base = morphemes[0][1]
            suffixes = []
            # Keep zero-surface grammatical transitions attached to the next
            # surface affix. E.g. possession and nominal predication differ.
            context = []
            for morpheme, surface in morphemes[1:]:
                context.append(morpheme.id_)
                if surface:
                    suffixes.append(Segment(surface=surface, function="/".join(context)))
                    context = []
            if context and suffixes:
                last = suffixes[-1]
                suffixes[-1] = Segment(last.surface, last.function + "/" + "/".join(context))
            if base + "".join(seg.surface for seg in suffixes) != token:
                continue
            try:
                analysis = MorphAnalysis(token, base, lower_tr(candidate.dict_item.lemma),
                    tuple(suffixes), f"zeyrek:0.1.3:{candidate.dict_item.lemma}:{candidate.pos.value}")
            except ValueError:
                continue
            if analysis not in analyses:
                analyses.append(analysis)
        self._cache[token] = tuple(analyses)
        return self._cache[token]
