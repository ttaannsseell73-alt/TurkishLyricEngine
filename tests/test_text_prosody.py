import unittest

from turkish_lyric_engine.prosody import ProsodyPolicy, analyze_line, analyze_text, count_syllables
from turkish_lyric_engine.text import canonical_lyric, lower_tr, normalize_text, words


class TextTests(unittest.TestCase):
    def test_turkish_i_is_distinct(self):
        self.assertEqual(lower_tr("IŞIK İÇİN"), "ışık için")
        self.assertNotEqual(lower_tr("KIR"), lower_tr("KİR"))

    def test_decomposed_unicode(self):
        self.assertEqual(words("I\u0307ÇİM"), ["içim"])

    def test_normalization_keeps_repetition(self):
        text = "\ufeff[Kıta 1]\r\n  Bir   söz \r\n\r\n[Nakarat]\r\nBir söz\r\nBir söz"
        self.assertEqual(canonical_lyric(text), "Bir söz\nBir söz\nBir söz")

    def test_nonsection_brackets_are_content(self):
        self.assertEqual(canonical_lyric("[Sana kalan]\nGeri dön"), "[Sana kalan]\nGeri dön")

    def test_circumflex_and_soft_g(self):
        for word, expected in [("kâğıt", 2), ("rüzgâr", 2), ("dağ", 1), ("değil", 2), ("aile", 3)]:
            with self.subTest(word=word):
                self.assertEqual(count_syllables(word), expected)

    def test_apostrophe(self):
        self.assertEqual(count_syllables("Ankara’ya"), 4)
        self.assertEqual(words("Ankara’ya"), ["ankara'ya"])

    def test_numbers_are_not_silently_scored(self):
        report = analyze_line("2026 için bir söz")
        self.assertEqual(report["pronunciation_status"], "uncertain")
        self.assertIn("number_pronunciation_unknown", report["warnings"])

    def test_abbreviation_and_foreign_words(self):
        report = analyze_line("TR wow")
        self.assertEqual(report["pronunciation_status"], "uncertain")
        self.assertIn("no_vowel_or_abbreviation", report["warnings"])
        self.assertIn("foreign_pronunciation_unknown", report["warnings"])

    def test_free_meter_default(self):
        report = analyze_text("Ben seni değil, beklemeyi bıraktım.")
        self.assertIsNone(report["policy"]["target_syllables"])
        self.assertIsNone(report["lines"][0]["meter_deviation"])
        self.assertIsNone(report["quality_score"])

    def test_requested_meter_only(self):
        report = analyze_line("Beni unut sen artık", ProsodyPolicy(7, 0))
        self.assertEqual(report["orthographic_syllables"], 7)
        self.assertNotIn("outside_requested_meter", report["warnings"])
        mismatch = analyze_line("Beni unut", ProsodyPolicy(7, 0))
        self.assertIn("outside_requested_meter", mismatch["warnings"])

    def test_empty_text_no_success_score(self):
        report = analyze_text("[Chorus]\n")
        self.assertEqual(report["lines"], [])
        self.assertIsNone(report["syllable_range"])

    def test_policy_validation(self):
        for kwargs in [{"target_syllables": 0}, {"tolerance": -1}, {"long_line_warning": 0}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ProsodyPolicy(**kwargs)


if __name__ == "__main__":
    unittest.main()
