"""Transparent Turkish grapheme/phoneme estimates and syllable articulation.

Unknown lexical stress, loanword length and dialect are never declared known.
Explicit pronunciation/stress overrides are accepted by the lexicon layer.
"""

from __future__ import annotations

from .text import LETTERS, VOWELS, lower_tr

PHONES = {"c": "dʒ", "ç": "tʃ", "ş": "ʃ", "j": "ʒ", "y": "j", "ı": "ɯ", "ö": "œ", "ü": "y"}
NEAR_GROUPS = [{"p", "b"}, {"t", "d"}, {"k", "g"}, {"f", "v"}, {"s", "z"}, {"tʃ", "dʒ"},
               {"ʃ", "ʒ"}, {"a", "ɯ"}, {"e", "i"}, {"o", "u"}, {"œ", "y"}]


def syllabify(word: str) -> list[str]:
    token = lower_tr(word).replace("'", "")
    nuclei = [i for i, c in enumerate(token) if c in VOWELS]
    if not nuclei:
        return []
    cuts = [0]
    for left, right in zip(nuclei, nuclei[1:]):
        gap = right - left - 1
        # Adjacent vowels split; between vowels, the final consonant starts
        # the next syllable. This is orthographic syllabification, not ulama.
        cuts.append(right if gap == 0 else right - 1)
    cuts.append(len(token))
    return [token[a:b] for a, b in zip(cuts, cuts[1:])]


def phonemes(word: str, pronunciation: list[str] | None = None) -> dict:
    token = lower_tr(word).replace("'", "")
    if pronunciation is not None:
        if not pronunciation or any(not isinstance(p, str) or not p for p in pronunciation):
            raise ValueError("pronunciation must be a non-empty phoneme array")
        return {"phonemes": list(pronunciation), "status": "supplied_pronunciation", "warnings": []}
    result, warnings = [], []
    for char in token:
        if char not in LETTERS:
            warnings.append("unsupported_grapheme")
        if char == "ğ":
            # Keep a distinct length marker. Same-vowel fusion/glide behavior
            # requires lexical/acoustic evidence; do not silently delete it.
            result.append("ː")
            warnings.append("soft_g_pronunciation_needs_review")
        elif char in "âîû":
            base = {"â": "a", "î": "i", "û": "u"}[char]
            result.extend([PHONES.get(base, base), "ː"])
            warnings.append("lexical_vowel_length_needs_review")
        else:
            result.append(PHONES.get(char, char))
    return {"phonemes": result, "status": "grapheme_estimate", "warnings": sorted(set(warnings))}


def tail_match(left: list[str], right: list[str]) -> list[str]:
    result = []
    for a, b in zip(reversed(left), reversed(right)):
        if a != b:
            break
        result.append(a)
    return list(reversed(result))


def near_tail_score(left: list[str], right: list[str], window: int = 3) -> float:
    pairs = list(zip(reversed(left[-window:]), reversed(right[-window:])))
    if not pairs:
        return 0.0
    total = 0.0
    for a, b in pairs:
        total += 1.0 if a == b else 0.6 if any(a in group and b in group for group in NEAR_GROUPS) else 0.0
    return round(total / len(pairs), 4)


def articulation(word: str, *, stress_syllable: int | None = None, pronunciation=None) -> dict:
    syllables = syllabify(word)
    token = lower_tr(word).replace("'", "")
    clusters, current = [], ""
    for char in token + "a":
        if char not in VOWELS and char != "ğ":
            current += char
        else:
            if len(current) >= 3:
                clusters.append(current)
            current = ""
    if stress_syllable is not None and (type(stress_syllable) is not int or not 1 <= stress_syllable <= len(syllables)):
        raise ValueError("stress syllable outside word")
    return {"syllables": syllables, "syllable_shapes": ["".join("V" if c in VOWELS else "C" for c in s) for s in syllables],
            "duration_structure": ["open" if s[-1] in VOWELS else "closed" for s in syllables],
            "duration_status": "structural_cue_not_acoustic_duration",
            "consonant_clusters": clusters,
            "long_word_review": len(syllables) >= 6,
            "stress": {"candidate_syllable": stress_syllable or (len(syllables) if syllables else None),
                       "status": "supplied_lexical_stress" if stress_syllable else "default_final_stress_candidate_not_lexically_disambiguated"},
            "phonology": phonemes(word, pronunciation)}
