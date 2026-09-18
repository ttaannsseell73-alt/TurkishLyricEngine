"""Concept diversity and explicit idea judging precede any lyric draft."""
from .contracts import IDEAS_SCHEMA, RANK_SCHEMA, validate_candidates, validate_rankings


class ConceptEngine:
    def generate(self, runner, brief, mechanisms, knowledge, preferences):
        ids = {m["id"] for m in mechanisms}
        return runner.call("concepts", """Tam count adet birbirinden farklı şarkı fikri üret.
Tema → özgün açı → duygusal çatışma → değişim. angle sahici bir insan durumunu içersin.
conflict iki zıt dürtüyü, turn anlatıcının değişimini açıklasın. Verilen mekanizmaları çeşitlendir.
Henüz şarkı sözleri yazma; her fikre benzersiz c01 gibi ID ver.""",
            {"brief": brief.to_dict(), "count": brief.concept_count, "mechanisms": mechanisms,
             "corpus_statistics": knowledge, "user_preferences": preferences}, IDEAS_SCHEMA,
            lambda value: validate_candidates(value, "concepts", brief.concept_count, ids))

    def evaluate(self, runner, brief, concepts, preferences):
        rankings = runner.call("idea_judge", """Her fikri tam bir kez puanla ve somut gerekçe yaz.
Özgün dramatik açı, gerçek insan davranışı, açık çatışma, şarkıya taşınabilirlik ve değişim esas.
Soyut slogan, birbirinin eş anlamlısı fikir ve sırf garip olmak için kurulan fikri düşür.
Kullanıcı tercihleri bir beğeni kanıtıdır; küçük örneklemleri mutlak kural sayma.""",
            {"brief": brief.to_dict(), "concepts": concepts, "preferences": preferences}, RANK_SCHEMA,
            lambda value: validate_rankings(value, concepts), judge=True)
        lookup = {c["id"]: c for c in concepts}
        return [{**r, "concept": lookup[r["id"]]} for r in rankings]
