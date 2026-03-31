from django.test import TestCase

from .models import Department, Professor, ProfessorStats


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
