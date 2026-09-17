import unittest

from turkish_lyric_engine.meter import MeterSpec, analyze_meter, scan_durak


class MeterTests(unittest.TestCase):
    def test_seven_syllable_four_three(self):
        report = analyze_meter("Beni unut sen artık", MeterSpec(7, (4, 3)))
        self.assertTrue(report["all_lines_match"])
        self.assertEqual(report["lines"][0]["durak_checks"][0]["groups"], ["beni unut", "sen artık"])

    def test_eight_four_four(self):
        report = analyze_meter("Beni unut bana dönme", MeterSpec(8, (4, 4)))
        self.assertTrue(report["all_lines_match"])
        self.assertEqual(report["lines"][0]["durak_checks"][0]["status"], "compatible_word_boundaries")

    def test_eleven_six_five(self):
        report = analyze_meter("Beni unut artık bana geri dön", MeterSpec(11, (6, 5)))
        self.assertTrue(report["all_lines_match"])
        self.assertEqual(report["lines"][0]["durak_checks"][0]["groups"], ["beni unut artık", "bana geri dön"])

    def test_eleven_four_four_three(self):
        report = analyze_meter("Beni unut bana dönme sen artık", MeterSpec(11, (4, 4, 3)))
        self.assertTrue(report["all_lines_match"])
        self.assertEqual(report["lines"][0]["durak_checks"][0]["groups"], ["beni unut", "bana dönme", "sen artık"])

    def test_fourteen_seven_seven(self):
        report = analyze_meter("Beni unut sen artık yeni güne ben uyan", MeterSpec(14, (7, 7)))
        self.assertTrue(report["all_lines_match"])
        self.assertEqual(report["lines"][0]["durak_checks"][0]["status"], "compatible_word_boundaries")

    def test_durak_never_splits_a_word(self):
        check = scan_durak("Unutamadığım ben", (4, 3))
        self.assertEqual(check["status"], "incompatible")
        self.assertIn(4, check["missing_word_boundaries"])
        self.assertEqual(check["groups"], [])

    def test_mismatch_is_local_to_line(self):
        report = analyze_meter("Beni unut sen artık\nBeni unut", MeterSpec(7))
        self.assertFalse(report["all_lines_match"])
        self.assertEqual(report["summary"], {"matches": 1, "mismatch": 1})
        self.assertEqual(report["lines"][1]["deviation"], -3)

    def test_unknown_pronunciation_cannot_pass_meter(self):
        report = analyze_meter("7 beni unut sen artık", MeterSpec(7))
        self.assertEqual(report["lines"][0]["meter_status"], "uncertain")
        self.assertFalse(report["all_lines_match"])
        self.assertEqual(report["lines"][0]["durak_checks"][0]["status"], "uncertain")

    def test_free_meter_no_accidental_fixed_enforcement(self):
        report = analyze_meter("Beni unut\nYeni bir güne uyan")
        self.assertEqual(report["meter_type"], "free")
        self.assertIsNone(report["all_lines_match"])
        self.assertEqual(report["summary"], {"free_meter": 2})

    def test_empty_not_a_pass(self):
        self.assertFalse(analyze_meter("", MeterSpec(11))["all_lines_match"])

    def test_invalid_durak(self):
        for spec in [(None, (4, 3)), (11, (6, 6)), (7, (0, 7)), (7, (7,))]:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                MeterSpec(*spec)


if __name__ == "__main__":
    unittest.main()
