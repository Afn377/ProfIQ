"""Tests for sentiment scoring helpers."""
from __future__ import annotations

import unittest

from sentiment.analyzer import (
    analyze_text,
    classify,
    _adjusted_compound,
    _rating_to_compound,
)


class IdiomNegativeTests(unittest.TestCase):
    """Negative phrase cases."""

    def test_avoid_like_the_plague(self):
        s = analyze_text("Avoid like the plague")
        self.assertEqual(s["label"], "negative")
        self.assertLessEqual(s["compound"], -0.5)

    def test_avoid_at_all_costs(self):
        s = analyze_text("Avoid at all costs.")
        self.assertEqual(s["label"], "negative")

    def test_do_not_take(self):
        s = analyze_text("Do not take this class.")
        self.assertEqual(s["label"], "negative")

    def test_would_not_recommend(self):
        s = analyze_text("Would not recommend, save your money.")
        self.assertEqual(s["label"], "negative")
        self.assertLessEqual(s["compound"], -0.5)

    def test_worst_professor(self):
        s = analyze_text("Worst professor I have ever had.")
        self.assertEqual(s["label"], "negative")

    def test_drop_this_class(self):
        s = analyze_text("Drop this class while you still can.")
        self.assertEqual(s["label"], "negative")


class LexiconTests(unittest.TestCase):
    """Single-word lexicon cases."""

    def test_useless(self):
        # "useless" should count as negative review wording.
        s = analyze_text("Useless lectures.")
        self.assertEqual(s["label"], "negative")

    def test_lifesaver(self):
        s = analyze_text("She is a lifesaver, take her class!")
        self.assertEqual(s["label"], "positive")

    def test_godsend(self):
        s = analyze_text("This professor is a godsend.")
        self.assertEqual(s["label"], "positive")

    def test_condescending(self):
        s = analyze_text("Condescending and rude.")
        self.assertEqual(s["label"], "negative")


class IdiomPositiveTests(unittest.TestCase):
    def test_highly_recommend(self):
        s = analyze_text("Highly recommend!")
        self.assertEqual(s["label"], "positive")
        self.assertGreaterEqual(s["compound"], 0.5)

    def test_best_professor(self):
        s = analyze_text("Best professor in the department.")
        self.assertEqual(s["label"], "positive")

    def test_goes_above_and_beyond(self):
        s = analyze_text("She goes above and beyond for her students.")
        self.assertEqual(s["label"], "positive")


class StarRatingBlendTests(unittest.TestCase):
    """Rating-blend cases."""

    def test_low_rating_pulls_positive_text_down(self):
        positive_text = "Great teacher"
        baseline = analyze_text(positive_text)["compound"]
        blended = analyze_text(positive_text, rating=1.0)["compound"]
        self.assertLess(blended, baseline)

    def test_high_rating_pulls_negative_text_up(self):
        negative_text = "Hard class."
        baseline = analyze_text(negative_text)["compound"]
        blended = analyze_text(negative_text, rating=5.0)["compound"]
        self.assertGreater(blended, baseline)

    def test_rating_3_is_neutral(self):
        # A 3-star rating contributes zero before weighting.
        text = "Decent professor."
        text_only = analyze_text(text)["compound"]
        with_rating = analyze_text(text, rating=3.0)["compound"]
        self.assertAlmostEqual(with_rating, text_only * 0.7, places=4)

    def test_rating_to_compound_mapping(self):
        self.assertAlmostEqual(_rating_to_compound(1.0), -1.0)
        self.assertAlmostEqual(_rating_to_compound(3.0), 0.0)
        self.assertAlmostEqual(_rating_to_compound(5.0), +1.0)


class HelperTests(unittest.TestCase):
    def test_classify_thresholds(self):
        self.assertEqual(classify(0.05), "positive")
        self.assertEqual(classify(-0.05), "negative")
        self.assertEqual(classify(0.0), "neutral")
        self.assertEqual(classify(0.04), "neutral")
        self.assertEqual(classify(-0.04), "neutral")

    def test_empty_text_returns_neutral(self):
        s = analyze_text("")
        self.assertEqual(s["label"], "neutral")
        self.assertEqual(s["compound"], 0.0)

    def test_compound_clamped(self):
        # Scores stay inside VADER's normal range.
        s = analyze_text(
            "Best professor ever. Highly recommend. Goes above and beyond. "
            "Saved my GPA. One of the best."
        )
        self.assertLessEqual(s["compound"], 1.0)
        self.assertGreaterEqual(s["compound"], -1.0)

    def test_idioms_dominate_weak_vader_signal(self):
        # The phrase should stay strongly negative.
        self.assertLessEqual(_adjusted_compound("Avoid like the plague"), -0.9)


