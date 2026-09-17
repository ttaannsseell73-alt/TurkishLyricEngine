from dataclasses import replace
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from turkish_lyric_engine.corpus import CorpusRecord, CorpusStore, digest, read_jsonl
from turkish_lyric_engine.similarity import check_corpus, compare_texts


def record(record_id="one", text="Beni unut\nYeni bir güne uyan", **kwargs):
    defaults = dict(record_id=record_id, kind="song", title="Özgün test", text=text,
                    source="test_fixture", rights="owned", production_allowed=False)
    return CorpusRecord(**(defaults | kwargs))


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "corpus.sqlite3"

    def tearDown(self):
        self.temp.cleanup()

    def test_idempotent_reingestion(self):
        with CorpusStore(self.path) as store:
            self.assertEqual(store.ingest([record()])["inserted_documents"], 1)
            report = store.ingest([record()])
            self.assertEqual(report["skipped_records"], 1)
            self.assertEqual(store.document_count(), 1)

    def test_dedup_preserves_independent_sources(self):
        first = record()
        second = replace(first, record_id="two", source="second_archive", title="İkinci kaynak",
                         text="[Nakarat]\nBENİ UNUT!\nYeni  bir güne uyan.")
        with CorpusStore(self.path) as store:
            report = store.ingest([first, second])
            self.assertEqual(report["inserted_documents"], 1)
            self.assertEqual(report["inserted_records"], 2)
            self.assertEqual(len(store.provenance(digest(first.text))), 2)
            originals = list(store.connection.execute("SELECT original_text FROM records ORDER BY record_id"))
            self.assertEqual([row[0] for row in originals], [first.text, second.text])

    def test_conflicting_id_rolls_entire_batch_back(self):
        with CorpusStore(self.path) as store:
            store.ingest([record()])
            with self.assertRaises(ValueError):
                store.ingest([record("new", "Geri dön\nSana yolum yok"), replace(record(), source="changed")])
            self.assertEqual(store.document_count(), 1)
            self.assertEqual(store.connection.execute("SELECT COUNT(*) FROM records").fetchone()[0], 1)

    def test_bad_first_batch_rolls_back(self):
        with CorpusStore(self.path) as store:
            with self.assertRaises(ValueError):
                store.ingest([record(), replace(record(), source="changed")])
            self.assertEqual(store.document_count(), 0)

    def test_repeat_counts_preserved(self):
        with CorpusStore(self.path) as store:
            store.ingest([record(text="Beni unut\nBeni unut\nBeni unut")])
            stats = store.stats()
            self.assertEqual(stats["syllable_histogram"], {4: 3})
            self.assertEqual(stats["common_endings"][0], ("unut", 3))

    def test_refrain_multiplicity_changes_digest(self):
        self.assertNotEqual(digest("Beni unut"), digest("Beni unut\nBeni unut"))

    def test_turkish_dotless_i_not_collapsed(self):
        self.assertNotEqual(digest("Kır"), digest("Kir"))

    def test_rights_do_not_default_to_production(self):
        row = record(rights="unknown")
        self.assertFalse(row.production_allowed)
        for rights in ["unknown", "restricted"]:
            with self.subTest(rights=rights), self.assertRaises(ValueError):
                replace(row, rights=rights, production_allowed=True)

    def test_rights_boolean_is_strict(self):
        with self.assertRaises(ValueError):
            record(production_allowed="false")

    def test_empty_content_rejected(self):
        for text in ["", "!!!", "[Chorus]"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                record(text=text)

    def test_malformed_jsonl_location(self):
        path = Path(self.temp.name) / "bad.jsonl"
        path.write_text('{}\n{"oops":', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "line 1"):
            read_jsonl(path)

    def test_missing_read_database_does_not_create_one(self):
        with self.assertRaises(ValueError):
            CorpusStore(self.path, create=False)
        self.assertFalse(self.path.exists())

    def test_unknown_schema_rejected(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("PRAGMA user_version = 999")
        with self.assertRaisesRegex(ValueError, "schema version"):
            CorpusStore(self.path)

    def test_foreign_database_not_repurposed(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("CREATE TABLE personal_notes (text TEXT)")
        with self.assertRaisesRegex(ValueError, "foreign database"):
            CorpusStore(self.path)

    def test_persistence_after_reopen(self):
        with CorpusStore(self.path) as store:
            store.ingest([record()])
        with CorpusStore(self.path, create=False) as store:
            self.assertEqual(store.document_count(), 1)


class SimilarityTests(unittest.TestCase):
    def test_exact_ignores_labels_case_and_punctuation(self):
        report = compare_texts("[Nakarat]\nBeni unut!", "BENİ UNUT")
        self.assertTrue(report["exact_document_match"])
        self.assertEqual(report["token_sequence_ratio"], 1.0)

    def test_dotted_and_dotless_i_stay_distinct(self):
        self.assertFalse(compare_texts("Kır", "Kir")["exact_document_match"])

    def test_empty_trigrams_do_not_return_perfect_score(self):
        report = compare_texts("Beni unut", "Beni unut")
        self.assertEqual(report["trigram_jaccard"], 0.0)

    def test_line_copy_detected_inside_different_song(self):
        report = compare_texts("Beni unut yeni bir güne uyan\nSana yolum yok", "Geri dön\nBeni unut yeni bir güne uyan")
        self.assertFalse(report["exact_document_match"])
        self.assertEqual(report["best_line_match"]["ratio"], 1.0)
        self.assertEqual(report["best_line_match"]["reference_line"], 2)

    def test_empty_corpus_not_reported_as_clear(self):
        with tempfile.TemporaryDirectory() as temp, CorpusStore(Path(temp) / "db.sqlite3") as store:
            report = check_corpus("Beni unut", store)
            self.assertEqual(report["status"], "not_checked_empty_corpus")
            self.assertIsNone(report["copyright_verdict"])

    def test_exact_match_ranked_first(self):
        with tempfile.TemporaryDirectory() as temp, CorpusStore(Path(temp) / "db.sqlite3") as store:
            store.ingest([record(), record("two", "Yeni bir gün\nSana başka yol")])
            report = check_corpus(record().text, store)
            self.assertTrue(report["matches"][0]["metrics"]["exact_document_match"])
            self.assertEqual(report["reference_documents"], 2)


if __name__ == "__main__":
    unittest.main()
