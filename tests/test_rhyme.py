from pathlib import Path
import json
import tempfile
import unittest

from turkish_lyric_engine.morphology import AnnotationMorphology, MorphAnalysis, Segment
from turkish_lyric_engine.rhyme import analyze_pair


def noun(word, base, suffix="ler", function="noun_plural"):
    return MorphAnalysis(word, base, base, (Segment(suffix, function),) if suffix else (), "test:reviewed")


class RhymeTests(unittest.TestCase):
    def test_reviewed_redif_rhyme_regression_fixture(self):
        fixtures = json.loads((Path(__file__).parent / 'fixtures' / 'redif_rhyme_regressions.json').read_text(encoding='utf-8'))
        for fixture in fixtures:
            entries = [MorphAnalysis(row['word'],row['base_surface'],row['lemma'],tuple(Segment(**s) for s in row['suffixes']),row['evidence']) for row in fixture['analyses']]
            with self.subTest(left=fixture['left'],right=fixture['right']):
                report = analyze_pair(fixture['left'],fixture['right'],AnnotationMorphology(entries))
                for name,value in fixture['expected'].items():
                    self.assertEqual(report[name],value)

    def test_redif_separated_from_true_base_tail(self):
        provider = AnnotationMorphology([noun("güller", "gül"), noun("küller", "kül")])
        report = analyze_pair("Kalan güller", "Solan küller", provider)
        self.assertEqual(report["suffix_redif"], "ler")
        self.assertEqual(report["base_tail"], "ül")
        self.assertEqual(report["status"], "base_ending_match")
        self.assertEqual(report["rhyme_class_candidate"], "tam")

    def test_only_suffix_is_not_rhyme(self):
        provider = AnnotationMorphology([noun("kızlar", "kız", "lar"), noun("atlar", "at", "lar")])
        report = analyze_pair("kızlar", "atlar", provider)
        self.assertEqual(report["suffix_redif"], "lar")
        self.assertEqual(report["base_tail"], "")
        self.assertEqual(report["status"], "redif_only")

    def test_same_spelling_different_functions_is_not_redif(self):
        provider = AnnotationMorphology([noun("güller", "gül", function="noun_plural"),
                                         noun("küller", "kül", function="verb_third_plural")])
        report = analyze_pair("güller", "küller", provider)
        self.assertEqual(report["suffix_redif"], "")
        self.assertEqual(report["status"], "unresolved")
        self.assertEqual(report["reason"], "remaining_non_equivalent_suffixes")

    def test_unknown_does_not_claim_rhyme(self):
        report = analyze_pair("bekliyorum", "özlüyorum")
        self.assertEqual(report["surface_tail"], "yorum")
        self.assertEqual(report["status"], "unresolved")
        self.assertEqual(report["base_tail"], "")

    def test_ambiguous_parse_does_not_choose_first(self):
        provider = AnnotationMorphology([noun("güller", "gül"),
                                         noun("güller", "gül", function="verb_third_plural"), noun("küller", "kül")])
        report = analyze_pair("güller", "küller", provider)
        self.assertEqual(report["status"], "unresolved")
        self.assertEqual(report["morphology_candidate_counts"], [2, 1])

    def test_word_and_suffix_redif_can_coexist(self):
        provider = AnnotationMorphology([noun("güller", "gül"), noun("küller", "kül")])
        report = analyze_pair("Güller bana kaldı", "Küller bana kaldı", provider)
        self.assertEqual(report["word_redif"], "bana kaldı")
        self.assertEqual(report["word_redif_status"], "candidate_requires_same_meaning_and_function")
        self.assertEqual(report["suffix_redif"], "ler")
        self.assertEqual(report["base_tail"], "ül")

    def test_full_line_repetition_is_not_rhyme(self):
        report = analyze_pair("Beni unut", "Beni unut")
        self.assertEqual(report["status"], "repetition_only")
        self.assertEqual(report["word_redif"], "beni unut")
        self.assertIsNone(report["rhyme_class_candidate"])

    def test_missing_ending(self):
        self.assertEqual(analyze_pair("!!!", "bana")["reason"], "missing_ending")

    def test_invalid_reconstruction_is_rejected(self):
        with self.assertRaises(ValueError):
            noun("güller", "gül", "lar")

    def test_invalid_annotations(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "invalid.json"
            for data in ["{}", '[{"word":"güller"}]', '[null]']:
                file.write_text(data, encoding="utf-8")
                with self.subTest(data=data), self.assertRaises(ValueError):
                    AnnotationMorphology.from_file(file)

    def test_duplicate_annotations_do_not_create_ambiguity(self):
        analysis = noun("güller", "gül")
        self.assertEqual(len(AnnotationMorphology([analysis, analysis]).analyze("GÜLLER")), 1)


if __name__ == "__main__":
    unittest.main()
