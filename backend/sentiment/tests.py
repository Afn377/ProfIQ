import unittest

from sentiment.analyzer import analyze_text, classify


class ClassifyThresholdTests(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(classify(0.5), "positive")
        self.assertEqual(classify(0.05), "positive")
        self.assertEqual(classify(0.0), "neutral")
        self.assertEqual(classify(-0.05), "negative")


class DomainPhraseTests(unittest.TestCase):
    """Reviews a student would read one way that general-English VADER reads another."""

    def test_avoid_at_all_costs(self):
        self.assertEqual(analyze_text("Avoid him at all costs.")["label"], "negative")

    def test_do_not_take(self):
        self.assertEqual(analyze_text("Do not take this class.")["label"], "negative")

    def test_would_not_recommend(self):
        self.assertEqual(analyze_text("Would not recommend.")["label"], "negative")

    def test_start_praying(self):
        self.assertEqual(
            analyze_text("If you don't have a religion, pick one and start praying.")["label"],
            "negative",
        )

    def test_easy_a(self):
        self.assertEqual(analyze_text("Easy A, saved my GPA.")["label"], "positive")

    def test_hard_but_cares(self):
        self.assertEqual(
            analyze_text("Hardest class I have ever taken but he really cares.")["label"],
            "positive",
        )

    def test_warning_beats_praise(self):
        # The recommendation is the point; the adjective shouldn't win.
        self.assertEqual(
            analyze_text("Amazing lectures but do not take this class.")["label"],
            "negative",
        )

    def test_warning_beats_a_pile_of_praise(self):
        # No amount of adjectives should outvote an explicit "do not take".
        text = "Amazing, brilliant, best professor ever, super engaging, do not take this class."
        self.assertEqual(analyze_text(text)["label"], "negative")
