"""Transactional SQLite corpus with deduplication and separate provenance.

Archives remain local. Ingestion never scrapes or sends text to an LLM.
Rights are recorded assertions, not a legal determination.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import csv
import json
import math
import re
from pathlib import Path
import sqlite3
from typing import Iterable

from .prosody import analyze_text
from .text import canonical_lyric, is_header, lexical_key, normalize_text, words
from .rhyme import analyze_pair
from .morphology import AutoMorphology

KINDS = {"song", "poem", "turku", "literary", "rhyme_dictionary", "gold", "red"}
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
    lines = canonical_lyric(text).splitlines()
    key = "\n".join(lexical_key(line) for line in lines)
    numbers = [re.findall(r"\d+(?:[.,]\d+)*", line) for line in lines]
    if any(numbers):
        key += "\n#numeric-surfaces:" + json.dumps(numbers, ensure_ascii=False)
    return sha256(key.encode("utf-8")).hexdigest()


def read_archive(path: str | Path) -> list[CorpusRecord]:
    """JSON(L), CSV, or TXT directory; TXT metadata lives in <file>.meta.json."""
    file = Path(path)
    if file.is_dir():
        batch = []
        for item in sorted(file.rglob("*.txt")):
            batch.extend(read_archive(item))
        if not batch:
            raise ValueError("archive directory contains no TXT records")
        return batch
    if file.suffix.lower() == ".jsonl":
        return read_jsonl(file)
    if file.suffix.lower() == ".json":
        rows = json.loads(file.read_text(encoding="utf-8-sig"))
    elif file.suffix.lower() == ".csv":
        with file.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            value = row.get("production_allowed", "false")
            if value not in {"true", "false", "0", "1", ""}:
                raise ValueError("CSV production_allowed must be true/false/0/1")
            row["production_allowed"] = value in {"true", "1"}
    elif file.suffix.lower() == ".txt":
        sidecar = file.with_suffix(file.suffix + ".meta.json")
        metadata = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
        if not isinstance(metadata, dict) or "text" in metadata:
            raise ValueError("invalid TXT metadata sidecar")
        text = file.read_text(encoding="utf-8-sig")
        defaults = {"record_id": "txt:" + sha256((str(file.resolve()) + text).encode()).hexdigest(),
                    "kind": "literary", "title": file.stem, "source": file.name}
        rows = [{**defaults, **metadata, "text": text}]
    else:
        raise ValueError("supported archive formats: JSONL, JSON, CSV, TXT directory")
    if not isinstance(rows, list) or not rows:
        raise ValueError("archive must contain a non-empty record array")
    return [CorpusRecord.from_dict(row) for row in rows]


def split_stanzas(text: str) -> list[dict]:
    stanza, section, result, boundary = 1, "unlabelled", [], False
    for line in normalize_text(text).splitlines():
        if not line or is_header(line):
            if result and not boundary:
                stanza += 1
            boundary = True
            if is_header(line):
                section = line.strip("[]:")
            continue
        result.append({"ordinal": len(result) + 1, "stanza": stanza, "section": section, "text": line})
        boundary = False
    return result


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
            self.indexed = bool(self.connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='corpus_terms'").fetchone())
            if create:
                self._ensure_index()
        except Exception:
            self.connection.close()
            raise

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> CorpusStore:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def _ensure_index(self) -> None:
        # Additive M1 migration; original documents and provenance are untouched.
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS corpus_lines (
                content_hash TEXT NOT NULL REFERENCES documents(content_hash),
                ordinal INTEGER NOT NULL, stanza INTEGER NOT NULL, section TEXT NOT NULL,
                text TEXT NOT NULL, syllables INTEGER NOT NULL, ending TEXT NOT NULL,
                rhyme_json TEXT NOT NULL, PRIMARY KEY(content_hash, ordinal));
            CREATE TABLE IF NOT EXISTS corpus_terms (
                token TEXT NOT NULL, content_hash TEXT NOT NULL REFERENCES documents(content_hash),
                occurrences INTEGER NOT NULL, PRIMARY KEY(token, content_hash));
            CREATE INDEX IF NOT EXISTS corpus_terms_document ON corpus_terms(content_hash);
            CREATE TABLE IF NOT EXISTS corpus_ngrams (
                phrase TEXT NOT NULL, n INTEGER NOT NULL, content_hash TEXT NOT NULL REFERENCES documents(content_hash),
                occurrences INTEGER NOT NULL, PRIMARY KEY(phrase, content_hash));
        """)
        self.indexed = True
        provider = AutoMorphology(use_zeyrek=False)
        with self.connection:
            for doc in self.connection.execute("SELECT content_hash, text FROM documents ORDER BY content_hash").fetchall():
                if not self.connection.execute("SELECT 1 FROM corpus_lines WHERE content_hash=? LIMIT 1", (doc[0],)).fetchone():
                    self._index_document(doc[0], doc[1], provider)

    def _index_document(self, identity: str, text: str, provider=None) -> None:
        provider = provider or AutoMorphology(use_zeyrek=False)
        terms, phrases, previous = Counter(), Counter(), None
        for row in split_stanzas(text):
            tokens = words(row["text"])
            terms.update(tokens)
            for n in range(2, 6):
                phrases.update(" ".join(tokens[i:i+n]) for i in range(max(0, len(tokens)-n+1)))
            rhyme = analyze_pair(previous["text"], row["text"], provider) if previous and previous["stanza"] == row["stanza"] else {}
            syllables = analyze_text(row["text"])["lines"][0]["orthographic_syllables"]
            self.connection.execute("INSERT INTO corpus_lines VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (identity, row["ordinal"], row["stanza"], row["section"], row["text"], syllables,
                 tokens[-1] if tokens else "", json.dumps(rhyme, ensure_ascii=False)))
            previous = row
        self.connection.executemany("INSERT INTO corpus_terms VALUES (?, ?, ?)",
                                    [(term, identity, count) for term, count in terms.items()])
        self.connection.executemany("INSERT INTO corpus_ngrams VALUES (?, ?, ?, ?)",
                                    [(phrase, len(phrase.split()), identity, count) for phrase, count in phrases.items()])

    def ingest(self, records: Iterable[CorpusRecord]) -> dict:
        batch = list(records)
        if not batch or any(not isinstance(record, CorpusRecord) for record in batch):
            raise ValueError("ingest requires a non-empty validated CorpusRecord batch")
        inserted_documents = inserted_records = skipped_records = 0
        if not self.indexed:
            self._ensure_index()
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
                    # Numeric M1 hashes ignored digits; preserve an unchanged legacy
                    # record while all new records use the safer numerical key.
                    legacy_key = "\n".join(lexical_key(line) for line in canonical_lyric(record.text).splitlines())
                    legacy_hash = sha256(legacy_key.encode("utf-8")).hexdigest()
                    if tuple(existing)[1:] == expected[1:] and existing[0] == legacy_hash:
                        expected = (existing[0], *expected[1:])
                    if tuple(existing) != expected:
                        raise ValueError(f"record_id conflict: {record.record_id}; explicit migration required")
                    skipped_records += 1
                    continue
                cursor = self.connection.execute(
                    "INSERT OR IGNORE INTO documents VALUES (?, ?, ?)",
                    (content_hash, normalized,
                     json.dumps(analyze_text(normalized), ensure_ascii=False, sort_keys=True)))
                inserted_documents += cursor.rowcount
                if cursor.rowcount:
                    self._index_document(content_hash, normalized)
                self.connection.execute("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                        (record.record_id, *expected))
                inserted_records += 1
        return {"inserted_documents": inserted_documents, "inserted_records": inserted_records,
                "skipped_records": skipped_records, "total_documents": self.document_count()}

    def document_count(self) -> int:
        return self.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def documents(self) -> list[dict]:
        return list(self.iter_documents())

    def iter_documents(self):
        for row in self.connection.execute("SELECT * FROM documents ORDER BY content_hash"):
            yield dict(row)

    def provenance(self, content_hash: str) -> list[dict]:
        return [dict(row) for row in self.connection.execute(
            "SELECT record_id, kind, title, source, rights, production_allowed FROM records "
            "WHERE content_hash = ? ORDER BY record_id", (content_hash,))]

    def search(self, query: str, *, limit: int = 10, include_text: bool = False) -> dict:
        tokens = sorted(set(words(query)))
        if not tokens or not 1 <= limit <= 100:
            raise ValueError("search requires words and a limit in [1,100]")
        scores = Counter()
        total = self.document_count()
        for token in tokens:
            if self.indexed:
                rows = list(self.connection.execute("SELECT content_hash, occurrences FROM corpus_terms WHERE token=?", (token,)))
            else:
                rows = [(doc["content_hash"], words(canonical_lyric(doc["text"])).count(token)) for doc in self.documents()]
                rows = [(identity, count) for identity, count in rows if count]
            inverse_frequency = math.log(1 + total / max(1, len(rows)))
            for identity, count in rows:
                scores[identity] += (1 + math.log(count)) * inverse_frequency
        matches = []
        for identity, score in sorted(scores.items(), key=lambda p: (-p[1], p[0]))[:limit]:
            row = {"content_hash": identity, "score": round(score, 6), "provenance": self.provenance(identity)}
            if include_text:
                row["text"] = self.connection.execute("SELECT text FROM documents WHERE content_hash=?", (identity,)).fetchone()[0]
            matches.append(row)
        return {"status": "searched" if total else "empty_corpus", "method": "inverted_tf_idf",
                "matches": matches, "raw_text_included": include_text, "generation_use": "statistics_only"}

    def knowledge(self) -> dict:
        stats = self.stats()
        return {"status": "corpus_statistics" if self.document_count() else "no_corpus",
                "documents": self.document_count(), "syllable_histogram": stats["syllable_histogram"],
                "kinds": stats["provenance_records_by_kind"], "raw_archive_text_in_prompt": False}

    def stats(self) -> dict:
        line_counts, endings, phrases, vocabulary, motifs = Counter(), Counter(), Counter(), Counter(), Counter()
        for doc in self.documents():
            report = json.loads(doc["analysis_json"])
            for line in report["lines"]:
                line_counts[line["orthographic_syllables"]] += 1
                tokens = words(line["text"])
                vocabulary.update(tokens)
                if tokens:
                    endings[tokens[-1]] += 1
                phrases.update(tuple(tokens[i:i + 3]) for i in range(max(0, len(tokens) - 2)))
            all_words = set(words(canonical_lyric(doc["text"])))
            for motif, stems in {"bekleme": ("bekle", "erte"), "ayrılma": ("git", "bırak", "veda"),
                                 "geri_dönme": ("dön", "geri"), "inkâr": ("değil", "yok"),
                                 "hatırlama": ("hatır", "unut", "anım")}.items():
                if any(token.startswith(stem) for token in all_words for stem in stems):
                    motifs[motif] += 1
        by_kind = dict(self.connection.execute("SELECT kind, COUNT(*) FROM records GROUP BY kind ORDER BY kind"))
        return {
            "schema_version": SCHEMA_VERSION,
            "unique_documents": self.document_count(),
            "provenance_records_by_kind": by_kind,
            "syllable_histogram": dict(sorted(line_counts.items())),
            "common_endings": endings.most_common(20),
            "common_trigrams": [{"phrase": " ".join(k), "count": v} for k, v in phrases.most_common(20)],
            "common_words": [{"word": k, "count": v} for k, v in vocabulary.most_common(30)],
            "motif_candidates": dict(sorted(motifs.items())),
            "motif_method": "editorial_lexical_stem_candidates_not_semantic_labels",
            "counting_unit": "unique_documents_with_original_refrain_multiplicity",
            "rights_status": "metadata_assertions_only",
            "production_enabled_records": self.connection.execute(
                "SELECT COUNT(*) FROM records WHERE production_allowed = 1").fetchone()[0],
        }
