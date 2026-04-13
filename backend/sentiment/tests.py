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


class RatingBlendTests(unittest.TestCase):
    def test_low_rating_pulls_down_and_high_pulls_up(self):
        low = analyze_text("It was ok.", rating=1.0)["compound"]
        high = analyze_text("It was ok.", rating=5.0)["compound"]
        self.assertLess(low, high)

    def test_no_rating_leaves_text_score_alone(self):
        plain = analyze_text("Great lectures, would recommend.")["compound"]
        self.assertAlmostEqual(plain, 0.8)

    def test_three_stars_is_neutral_pull(self):
        from sentiment.analyzer import _rating_to_compound
        self.assertEqual(_rating_to_compound(3.0), 0.0)
        self.assertEqual(_rating_to_compound(1.0), -1.0)
        self.assertEqual(_rating_to_compound(5.0), 1.0)


class ThemeTests(unittest.TestCase):
    def test_finds_named_themes(self):
        from sentiment.analyzer import extract_themes
        themes = extract_themes("Clear lectures, fair grading, tough exams.")
        self.assertIn("clarity", themes)
        self.assertIn("fairness", themes)
        self.assertIn("grading", themes)

    def test_does_not_match_inside_other_words(self):
        from sentiment.analyzer import extract_themes
        # "hardly" is not "hard"; "unfair" contains "fair" but is its own word.
        themes = extract_themes("He is hardly ever around.")
        self.assertNotIn("workload", themes)
