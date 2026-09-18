"""Multi-writer drafts and restricted line rewrites; no offline fake writer."""
from copy import deepcopy

from .contracts import FORM, PATCH_SCHEMA, SONG_SCHEMA, exact_fields, fingerprint, string, validate_song

VARIANTS = ("somut insan davranışı ve sade dil", "iç gerilim ve kontrollü imge",
            "konuşur gibi akış ve dramatik sonuç", "az kelimeyle anlam sıkıştırma", "eylemle gösterilen duygu")


def canonical_coordinate(section_id: str, line: int) -> tuple[str, int]:
    return ("chorus" if section_id in {"chorus2", "final_chorus"} else section_id, line)


def apply_patches(response, song, allowed: set[tuple[str, int]], concept, hook, story, max_chars):
    exact_fields(response, {"patches"}, "revision")
    if not isinstance(response["patches"], list) or not response["patches"]:
        raise ValueError("revision must replace at least one reported weak line")
    revised, seen = deepcopy(song), set()
    for patch in response["patches"]:
        exact_fields(patch, {"section_id", "line", "text"}, "patch")
        if type(patch["line"]) is not int:
            raise ValueError("patch line must be an integer")
        coordinate = canonical_coordinate(patch["section_id"], patch["line"])
        if coordinate not in allowed or coordinate in seen or coordinate == ("chorus", 1):
            raise ValueError("patch changed an unreported, duplicate, or locked hook line")
        text = string(patch["text"], "replacement line", 250)
        sections = [s for s in revised["sections"] if s["id"] == coordinate[0]]
        if not sections or not 1 <= coordinate[1] <= len(sections[0]["lines"]):
            raise ValueError("patch coordinate outside song")
        if sections[0]["lines"][coordinate[1]-1] == text:
            raise ValueError("revision patch did not change the line")
        sections[0]["lines"][coordinate[1]-1] = text
        seen.add(coordinate)
    chorus = revised["sections"][2]["lines"]
    revised["sections"][5]["lines"] = chorus.copy()
    revised["sections"][7]["lines"] = chorus.copy()
    return validate_song(revised, concept, hook, story, max_chars)


class LyricWriter:
    def draft(self, runner, brief, concept, hook, story, index, rhyme_plan):
        return runner.call("draft", """Kilitli fikir, hook ve hikâyeden tam şarkı taslağı yaz.
form'daki bölüm sırasını ve satır sayılarını aynen koru. Chorus ilk satırı hook.text aynen olsun;
chorus2 ve final_chorus ilk chorus'un birebir kopyası olsun. Verse/pre/bridge hikâyeyi ilerletsin.
story_hash verilen hash'tir. Ölçü ve kafiye yardımcıdır; anlamı bozarak doldurma yapma.
lyrics yalnız söylenen satırlardır, başlık/teknik yönerge satırın içine girmez.
prefer_nonverb_endings açıksa yüklem sonlarını azalt; bu tercih için doğal Türkçeyi bozma.
Yazar yaklaşımını kullan ama aynı fikrin dışına çıkma.""", {"brief": brief.to_dict(), "concept": concept,
            "hook": hook, "story": story, "story_hash": fingerprint(story), "form": FORM,
            "writer_approach": VARIANTS[index % len(VARIANTS)], "rhyme_plan": rhyme_plan}, SONG_SCHEMA,
            lambda value: validate_song(value, concept, hook, story, brief.max_chars))

    def revise(self, runner, brief, song, concept, hook, story, issues, rhyme_plan):
        allowed = {canonical_coordinate(i["section_id"], i["line"]) for i in issues}
        allowed.discard(("chorus", 1))
        if not allowed:
            raise ValueError("no mutable weak line; locked hook requires reselection")
        return runner.call("revision", """Yalnız reported_issues içinde izin verilen zayıf satırları değiştir.
Her patch section_id, 1 tabanlı line, text içerir. İlk hook satırı değişmez; konsept ve hikâye değişmez.
Chorus tekrarı uygulama tarafından eşlenecek: yalnız chorus koordinatını kullan.
Düşük puanın sebebini gider; aynı satırı veya ilgisiz bölüm değişikliğini döndürme.
Ölçü sorunuysa istenen heceyi/durağı; dil sorunuysa doğal Türkçeyi; anlatı sorunuysa beat değişimini;
benzerlik sorunuysa aynı fikri tümüyle yeni ifadeyle düzelt.""", {"brief": brief.to_dict(), "concept": concept,
            "hook": hook, "story": story, "song": song, "reported_issues": issues,
            "allowed_coordinates": sorted(allowed), "rhyme_plan": rhyme_plan}, PATCH_SCHEMA,
            lambda value: apply_patches(value, song, allowed, concept, hook, story, brief.max_chars))
