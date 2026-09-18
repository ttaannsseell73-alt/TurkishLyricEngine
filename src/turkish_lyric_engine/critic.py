"""Auditable technical evidence plus model-based semantic/coherence judging."""
from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
from statistics import mean

from .cliche import ClicheDetector
from .contracts import CRITIC_SCHEMA, exact_fields, render_song, string
from .meter import MeterSpec, analyze_meter
from .morphology import AutoMorphology
from .prosody import analyze_line
from .phonology import articulation
from .rhyme import analyze_pair
from .similarity import compare_texts
from .text import lexical_key, lyric_lines, words

SEMANTIC_DIMENSIONS = tuple(CRITIC_SCHEMA["properties"]["dimensions"]["properties"])
RHYME_PAIRS = {"free": (), "AABB": ((1, 2), (3, 4)), "ABAB": ((1, 3), (2, 4)), "ABCB": ((2, 4),)}


def coordinates(song):
    return [(s["id"], i, line) for s in song["sections"] for i, line in enumerate(s["lines"], 1)]


def validate_semantic(payload: dict, song: dict, target: int) -> dict:
    exact_fields(payload, {"dimensions", "rationale", "issues"}, "semantic critic")
    exact_fields(payload["dimensions"], set(SEMANTIC_DIMENSIONS), "semantic dimensions")
    for score in payload["dimensions"].values():
        if type(score) is not int or not 0 <= score <= 100:
            raise ValueError("semantic critic scores must be integers in [0,100]")
    string(payload["rationale"], "critic rationale", 4000)
    available = {(sid, number) for sid, number, _ in coordinates(song)}
    issues = payload["issues"]
    if not isinstance(issues, list):
        raise ValueError("critic issues must be an array")
    for issue in issues:
        exact_fields(issue, {"section_id", "line", "reason", "suggestion"}, "critic issue")
        if type(issue["line"]) is not int or (issue["section_id"], issue["line"]) not in available:
            raise ValueError("critic reported an invalid line coordinate")
        string(issue["reason"], "issue reason")
        string(issue["suggestion"], "issue suggestion")
    if min(payload["dimensions"].values()) < target and not issues:
        raise ValueError("a low semantic score must identify actionable weak lines")
    return payload


def copying_guard(song, corpus) -> dict:
    if corpus is None or not corpus.document_count():
        return {"status": "not_checked_no_corpus", "blocked": False, "issues": [], "copyright_verdict": None}
    locations = coordinates(song)
    issues, matches = [], []
    for doc in corpus.iter_documents():
        report = compare_texts(render_song(song), doc["text"])
        doc_flag = report["exact_document_match"] or (
            len(words(doc["text"])) >= 20 and report["token_sequence_ratio"] >= .85)
        reference_lines = [words(line) for _, line in lyric_lines(doc["text"])]
        for position, (sid, number, text) in enumerate(locations, 1):
            block_copy = report["best_block_match"]["words"] >= 8 and report["best_block_match"]["candidate_line"] == position
            if len(words(text)) < 5 and not block_copy and not doc_flag:
                continue
            candidate_tokens = words(text)
            copied = any(2*min(len(candidate_tokens), len(line))/(len(candidate_tokens)+len(line)) >= .95
                         and SequenceMatcher(None, candidate_tokens, line, autojunk=False).ratio() >= .95
                         for line in reference_lines if len(line) >= 5)
            copied |= block_copy
            if copied or doc_flag:
                issues.append({"section_id": sid, "line": number, "reason": "corpus_lexical_copy_candidate",
                               "suggestion": "Aynı fikri yeni sözcük ve cümle yapısıyla yeniden ifade et.", "hard": True})
        if doc_flag or report["best_line_match"]["ratio"] >= .8:
            matches.append({"content_hash": doc["content_hash"], "metrics": report,
                            "provenance": corpus.provenance(doc["content_hash"])})
    return {"status": "checked_supplied_corpus", "blocked": bool(issues), "issues": issues,
            "matches": matches[:10], "copyright_verdict": None,
            "semantic_similarity_status": "not_evaluated_by_embedding",
            "thresholds": {"min_line_words": 5, "line_ratio": .95, "document_ratio": .85, "min_block_words": 8}}


