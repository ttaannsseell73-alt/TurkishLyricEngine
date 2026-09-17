from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from turkish_lyric_engine.cli import main


class CliTests(unittest.TestCase):
    def call(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(args)
        return code, out.getvalue(), err.getvalue()

    def test_meter_cli_returns_report(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.txt"
            path.write_text("Beni unut sen artık", encoding="utf-8")
            code, out, err = self.call(["meter", str(path), "--syllables", "7", "--durak", "4+3"])
            self.assertEqual(code, 0, err)
            self.assertTrue(json.loads(out)["all_lines_match"])

    def test_invalid_durak_is_clear_error(self):
        code, out, err = self.call(["meter", "missing.txt", "--syllables", "11", "--durak", "6+6"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("sum", err)

    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "report.json"
            output.write_text("important", encoding="utf-8")
            code, out, err = self.call(["rhyme", "bana", "sana", "--output", str(output)])
            self.assertEqual(code, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "important")

    def test_full_ingest_stats_similarity_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "db.sqlite3"
            fixture = Path(__file__).resolve().parents[1] / "examples" / "archive.jsonl"
            code, out, err = self.call(["ingest", str(fixture), "--db", str(db)])
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out)["inserted_documents"], 2)
            code, out, err = self.call(["stats", "--db", str(db)])
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out)["unique_documents"], 2)
            lyric = fixture.parent / "lyric_11.txt"
            code, out, err = self.call(["similarity", str(lyric), "--db", str(db)])
            self.assertEqual(code, 0, err)
            self.assertTrue(json.loads(out)["matches"][0]["metrics"]["exact_document_match"])

    def test_invalid_archive_does_not_create_database(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "db.sqlite3"
            archive = Path(temp) / "bad.jsonl"
            archive.write_text('{}', encoding="utf-8")
            code, out, err = self.call(["ingest", str(archive), "--db", str(db)])
            self.assertEqual(code, 2)
            self.assertFalse(db.exists())


if __name__ == "__main__":
    unittest.main()
