"""Transactional SQLite corpus with deduplication and separate provenance.

Archives remain local. Ingestion never scrapes or sends text to an LLM.
Rights are recorded assertions, not a legal determination.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from .prosody import analyze_text
from .text import canonical_lyric, lexical_key, lower_tr, normalize_text, words

KINDS = {"song", "poem", "turku", "rhyme_dictionary", "gold", "red"}
RIGHTS = {"owned", "public_domain", "permission", "restricted", "unknown"}
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CorpusRecord:
    record_id: str
    kind: str
    title: str
    text: str
    source: str
    rights: str = "unknown"
    production_allowed: bool = False

    def __post_init__(self) -> None:
        for name in ("record_id", "title", "text", "source"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.kind not in KINDS:
            raise ValueError(f"unsupported corpus kind: {self.kind}")
        if self.rights not in RIGHTS:
            raise ValueError(f"unsupported rights label: {self.rights}")
        if type(self.production_allowed) is not bool:
            raise ValueError("production_allowed must be a boolean")
        if self.production_allowed and self.rights not in {"owned", "public_domain", "permission"}:
            raise ValueError("unknown/restricted material cannot be production-enabled")
        if not lexical_key(canonical_lyric(self.text)):
            raise ValueError("record contains no lyric words")

    @classmethod
    def from_dict(cls, row: dict) -> CorpusRecord:
        if not isinstance(row, dict):
            raise ValueError("corpus row must be a JSON object")
        try:
            return cls(**row)
        except TypeError as exc:
            raise ValueError(f"invalid corpus fields: {exc}") from exc


def read_jsonl(path: str | Path) -> list[CorpusRecord]:
    records = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(CorpusRecord.from_dict(json.loads(line)))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid JSONL line {number}: {exc}") from exc
    if not records:
        raise ValueError("empty corpus batch")
    return records


def digest(text: str) -> str:
    # Preserve line order and refrain multiplicity in the deduplication key.
    key = "\n".join(lexical_key(line) for line in canonical_lyric(text).splitlines())
    return sha256(key.encode("utf-8")).hexdigest()


class CorpusStore:
    def __init__(self, path: str | Path, *, create: bool = True):
        self.path = Path(path)
        if not create and not self.path.is_file():
            raise ValueError(f"corpus database does not exist: {path}")
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        try:
            self.connection.execute("PRAGMA foreign_keys = ON")
            version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, SCHEMA_VERSION):
                raise ValueError(f"unsupported corpus schema version: {version}")
            if version == 0:
                if not create:
                    raise ValueError("not an initialized TurkishLyricEngine database")
                # Do not repurpose someone else's SQLite database.
                if self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise ValueError("refusing to initialize a non-empty foreign database")
                self.connection.executescript("""
                    CREATE TABLE documents (
                        content_hash TEXT PRIMARY KEY,
                        text TEXT NOT NULL,
                        analysis_json TEXT NOT NULL
                    );
                    CREATE TABLE records (
                        record_id TEXT PRIMARY KEY,
                        content_hash TEXT NOT NULL REFERENCES documents(content_hash),
                        kind TEXT NOT NULL,
                        title TEXT NOT NULL,
                        source TEXT NOT NULL,
                        rights TEXT NOT NULL,
                        production_allowed INTEGER NOT NULL CHECK(production_allowed IN (0, 1)),
                        original_text TEXT NOT NULL
                    );
                    CREATE INDEX records_content ON records(content_hash);
                    PRAGMA user_version = 1;
                """)
            self.connection.execute("SELECT content_hash, text, analysis_json FROM documents LIMIT 0")
            self.connection.execute("SELECT record_id, original_text FROM records LIMIT 0")
        except Exception:
            self.connection.close()
            raise

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> CorpusStore:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def ingest(self, records: Iterable[CorpusRecord]) -> dict:
        batch = list(records)
        if not batch or any(not isinstance(record, CorpusRecord) for record in batch):
            raise ValueError("ingest requires a non-empty validated CorpusRecord batch")
        inserted_documents = inserted_records = skipped_records = 0
        # Any conflict rolls the entire batch back, including earlier inserts.
        with self.connection:
            for record in batch:
                content_hash = digest(record.text)
                normalized = normalize_text(record.text)
                expected = (content_hash, record.kind, record.title, record.source,
                            record.rights, int(record.production_allowed), record.text)
                existing = self.connection.execute(
                    "SELECT content_hash, kind, title, source, rights, production_allowed, original_text "
                    "FROM records WHERE record_id = ?", (record.record_id,)).fetchone()
                if existing is not None:
                    if tuple(existing) != expected:
                        raise ValueError(f"record_id conflict: {record.record_id}; explicit migration required")
                    skipped_records += 1
                    continue
                cursor = self.connection.execute(
                    "INSERT OR IGNORE INTO documents VALUES (?, ?, ?)",
                    (content_hash, normalized,
                     json.dumps(analyze_text(normalized), ensure_ascii=False, sort_keys=True)))
                inserted_documents += cursor.rowcount
                self.connection.execute("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                        (record.record_id, *expected))
                inserted_records += 1
        return {"inserted_documents": inserted_documents, "inserted_records": inserted_records,
                "skipped_records": skipped_records, "total_documents": self.document_count()}

    def document_count(self) -> int:
        return self.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def documents(self) -> list[dict]:
        return [dict(row) for row in self.connection.execute("SELECT * FROM documents ORDER BY content_hash")]

    def provenance(self, content_hash: str) -> list[dict]:
        return [dict(row) for row in self.connection.execute(
            "SELECT record_id, kind, title, source, rights, production_allowed FROM records "
            "WHERE content_hash = ? ORDER BY record_id", (content_hash,))]

    def stats(self) -> dict:
        line_counts, endings, phrases = Counter(), Counter(), Counter()
        for doc in self.documents():
            report = json.loads(doc["analysis_json"])
            for line in report["lines"]:
                line_counts[line["orthographic_syllables"]] += 1
                tokens = words(line["text"])
                if tokens:
                    endings[tokens[-1]] += 1
                phrases.update(tuple(tokens[i:i + 3]) for i in range(max(0, len(tokens) - 2)))
        by_kind = dict(self.connection.execute("SELECT kind, COUNT(*) FROM records GROUP BY kind ORDER BY kind"))
        return {
            "schema_version": SCHEMA_VERSION,
            "unique_documents": self.document_count(),
            "provenance_records_by_kind": by_kind,
            "syllable_histogram": dict(sorted(line_counts.items())),
            "common_endings": endings.most_common(20),
            "common_trigrams": [{"phrase": " ".join(k), "count": v} for k, v in phrases.most_common(20)],
            "counting_unit": "unique_documents_with_original_refrain_multiplicity",
            "rights_status": "metadata_assertions_only",
            "production_enabled_records": self.connection.execute(
                "SELECT COUNT(*) FROM records WHERE production_allowed = 1").fetchone()[0],
        }
