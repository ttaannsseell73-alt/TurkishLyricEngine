"""Run separately with TLE_REQUIRE_ZEYREK=1 in the morphology CI job."""

import os
from importlib.util import find_spec
import unittest

from turkish_lyric_engine.morphology import ZeyrekMorphology
from turkish_lyric_engine.rhyme import analyze_pair


AVAILABLE = find_spec("zeyrek") is not None
if os.environ.get("TLE_REQUIRE_ZEYREK") == "1" and not AVAILABLE:
    raise RuntimeError("Morphology integration requires a real installed Zeyrek backend")


@unittest.skipUnless(AVAILABLE, "optional real Zeyrek integration; exercised by separate CI job")
class ZeyrekIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider = ZeyrekMorphology()

    def test_real_analysis_reconstructs_surface(self):
        analyses = self.provider.analyze("geldim")
        self.assertEqual(len(analyses), 1)
        analysis = analyses[0]
        self.assertEqual(analysis.base_surface, "gel")
        self.assertEqual(analysis.lemma, "gelmek")
        self.assertEqual(analysis.base_surface + "".join(seg.surface for seg in analysis.suffixes), "geldim")

    def test_real_derivational_redif_separated(self):
        report = analyze_pair("yaralıyım", "hatalıyım", self.provider)
        self.assertEqual(report["status"], "base_ending_match")
        self.assertEqual(report["suffix_redif"], "lıyım")
        self.assertEqual(report["base_tail"], "a")
        self.assertEqual(report["rhyme_class_candidate"], "yarım")

    def test_real_ambiguity_stays_unresolved(self):
        analyses = self.provider.analyze("gülüm")
        self.assertGreater(len(analyses), 1)
        report = analyze_pair("gülüm", "külüm", self.provider)
        self.assertEqual(report["status"], "unresolved")

    def test_real_unknown_stays_unknown(self):
        self.assertEqual(self.provider.analyze("zzqqxy"), ())

    def test_allomorphic_suffixes_not_silently_chopped(self):
        report = analyze_pair("bekliyorum", "özlüyorum", self.provider)
        self.assertEqual(report["status"], "unresolved")
        self.assertEqual(report["reason"], "remaining_non_equivalent_suffixes")


if __name__ == "__main__":
    unittest.main()
