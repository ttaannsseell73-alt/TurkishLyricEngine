"""Hook generation and evaluation are separate model stages."""
from .contracts import HOOKS_SCHEMA, RANK_SCHEMA, validate_candidates, validate_rankings
from .meter import MeterSpec, analyze_meter
from .prosody import analyze_line
from .text import words


def hook_metrics(hook: dict, brief) -> dict:
    text = hook["text"]
    prosody = analyze_line(text)
    meter = analyze_meter(text, MeterSpec(brief.meter, brief.durak))
    tokens = words(text)
    initials = [word[0] for word in tokens]
    return {"words": len(tokens), "syllables": prosody["orthographic_syllables"],
            "initial_sound_repetitions": len(initials) - len(set(initials)),
            "articulation": prosody["articulation_load"], "meter": meter,
            "eligible": 4 <= len(tokens) <= 7 and prosody["pronunciation_status"] != "uncertain"
                        and (brief.meter is None or meter["all_lines_match"])
                        and (not brief.durak or all(c["status"] == "compatible_word_boundaries"
                            for c in meter["lines"][0]["durak_checks"])),
            "memorability_status": "requires_contextual_judge_and_human_review"}


class HookLab:
    def generate(self, runner, brief, concept):
        return runner.call("hooks", """Tam count adet benzersiz 4–7 kelimelik Türkçe hook üret.
concept_id kilitlidir. Hook kolay tekrarlanır, ana çatışmayı taşır; kısa ve fonetik olarak güçlüdür.
Instagram aforizması, açıklayıcı terapi cümlesi veya soyut süslü slogan yazma.
Ölçü seçildiyse hook o hece sayısına ve durak kelime sınırlarına uymalıdır.
Her adaya h01 gibi benzersiz ID ver.""", {"brief": brief.to_dict(), "concept": concept, "count": brief.hook_count},
            HOOKS_SCHEMA, lambda value: validate_candidates(value, "hooks", brief.hook_count, concept_id=concept["id"]))

    def evaluate(self, runner, brief, concept, hooks):
        evidence = [{"hook": h, "metrics": hook_metrics(h, brief)} for h in hooks]
        rankings = runner.call("hook_judge", """Her hook'u tam bir kez puanla, somut gerekçe yaz.
Ana fikri taşıma, doğal konuşma, hatırlanabilirlik, ses akışı ve tekrarda güç esas.
Kısa olmayı tek başına başarı sayma. Kafiye için anlamı bozan veya başka fikre kayan adayı düşür.""",
            {"brief": brief.to_dict(), "concept": concept, "candidates": evidence}, RANK_SCHEMA,
            lambda value: validate_rankings(value, hooks), judge=True)
        lookup = {e["hook"]["id"]: e for e in evidence}
        return [{**r, **lookup[r["id"]]} for r in rankings]
