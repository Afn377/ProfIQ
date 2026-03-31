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
