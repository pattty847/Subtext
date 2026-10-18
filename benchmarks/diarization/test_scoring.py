"""Guard against scoring arbitrary speaker names as identity errors."""
import tempfile
import unittest
from pathlib import Path
from benchmark import score

class ScoringTest(unittest.TestCase):
    def test_permuted_labels_are_equivalent_and_merging_is_penalized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            ref=root/'ref.rttm'
            ref.write_text('SPEAKER clip 1 0 5 <NA> <NA> A <NA> <NA>\nSPEAKER clip 1 5 5 <NA> <NA> B <NA> <NA>\n')
            hyp=root/'hyp.rttm'
            hyp.write_text('SPEAKER other 1 0 5 <NA> <NA> Y <NA> <NA>\nSPEAKER other 1 5 5 <NA> <NA> X <NA> <NA>\n')
            self.assertEqual(score(ref,hyp,10)['DER_collar_0.0'],0)
            hyp.write_text('SPEAKER other 1 0 10 <NA> <NA> X <NA> <NA>\n')
            result=score(ref,hyp,10)
            self.assertAlmostEqual(result['speaker_confusion_rate'],0.5)
            self.assertEqual(result['predicted_speakers'],1)

    def test_empty_prediction_counts_as_missed_speech(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            ref=root/'ref.rttm'
            hyp=root/'hyp.rttm'
            ref.write_text('SPEAKER clip 1 0 5 <NA> <NA> A <NA> <NA>\n')
            hyp.write_text('')
            result=score(ref,hyp,10)
            self.assertEqual(result['DER_collar_0.0'],1.0)
            self.assertEqual(result['missed_detection_seconds'],5.0)

if __name__=='__main__':
    unittest.main()
