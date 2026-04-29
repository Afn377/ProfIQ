"""Tests for professor submissions."""
from __future__ import annotations

from unittest import mock

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from professors.models import Department, Professor


# Disable throttling in this test module.
THROTTLE_OFF = override_settings(
    REST_FRAMEWORK={
        "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
        "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
        "PAGE_SIZE": 25,
        "DEFAULT_THROTTLE_CLASSES": [],
        "DEFAULT_THROTTLE_RATES": {},
    },
)


@THROTTLE_OFF
class CreateProfessorHappyPathTests(APITestCase):
    """Successful create cases."""

    def setUp(self):
        self.url = reverse("professor-list")

    @mock.patch("professors.views._enqueue_lazy_analyze")
    def test_minimal_submission_creates_professor(self, mock_enqueue):
        before = Professor.objects.count()
        resp = self.client.post(
            self.url,
            data={"name": "Jane Doolittle", "institution": "Test State University"},
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        body = resp.json()
        self.assertTrue(body["created"])
        self.assertEqual(body["name"], "Jane Doolittle")
        self.assertEqual(body["institution"], "Test State University")
        self.assertIn("id", body)
        self.assertEqual(Professor.objects.count(), before + 1)
        # New rows should queue stats work.
        mock_enqueue.assert_called_once()

    @mock.patch("professors.views._enqueue_lazy_analyze")
    def test_optional_department_is_persisted(self, _mock_enqueue):
        dept = Department.objects.create(name="Mathematics")
        resp = self.client.post(
            self.url,
            data={
                "name": "Alan Curl",
                "institution": "Test State University",
                "department": dept.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        prof = Professor.objects.get(id=resp.json()["id"])
        self.assertEqual(prof.department_id, dept.id)

    @mock.patch("professors.views._enqueue_lazy_analyze")
    def test_whitespace_is_normalised(self, _mock_enqueue):
        resp = self.client.post(
            self.url,
            data={
                "name": "  Sara   van der  Berg  ",
                "institution": "Test\tState\nUniversity",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        body = resp.json()
        self.assertEqual(body["name"], "Sara van der Berg")
        self.assertEqual(body["institution"], "Test State University")


@THROTTLE_OFF
class CreateProfessorDedupTests(APITestCase):
    """Duplicate create cases."""

    def setUp(self):
        self.url = reverse("professor-list")
        self.existing = Professor.objects.create(
            name="Existing Person",
            institution="Test State University",
        )

    @mock.patch("professors.views._enqueue_lazy_analyze")
    def test_exact_duplicate_returns_existing_with_200(self, mock_enqueue):
        before = Professor.objects.count()
        resp = self.client.post(
            self.url,
            data={"name": "Existing Person", "institution": "Test State University"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        body = resp.json()
        self.assertFalse(body["created"])
        self.assertEqual(body["id"], self.existing.id)
        self.assertEqual(Professor.objects.count(), before)
        # Existing rows should not queue create-time stats work.
        mock_enqueue.assert_not_called()

    @mock.patch("professors.views._enqueue_lazy_analyze")
    def test_case_insensitive_dedup(self, _mock_enqueue):
        before = Professor.objects.count()
        resp = self.client.post(
            self.url,
            data={"name": "EXISTING person", "institution": "test state UNIVERSITY"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.json()["id"], self.existing.id)
        self.assertEqual(Professor.objects.count(), before)


@THROTTLE_OFF
class CreateProfessorValidationTests(APITestCase):
    """Validation cases."""

    def setUp(self):
        self.url = reverse("professor-list")

    def test_missing_name_rejected(self):
        resp = self.client.post(
            self.url, data={"institution": "Test University"}, format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", resp.json())

    def test_missing_institution_rejected(self):
        resp = self.client.post(self.url, data={"name": "Ada Lovelace"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("institution", resp.json())

    def test_too_short_name_rejected(self):
        resp = self.client.post(
            self.url, data={"name": "A", "institution": "Test University"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", resp.json())

    def test_no_letters_rejected(self):
        resp = self.client.post(
            self.url, data={"name": "12345", "institution": "Test University"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", resp.json())


@THROTTLE_OFF
class CreateProfessorCanaryRejectionTests(APITestCase):
    """Placeholder-name rejection cases."""

    def setUp(self):
        self.url = reverse("professor-list")

    def test_fictional_name_blocked(self):
        before = Professor.objects.count()
        resp = self.client.post(
            self.url,
            data={"name": "Albus Dumbledore", "institution": "Test University"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertIn("name", resp.json())
        self.assertEqual(Professor.objects.count(), before)

    def test_joke_name_blocked(self):
        resp = self.client.post(
            self.url,
            data={"name": "Anita Bath", "institution": "Test University"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertIn("name", resp.json())

    def test_fictional_institution_blocked(self):
        resp = self.client.post(
            self.url,
            data={
                "name": "Real Looking Person",
                "institution": "Hogwarts School of Witchcraft & Wizardry",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertIn("institution", resp.json())

    def test_borderline_name_still_allowed(self):
        # Common real names should stay allowed.
        resp = self.client.post(
            self.url,
            data={"name": "John Watson", "institution": "Test University"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
