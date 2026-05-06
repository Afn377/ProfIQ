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


class RecommendationScoreTests(unittest.TestCase):
    def test_many_good_reviews_beat_one_glowing_review(self):
        from sentiment.analyzer import compute_recommendation_score as score
        one_glowing = score(avg_compound=0.95, positive_ratio=1.0, review_count=1)
        many_good = score(avg_compound=0.60, positive_ratio=0.9, review_count=200)
        self.assertGreater(many_good, one_glowing)

    def test_one_review_stays_near_the_middle(self):
        from sentiment.analyzer import compute_recommendation_score as score
        self.assertLess(score(0.95, 1.0, 1), 65)
        self.assertGreater(score(-0.9, 0.0, 1), 35)

    def test_more_reviews_move_further_from_the_middle(self):
        from sentiment.analyzer import compute_recommendation_score as score
        s1 = score(0.8, 1.0, 1)
        s10 = score(0.8, 1.0, 10)
        s100 = score(0.8, 1.0, 100)
        self.assertLess(s1, s10)
        self.assertLess(s10, s100)


class InferenceTests(unittest.TestCase):
    def setUp(self):
        from sentiment.ml import inference
        inference.reset()
        self.inference = inference

    def tearDown(self):
        self.inference.reset()

    def test_missing_model_degrades_to_none(self):
        from unittest.mock import patch
        from pathlib import Path
        with patch.object(self.inference, "CLF_PATH", Path("/nonexistent.joblib")):
            self.assertIsNone(self.inference.predict("Great class"))
            self.assertFalse(self.inference.is_available())

    def test_analyzer_works_without_model(self):
        from unittest.mock import patch
        from pathlib import Path
        with patch.object(self.inference, "CLF_PATH", Path("/nonexistent.joblib")):
            r = analyze_text("Great class, would recommend.")
        self.assertEqual(r["label"], "positive")
        self.assertIsNone(r["ml_label"])

    def test_question_is_neutral_without_the_model(self):
        r = self.inference.predict("Does he curve the final?")
        self.assertEqual(r["label"], "neutral")
        self.assertEqual(r["model"], "question_guard")


class RecommenderTests(unittest.TestCase):
    """Run against a tiny hand-made index so no model or file is needed."""

    def setUp(self):
        import numpy as np
        from sentiment.ml import recommender as r
        self.r = r
        v = np.array([[1, 0, 0], [0.9, 0.1, 0], [0.2, 1, 0], [0, 0, 1]], dtype="float32")
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        ids = np.array(["a", "b", "c", "d"]); names = np.array(["A", "B", "C", "D"])
        r._INDEX = (ids, names, v, {e: i for i, e in enumerate(ids)})

    def tearDown(self):
        self.r._INDEX = None

    def test_nearest_is_correct_and_self_excluded(self):
        out = self.r.similar("a", k=2)
        self.assertEqual([n.external_ref for n in out], ["b", "c"])
        self.assertNotIn("a", [n.external_ref for n in out])
        # Restricted to a candidate set (same department and school), the
        # closest overall ("b") is not eligible, so "c" is the answer.
        out = self.r.similar("a", k=2, among={"c", "d"})
        self.assertEqual([n.external_ref for n in out], ["c"])

    def test_unknown_ref_returns_empty(self):
        self.assertEqual(self.r.similar("zzz"), [])

    def test_missing_file_is_unavailable(self):
        from unittest.mock import patch
        from pathlib import Path
        self.r._INDEX = None
        with patch.object(self.r, "EMB_PATH", Path("/nonexistent.npz")):
            self.assertFalse(self.r.is_available())
