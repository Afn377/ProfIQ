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
