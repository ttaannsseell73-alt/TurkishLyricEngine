"""Locked narrative progression and section purposes."""
from .contracts import FORM, STORY_SCHEMA, validate_story


class StoryEngine:
    def plan(self, runner, brief, concept, hook):
        return runner.call("story", """Şarkının anlatı omurgasını planla. concept_id ve hook_id kilitlidir.
beats sırası verse1, prechorus, verse2, prechorus2, bridge. Her beat amaç ve önceki duruma göre
somut değişim içersin. verse1 durum, prechorus gerilim, verse2 yeni sonuç/eylem, ikinci prechorus
artmış gerilim, bridge bakış değişimi taşısın. Aynı duyguyu eş anlamlılarla yineleme.
Chorus hook'u merkezde tutar. Nesne kalabalığı ve kopuk güzel sözler oluşturma.""",
            {"brief": brief.to_dict(), "concept": concept, "hook": hook, "form": FORM}, STORY_SCHEMA,
            lambda value: validate_story(value, concept, hook))
