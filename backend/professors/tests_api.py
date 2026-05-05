from django.test import TestCase

from .models import Course, Department, Professor, ProfessorStats


class ProfessorListQueryCountTests(TestCase):
    def setUp(self):
        for i in range(30):
            dept = Department.objects.create(name=f"Department {i}")
            prof = Professor.objects.create(
                name=f"Professor {i:02d}", institution="Rutgers", department=dept,
            )
            ProfessorStats.objects.create(
                professor=prof, review_count=10, recommendation_score=50 + i,
            )

    def test_list_uses_constant_number_of_queries(self):
        # One page of professors should cost the same number of queries whether
        # the page holds 5 professors or 25: one COUNT for pagination, one SELECT
        # for the page.
        with self.assertNumQueries(2):
            response = self.client.get("/api/professors/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 25)


class ProfessorSearchTests(TestCase):
    def test_search_by_course_code_returns_each_professor_once(self):
        prof = Professor.objects.create(name="Ann Lee", institution="Rutgers")
        for code in ["CS 111", "CS 112", "CS 210"]:
            Course.objects.create(code=code).professors.add(prof)

        response = self.client.get("/api/professors/?q=CS")

        names = [row["name"] for row in response.json()["results"]]
        self.assertEqual(names, ["Ann Lee"])


class CompareTests(TestCase):
    def test_non_numeric_id_returns_400(self):
        response = self.client.get("/api/compare/?ids=1,abc")
        self.assertEqual(response.status_code, 400)
        self.assertIn("ids", response.json())

    def test_empty_ids_returns_400(self):
        response = self.client.get("/api/compare/")
        self.assertEqual(response.status_code, 400)

    def test_returns_theme_counts_per_professor(self):
        prof = Professor.objects.create(name="Ann Lee", institution="Rutgers")
        ProfessorStats.objects.create(professor=prof, theme_counts={"clarity": 3})
        response = self.client.get(f"/api/compare/?ids={prof.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["theme_counts"], {"clarity": 3})


class ProvenanceTests(TestCase):
    def test_seed_professor_never_in_top_list_and_score_hidden(self):
        prof = Professor.objects.create(name="Avery Stone", institution="State University")
        ProfessorStats.objects.create(
            professor=prof, review_count=15, recommendation_score=90.0,
            analysis_source=ProfessorStats.SEED,
        )
        summary = self.client.get("/api/summary/").json()
        self.assertEqual(summary["top_professors"], [])
        row = self.client.get("/api/professors/?q=avery").json()["results"][0]
        self.assertIsNone(row["recommendation_score"])


class LazyAnalyzeTests(TestCase):
    def setUp(self):
        import professors.views as v
        v._in_progress.clear()
        self.prof = Professor.objects.create(name="Ann Lee", institution="Rutgers", external_ref="rmp:1")

    def test_enqueue_refuses_a_professor_already_in_progress(self):
        import professors.views as v
        from unittest.mock import patch
        with patch.object(v.threading, "Thread") as thread:
            first = v._enqueue_analyze(self.prof.id)
            second = v._enqueue_analyze(self.prof.id)
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(thread.call_count, 1)

    def test_analysis_writes_live_stats_and_frees_the_slot(self):
        import professors.views as v
        from unittest.mock import patch
        fake = [{"comment": "Great lectures, would recommend.", "helpfulRating": 5, "clarityRating": 5}] * 3
        v._in_progress.add(self.prof.id)
        with patch.object(v._rmp_client, "iter_ratings", return_value=iter(fake)):
            v._analyze_professor(self.prof.id)
        stats = ProfessorStats.objects.get(professor=self.prof)
        self.assertEqual(stats.review_count, 3)
        self.assertEqual(stats.analysis_source, ProfessorStats.LIVE_RMP)
        self.assertNotIn(self.prof.id, v._in_progress)

    def test_slot_is_freed_even_when_the_fetch_fails(self):
        import professors.views as v
        from unittest.mock import patch
        v._in_progress.add(self.prof.id)
        with patch.object(v._rmp_client, "iter_ratings", side_effect=ConnectionError("boom")):
            with self.assertRaises(ConnectionError):
                v._analyze_professor(self.prof.id)
        self.assertNotIn(self.prof.id, v._in_progress)


class PrefixBoundTests(TestCase):
    def test_increments_last_char(self):
        from professors.views import _prefix_upper_bound
        self.assertEqual(_prefix_upper_bound("rut"), "ruu")
        self.assertEqual(_prefix_upper_bound("a"), "b")

    def test_autocomplete_is_prefix_only_and_case_insensitive(self):
        Professor.objects.create(name="A", institution="Rutgers")
        Professor.objects.create(name="B", institution="Truthful College")   # contains "rut", not a prefix
        names = [r["name"] for r in self.client.get("/api/institutions/?q=RUT").json()]
        self.assertEqual(names, ["Rutgers"])


class SeedStatsReanalysisTests(TestCase):
    # Imported seed stats have counts but no themes. Opening the page should
    # queue a live analysis the same way it does for a professor with no stats.
    def setUp(self):
        import professors.views as v
        v._in_progress.clear()
        self.prof = Professor.objects.create(name="Mark Ogletree", institution="Rutgers", external_ref="rmp:1488853")
        ProfessorStats.objects.create(
            professor=self.prof, review_count=2326, recommendation_score=70,
            analysis_source=ProfessorStats.SEED, theme_counts={},
        )

    def test_detail_queues_analysis_for_seed_stats(self):
        import professors.views as v
        from unittest.mock import patch
        with patch.object(v, "_enqueue_analyze", return_value=True) as enqueue:
            response = self.client.get(f"/api/professors/{self.prof.id}/")
        self.assertEqual(response.status_code, 200)
        enqueue.assert_called_once_with(self.prof.id)
        self.assertEqual(response["X-ProfIQ-Analyze"], "queued")

    def test_detail_does_not_requeue_live_stats(self):
        import professors.views as v
        from unittest.mock import patch
        self.prof.stats.analysis_source = ProfessorStats.LIVE_RMP
        self.prof.stats.save()
        with patch.object(v, "_enqueue_analyze", return_value=True) as enqueue:
            self.client.get(f"/api/professors/{self.prof.id}/")
        enqueue.assert_not_called()


class LiveReviewsTests(TestCase):
    def setUp(self):
        import professors.views as v
        v._page_cache.clear()
        self.prof = Professor.objects.create(name="Ann Lee", institution="Rutgers", external_ref="rmp:1")

    def test_live_review_carries_the_ml_label(self):
        import professors.views as v
        from unittest.mock import patch
        node = {"comment": "Great lectures, would recommend.", "helpfulRating": 5, "clarityRating": 5, "class": "CS101"}
        with patch.object(v._rmp_client, "fetch_ratings_page", return_value=([node], None, False)):
            response = self.client.get(f"/api/professors/{self.prof.id}/reviews/")
        self.assertEqual(response.status_code, 200)
        sentiment = response.json()["results"][0]["sentiment"]
        self.assertIn("ml_label", sentiment)
        self.assertIn("ml_confidence", sentiment)