def local_audit(song, brief, *, morphology=None, corpus=None, cliche=None, lexicon=None) -> dict:
    morphology = morphology or AutoMorphology()
    cliche = cliche or ClicheDetector(corpus)
    issues, lines, rhymes, loads, meter_points, rhyme_points = [], [], [], [], [], []
    unique_sections = [s for s in song["sections"] if s["id"] not in {"chorus2", "final_chorus"}]
    pronunciation_entries = {e.word: e for e in lexicon.entries} if lexicon else {}
    for section in unique_sections:
        sid = section["id"]
        meter = analyze_meter("\n".join(section["lines"]), MeterSpec(brief.meter, brief.durak))
        for number, (text, met) in enumerate(zip(section["lines"], meter["lines"]), 1):
            pro = analyze_line(text)
            suffix_stacks = 0
            for token in pro["tokens"]:
                analyses = morphology.analyze(token["word"])
                token["morphology_candidates"] = len(analyses)
                token["suffix_count"] = len(analyses[0].suffixes) if len(analyses) == 1 else None
                if token["suffix_count"] is not None and token["suffix_count"] >= 4:
                    suffix_stacks += 1
                entry = pronunciation_entries.get(token["word"])
                if entry:
                    token["articulation"] = articulation(token["word"], stress_syllable=entry.stress_syllable,
                         pronunciation=list(entry.pronunciation) if entry.pronunciation else None)
            problems = []
            if met["meter_status"] in {"mismatch", "uncertain"} and brief.meter is not None:
                problems.append(("requested_meter_mismatch_or_unknown", "İstenen hece sayısını doğal Türkçeyle karşıla.", True))
            if brief.durak and any(check["status"] != "compatible_word_boundaries" for check in met["durak_checks"]):
                problems.append(("requested_durak_incompatible", "Durağı kelime sınırına getir; kelimeyi bölme.", True))
            load = pro["articulation_load"]
            load["reviewed_suffix_stacks"] = suffix_stacks
            penalty = 12 * load["cluster_count"] + 10 * load["long_word_count"] + 8*suffix_stacks + max(0, pro["orthographic_syllables"] - 14) * 4
            if pro["pronunciation_status"] == "uncertain":
                penalty += 25
                problems.append(("pronunciation_unknown", "Söyleyişi belirsiz sayı/kısaltmayı açık yaz veya doğal Türkçe karşılığını kullan.", False))
            if load["cluster_count"] or load["long_word_count"] or suffix_stacks:
                problems.append(("articulation_load_review", "Zor ünsüz kümesini veya ek yığılmasını anlamı koruyarak hafiflet.", False))
            if pro["orthographic_syllables"] >= 15:
                problems.append(("long_line_singability_review", "Satırdaki dolgu sözleri azalt; düşünceyi daha kolay söylenen yapıya getir.", False))
            loads.append(max(0, 100 - penalty))
            meter_points.append(100 if brief.meter is None or met["meter_status"] == "matches" else 0)
            lines.append({"section_id": sid, "line": number, "prosody": pro, "meter": met})
            issues.extend({"section_id": sid, "line": number, "reason": reason, "suggestion": suggestion, "hard": hard}
                          for reason, suggestion, hard in problems)
        if len(section["lines"]) == 4:
            for a, b in RHYME_PAIRS[brief.rhyme_scheme]:
                pair = analyze_pair(section["lines"][a-1], section["lines"][b-1], morphology,
                                    pronunciations=lexicon.pronunciations if lexicon else None)
                rhymes.append({"section_id": sid, "pair": [a, b], "analysis": pair})
                ok = pair["status"] == "base_ending_match" or pair.get("rhyme_class_candidate") == "yakın"
                unresolved = pair["status"] == "unresolved"
                rhyme_points.append(100 if ok else 50 if unresolved else 0)
                if not ok:
                    issues.append({"section_id": sid, "line": b, "reason": "rhyme_unverified" if unresolved else "rhyme_missing_or_redif_only",
                                   "suggestion": "Kök/ek ayrımı doğrulanabilen, anlamı koruyan bir kafiye seç; ortak eki tek başına kafiye sayma.", "hard": not unresolved})
    joined = "\n".join(line for s in unique_sections for line in s["lines"])
    phrase_report = cliche.analyze(joined, brief.avoid)
    flattened = [(s["id"], i) for s in unique_sections for i in range(1, len(s["lines"])+1)]
    for hit in phrase_report["matches"]:
        sid, number = flattened[hit["line"]-1]
        issues.append({"section_id": sid, "line": number, "reason": "cliche_phrase_context_review",
                       "suggestion": "Bu kalıbı somut davranışla veya bağlamı değiştiren bir ifadeyle yeniden kur.", "hard": False})
    for hit in phrase_report["preference_hits"]:
        sid, number = flattened[hit["line"]-1]
        issues.append({"section_id": sid, "line": number, "reason": "user_avoid_profile",
                       "suggestion": "Kullanıcının kaçınılan sözcük tercihine uygun doğal bir ifade bul.", "hard": False})
    verse_keys = [lexical_key(line) for s in unique_sections if s["id"] != "chorus" for line in s["lines"]]
    excess = sum(count - 1 for count in Counter(verse_keys).values() if count > 1)
    for s in unique_sections:
        if s["id"] != "chorus":
            for i, text in enumerate(s["lines"], 1):
                if verse_keys.count(lexical_key(text)) > 1:
                    issues.append({"section_id": s["id"], "line": i, "reason": "unplanned_line_repetition",
                                   "suggestion": "Tekrar yerine bu bölümün hikâyede yarattığı değişimi göster.", "hard": False})
    copying = copying_guard(song, corpus)
    issues.extend(copying["issues"])
    dimensions = {"meter": round(mean(meter_points)) if meter_points else 0,
                  "articulation": round(mean(loads)) if loads else 0,
                  "rhyme": round(mean(rhyme_points)) if rhyme_points else None,
                  "cliche": max(0, round(100 - phrase_report["density_candidate"] * 100 - len(phrase_report["preference_hits"])*3)),
                  "repetition": max(0, 100 - excess*15)}
    return {"lines": lines, "rhyme_redif": rhymes, "cliche": phrase_report, "copying": copying,
            "dimensions": dimensions, "issues": issues, "hard_failures": sum(bool(i["hard"]) for i in issues),
            "morphology_backend": getattr(morphology, "status", type(morphology).__name__),
            "melodic_stress_status": "not_evaluated_without_melody",
            "redif_correctness": "surface_and_function_evidence_required",
            "score_calibration": "engineering_heuristic_not_artistic_validation"}