class MLAugmentationTests(unittest.TestCase):
    """Optional ML fields and fallbacks."""

    def test_ml_fields_present_in_output(self):
        # Keep the response shape stable.
        s = analyze_text("Best professor ever.")
        self.assertIn("ml_label", s)
        self.assertIn("ml_confidence", s)
        self.assertIn("ml_model", s)

    def test_opinionless_question_forced_neutral(self):
        """Opinion-free questions should stay neutral."""
        from sentiment.ml import inference as ml_inference

        ml_inference.reset()

        cases = [
            "Anyone taken Prof Smith for CS101?",
            "Has anyone had Smith for the morning section?",
            "Is the final cumulative?",
            "Does this professor curve grades?",
            "What time does the class meet?",
            "Anyone know if Prof Smith offers extra credit?",
            # Longer question text should still be caught.
            (
                "What/how to study for sheflin macro iclicker quizzes? "
                "So the first clicker quiz for professor sheflin intro "
                "to macroecon/macro is coming up so I was wondering how "
                "and what should I study?"
            ),
            (
                "Class meets MWF at 9am. Section 002. Anyone tried "
                "the Tuesday lab?"
            ),
        ]
        for text in cases:
            with self.subTest(text=text):
                pred = ml_inference.predict(text)
                # No local artifact: just verify the guard.
                if pred is None:
                    self.assertTrue(ml_inference._is_opinionless_question(text))
                    continue
                self.assertEqual(pred.label, "neutral")
                self.assertIn("question_guard", pred.model)

    def test_question_with_opinion_still_runs_model(self):
        from sentiment.ml import inference as ml_inference

        # Opinion words should bypass the question guard.
        for text in (
            "Why is this professor so terrible?",
            "Can someone explain why everyone hates her?",
            "Is she really that amazing?",
        ):
            with self.subTest(text=text):
                self.assertFalse(ml_inference._is_opinionless_question(text))

    def test_ml_missing_artifact_falls_back_silently(self):
        from sentiment.ml import inference as ml_inference

        ml_inference.reset()
        # Missing artifacts should not break rule-based scoring.
        from pathlib import Path

        ml_inference.DEFAULT_CLF_PATH = Path("/nonexistent/sentiment_clf.joblib")
        try:
            s = analyze_text("Worst class I ever took.")
            self.assertEqual(s["label"], "negative")
            self.assertIsNone(s["ml_label"])
            self.assertIsNone(s["ml_confidence"])
        finally:
            ml_inference.reset()


class MLRecommenderTests(unittest.TestCase):
    """Recommender fallback cases."""

    def test_returns_none_or_empty_when_artifact_missing(self):
        from sentiment.ml import recommender

        from pathlib import Path

        recommender.reset()
        original_emb = recommender.DEFAULT_EMB_PATH
        original_warm = recommender.DEFAULT_WARM_PATH
        recommender.DEFAULT_EMB_PATH = Path("/nonexistent/prof_embeddings.npz")
        recommender.DEFAULT_WARM_PATH = Path("/nonexistent/prof_embeddings_warm.npz")
        try:
            self.assertFalse(recommender.is_available())
            self.assertIsNone(recommender.similar_by_external_ref("rmp:1", k=5))
        finally:
            recommender.DEFAULT_EMB_PATH = original_emb
            recommender.DEFAULT_WARM_PATH = original_warm
            recommender.reset()

    def test_add_embedding_warms_index_and_persists(self):
        """Warm-cache embeddings should survive reload."""
        import tempfile
        from pathlib import Path

        import numpy as np

        from sentiment.ml import recommender

        # Keep temp files inside the repo sandbox.
        repo_tmp = Path(__file__).resolve().parent.parent / "data" / "tmp"
        repo_tmp.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(repo_tmp)) as tmp:
            tmp_path = Path(tmp)
            base_path = tmp_path / "prof_embeddings.npz"
            warm_path = tmp_path / "prof_embeddings_warm.npz"

            # Tiny trained index.
            base_ids = np.asarray(["rmp:1", "rmp:2"], dtype=np.str_)
            base_names = np.asarray(["Alice @ X", "Bob @ Y"], dtype=np.str_)
            base_vecs = np.asarray(
                [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]],
                dtype="float32",
            )
            np.savez_compressed(base_path, ids=base_ids, names=base_names, vecs=base_vecs)

            # Stub encoder returns a fixed unit vector.
            class _StubEncoder:
                def encode(self, docs, **_):
                    out = np.zeros((len(docs), 4), dtype="float32")
                    out[:, 0] = 0.9
                    out[:, 2] = float(np.sqrt(1 - 0.81))  # unit norm
                    return out

            recommender.reset()
            original_emb = recommender.DEFAULT_EMB_PATH
            original_warm = recommender.DEFAULT_WARM_PATH
            recommender.DEFAULT_EMB_PATH = base_path
            recommender.DEFAULT_WARM_PATH = warm_path
            recommender._ENCODER = _StubEncoder()
            try:
                self.assertTrue(recommender.is_available())
                self.assertFalse(recommender.is_indexed("rmp:99"))

                ok = recommender.add_embedding(
                    "rmp:99", "New Prof @ Z", "great teacher very clear"
                )
                self.assertTrue(ok)
                self.assertTrue(recommender.is_indexed("rmp:99"))
                self.assertTrue(warm_path.exists())

                neighbors = recommender.similar_by_external_ref("rmp:99", k=2)
                self.assertIsNotNone(neighbors)
                self.assertGreaterEqual(len(neighbors), 1)
                # Closest row should share the x direction.
                self.assertEqual(neighbors[0].external_ref, "rmp:1")

                # Reload from disk and include the warm-cache row.
                recommender._ENCODER = None
                recommender.reset()
                recommender.DEFAULT_EMB_PATH = base_path
                recommender.DEFAULT_WARM_PATH = warm_path
                self.assertTrue(recommender.is_available())
                self.assertTrue(recommender.is_indexed("rmp:99"))
                self.assertEqual(recommender.num_indexed(), 3)
            finally:
                recommender.DEFAULT_EMB_PATH = original_emb
                recommender.DEFAULT_WARM_PATH = original_warm
                recommender.reset()

    def test_label_helpers(self):
        from sentiment.ml.labels import rating_to_label, vader_label, LABELS

        self.assertEqual(rating_to_label(1.0), "negative")
        self.assertEqual(rating_to_label(3.0), "neutral")
        self.assertEqual(rating_to_label(5.0), "positive")
        self.assertEqual(vader_label(0.5), "positive")
        self.assertEqual(vader_label(-0.5), "negative")
        self.assertEqual(vader_label(0.0), "neutral")
        self.assertEqual(set(LABELS), {"negative", "neutral", "positive"})


if __name__ == "__main__":
    unittest.main()
