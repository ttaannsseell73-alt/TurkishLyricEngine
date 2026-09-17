"""Hece vezni and word-boundary durak checks; aruz is a separate future stage."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import accumulate

from .prosody import analyze_line
from .text import lyric_lines

COMMON_DURAKS = {
    7: ((4, 3),),
    8: ((4, 4),),
    11: ((6, 5), (4, 4, 3)),
    14: ((7, 7),),
}


@dataclass(frozen=True)
class MeterSpec:
    syllables: int | None = None
    durak: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if self.syllables is not None and (type(self.syllables) is not int or self.syllables < 1):
            raise ValueError("meter must be a positive integer or null (free verse)")
        if self.durak is not None:
            if self.syllables is None:
                raise ValueError("durak requires a fixed syllable meter")
            if len(self.durak) < 2 or any(type(p) is not int or p < 1 for p in self.durak):
                raise ValueError("durak needs at least two positive integer parts")
            if sum(self.durak) != self.syllables:
                raise ValueError("durak parts must sum to the requested meter")


def parse_durak(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(piece.strip()) for piece in value.split("+"))
    except ValueError as exc:
        raise ValueError("durak must be e.g. 6+5 or 4+4+3") from exc


def scan_durak(line: str, parts: tuple[int, ...]) -> dict:
    report = analyze_line(line)
    counts = [token["orthographic_syllables"] for token in report["tokens"]]
    boundaries = list(accumulate(counts))
    cuts = list(accumulate(parts))[:-1]
    unknown = report["pronunciation_status"] == "uncertain"
    matching_total = sum(counts) == sum(parts)
    missing = [cut for cut in cuts if cut not in boundaries]
    groups = []
    if matching_total and not missing and not unknown:
        start = 0
        for endpoint in accumulate(parts):
            end = boundaries.index(endpoint) + 1
            groups.append(" ".join(token["word"] for token in report["tokens"][start:end]))
            start = end
    return {
        "pattern": list(parts),
        "status": "uncertain" if unknown else
                  "compatible_word_boundaries" if matching_total and not missing else "incompatible",
        "requested_pause_syllables": cuts,
        "missing_word_boundaries": missing,
        "groups": groups,
        "natural_pause_status": "requires_human_or_melody_review",
    }


def analyze_meter(text: str, spec: MeterSpec | None = None) -> dict:
    spec = spec or MeterSpec()
    lines = []
    known_counts = []
    for number, line in lyric_lines(text):
        syllables = analyze_line(line)
        count = syllables["orthographic_syllables"]
        unknown = syllables["pronunciation_status"] == "uncertain"
        if not unknown:
            known_counts.append(count)
        if spec.syllables is None:
            status = "free_meter"
        elif unknown:
            status = "uncertain"
        else:
            status = "matches" if count == spec.syllables else "mismatch"
        patterns = (spec.durak,) if spec.durak else COMMON_DURAKS.get(spec.syllables, ())
        lines.append({
            "line_number": number, "text": line, "orthographic_syllables": count,
            "meter_status": status,
            "deviation": None if spec.syllables is None else count - spec.syllables,
            "durak_checks": [scan_durak(line, pattern) for pattern in patterns],
            "warnings": syllables["warnings"],
        })
    frequency = Counter(known_counts)
    dominant = max(frequency, key=lambda k: (frequency[k], -k)) if frequency else None
    statuses = Counter(line["meter_status"] for line in lines)
    all_matching = bool(lines) and statuses["matches"] == len(lines)
    return {
        "schema_version": 1,
        "meter_type": "hece" if spec.syllables is not None else "free",
        "requested_syllables": spec.syllables,
        "requested_durak": list(spec.durak) if spec.durak else None,
        "lines": lines,
        "summary": dict(sorted(statuses.items())),
        "all_lines_match": all_matching if spec.syllables is not None else None,
        "observed_dominant_syllables": dominant,
        "dominant_line_fraction": frequency[dominant] / len(lines) if dominant is not None else None,
        "aruz_status": "not_evaluated",
        "melodic_prosody_status": "not_evaluated_without_melody",
    }
