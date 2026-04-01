from django.test import TestCase

from .models import Department, Professor


class ProfessorCreateTests(TestCase):
    URL = "/api/professors/"

    def post(self, body):
        return self.client.post(self.URL, body, content_type="application/json")

    # --- happy path -------------------------------------------------------

    def test_valid_submission_creates_professor(self):
        response = self.post({"name": "Jane Doe", "institution": "Rutgers"})

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["created"])
        self.assertEqual(Professor.objects.count(), 1)

    def test_whitespace_in_name_is_collapsed(self):
        response = self.post({"name": "  Jane   Doe ", "institution": "Rutgers"})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["name"], "Jane Doe")

    def test_optional_department_is_accepted(self):
        dept = Department.objects.create(name="Computer Science")

        response = self.post({"name": "Jane Doe", "institution": "Rutgers", "department": dept.id})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["department"], "Computer Science")

    # --- validation -------------------------------------------------------

    def test_name_shorter_than_two_chars_rejected(self):
        response = self.post({"name": "J", "institution": "Rutgers"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.json())

    def test_name_without_a_letter_rejected(self):
        response = self.post({"name": "1234", "institution": "Rutgers"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.json())

    def test_missing_institution_rejected(self):
        response = self.post({"name": "Jane Doe"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("institution", response.json())

    def test_institution_shorter_than_two_chars_rejected(self):
        response = self.post({"name": "Jane Doe", "institution": "R"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("institution", response.json())

    # --- duplicates -------------------------------------------------------

    def test_exact_duplicate_returns_existing_with_200(self):
        first = self.post({"name": "Jane Doe", "institution": "Rutgers"})
        second = self.post({"name": "Jane Doe", "institution": "Rutgers"})

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["created"])
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual(Professor.objects.count(), 1)

    def test_case_insensitive_duplicate_returns_existing_with_200(self):
        first = self.post({"name": "Jane Doe", "institution": "Rutgers"})
        second = self.post({"name": "jane doe", "institution": "RUTGERS"})

        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual(Professor.objects.count(), 1)


class ProfessorThrottleTests(TestCase):
    def test_reads_are_not_rate_limited(self):
        # A user browsing the catalog should never be told to slow down.
        for _ in range(25):
            response = self.client.get("/api/professors/")
            self.assertEqual(response.status_code, 200)