class SemanticCoherenceEngine:
    def evaluate(self, runner, brief, concept, hook, story, song, local):
        return runner.call("critic", """Sert Türkçe şarkı eleştirisi yap. Şu dimensions değerlerini 0–100 puanla:
idea_adherence, natural_turkish, emotional_progression, hook_strength, register_consistency, originality,
singability_text. Verse/pre/chorus/bridge'in kilitli beat'lerle uyumunu, bölümden bölüme gelişimi,
zamir/kişi/zaman tutarlılığını, nesne kalabalığını ve açıklayıcı AI/terapi dilini denetle.
Güzel cümleler dizisini hikâye sanma. Doğal kelime sırası, ek yığılması ve cümlenin gerçekten biri
tarafından söylenebilirliğini değerlendir. Kafiye/metre puanı anlam kusurunu telafi etmesin.
Her düşük boyut için ilgili somut satıra issue yaz; section_id ve line 1 tabanlıdır.
Orijinallik puanı yalnız fikir/ifade yargısıdır; dış arşiv taraması veya telif hükmü değildir.
Rationale somut bulgular içersin. technical_evidence kalite kararını destekler, onun yerine geçmez.""",
            {"brief": brief.to_dict(), "concept": concept, "hook": hook, "story": story, "song": song,
             "technical_evidence": {k: local[k] for k in ("dimensions", "issues", "rhyme_redif", "cliche")}},
            CRITIC_SCHEMA, lambda value: validate_semantic(value, song, brief.target_score), judge=True)


def combine_audit(local, semantic, target):
    local_scores = [value for value in local["dimensions"].values() if value is not None]
    technical = mean(local_scores) if local_scores else 0
    semantic_score = mean(semantic["dimensions"].values())
    score = round(semantic_score*.65 + technical*.35, 2)
    issues = local["issues"] + [{**issue, "hard": False} for issue in semantic["issues"]]
    passed = (score >= target and all(value >= target for value in semantic["dimensions"].values())
              and all(value >= target for value in local_scores) and local["hard_failures"] == 0)
    return {"score": score, "target": target, "target_met": passed, "local": local, "semantic": semantic,
            "issues": issues, "decision": "review_ready" if passed else "quality_target_not_met",
            "judgement_calibration": "uncalibrated_model_judgement_and_engineering_heuristics"}


def rhyme_plan(brief, lexicon=None, hook=None, concept=None):
    terms = []
    if hook:
        terms.extend(words(hook["text"])[-2:])
    if concept:
        terms.extend(words(concept["angle"])[-2:])
    families = []
    if lexicon:
        for term in dict.fromkeys(terms):
            family = lexicon.family(term, limit=8)
            if family:
                families.append({"anchor": term, "candidates": family})
    return {"scheme": brief.rhyme_scheme, "pairs_for_four_line_sections": RHYME_PAIRS[brief.rhyme_scheme],
            "redif_is_not_rhyme": True, "dictionary_entries": len(lexicon.entries) if lexicon else 0,
            "dictionary_status": "available" if lexicon else "not_supplied", "families": families,
            "meaning_has_priority": True}
