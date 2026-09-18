"""Durable user feedback and empirical preferences; never invent GOLD/RED labels."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sqlite3

from .contracts import fingerprint, string


class FeedbackStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        try:
            existing = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if existing and (existing != {"feedback"} or version != 1):
                raise ValueError("not a recognized feedback database")
            self.db.executescript("""CREATE TABLE IF NOT EXISTS feedback (
                id TEXT PRIMARY KEY, run_id TEXT NOT NULL, genre TEXT NOT NULL,
                decision TEXT NOT NULL, original TEXT NOT NULL, replacement TEXT,
                mechanism_id TEXT NOT NULL, hook_words INTEGER NOT NULL,
                note TEXT NOT NULL);
                PRAGMA user_version = 1;""")
        except Exception:
            self.db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.db.close()

    def add(self, *, run_id: str, genre: str, decision: str, original: str,
            mechanism_id: str, hook_words: int, replacement: str | None = None, note: str = "") -> str:
        for name, value in (("run_id", run_id), ("genre", genre), ("original", original), ("mechanism_id", mechanism_id)):
            string(value, name, 10000)
        if decision not in {"accept", "reject", "edit"}:
            raise ValueError("feedback decision must be accept/reject/edit")
        if decision == "edit" and not replacement:
            raise ValueError("edit feedback requires replacement")
        if replacement is not None:
            string(replacement, "replacement", 10000)
        if type(hook_words) is not int or not 1 <= hook_words <= 30 or not isinstance(note, str):
            raise ValueError("invalid feedback metadata")
        row = (run_id, genre, decision, original, replacement, mechanism_id, hook_words, note)
        identity = fingerprint(row)
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO feedback VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (identity, *row))
        return identity

    def preferences(self, genre: str) -> dict:
        rows = list(self.db.execute("SELECT * FROM feedback WHERE genre = ? ORDER BY id", (genre,)))
        positives, negatives, hook_lengths = Counter(), Counter(), Counter()
        for row in rows:
            if row["decision"] in {"accept", "edit"}:
                positives[row["mechanism_id"]] += 1
                hook_lengths[row["hook_words"]] += 1
            else:
                negatives[row["mechanism_id"]] += 1
        return {"status": "empirical_feedback" if rows else "no_user_feedback", "genre": genre,
                "sample_count": len(rows), "mechanism_accepts": dict(positives), "mechanism_rejects": dict(negatives),
                "accepted_hook_lengths": dict(hook_lengths),
                "learning_method": "genre_conditioned_counts_no_model_training",
                "raw_lyrics_in_prompt": False}
