"""Owned abstract mechanisms: retain explanations, don't retrieve copied lyrics."""

from __future__ import annotations

import json
from pathlib import Path

from .contracts import exact_fields, string

SEED_MECHANISMS = [
    {"id": "retrospective_doubt", "name": "Bitişten geçmişi sorgulama", "mechanism": "Bitişi ilan et; geçmişte sevgi sayılan anların anlamını aşamalı sorgulat.", "risk": "Tek soruyu bütün kıtalarda aynı biçimde tekrarlamak."},
    {"id": "claim_contradiction", "name": "İddia ve davranış çelişkisi", "mechanism": "Anlatıcının iddiasını hemen ardından kendi somut davranışı çürütsün.", "risk": "Çelişkiyi açıklayıp duyguyu didaktik hale getirmek."},
    {"id": "attachment_boundary", "name": "Duygu ve karar ayrışması", "mechanism": "Duygunun sürmesiyle davranışın değişmesi birbirinden ayrılır; sınırın bedeli hikâyede görünür.", "risk": "Terapi sloganına veya bağımsız aforizmalara dönüşmek."},
    {"id": "sacrifice_waste", "name": "Fedanın değer kaybı", "mechanism": "Verilen bedelin karşılık bulmaması, daha önce erdem sayılan bağlılığın anlamını değiştirir.", "risk": "Ses benzerliğine dayalı slogan üretmek, olay örgüsünü unutmak."},
    {"id": "role_reversal", "name": "Kazananın görünmeyen kaybı", "mechanism": "Dışarıdan kazanç gibi görünen sonucu taşıyan kişinin gizli kaybını açığa çıkar.", "risk": "Her ilişkiyi galip ve mağlup yarışına indirgemek."},
]


def load_mechanisms(path: str | Path | None = None) -> list[dict]:
    rows = SEED_MECHANISMS if path is None else json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("mechanism library must be a non-empty array")
    ids = set()
    for row in rows:
        exact_fields(row, {"id", "name", "mechanism", "risk"}, "mechanism")
        for key, value in row.items():
            string(value, key, 1200)
        if row["id"] in ids:
            raise ValueError("duplicate mechanism ID")
        ids.add(row["id"])
    return json.loads(json.dumps(rows))
