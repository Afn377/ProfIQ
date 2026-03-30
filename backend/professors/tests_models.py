from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from .models import Course, Department, Professor, Review, Source


class NameInstitutionConstraintTests(TestCase):
    """unique (name, institution) — only enforced when external_ref is blank."""

    def test_duplicate_hand_added_professor_rejected(self):
        # Both rows have no external_ref, so the name rule applies.
        Professor.objects.create(name="John Smith", institution="Rutgers")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Professor.objects.create(name="John Smith", institution="Rutgers")

    def test_same_name_at_different_institution_allowed(self):
        Professor.objects.create(name="John Smith", institution="Rutgers")
        Professor.objects.create(name="John Smith", institution="Princeton")
        self.assertEqual(Professor.objects.count(), 2)

    def test_same_name_same_institution_allowed_with_different_refs(self):
        # Two different crawled John Smiths at Rutgers: the name rule must NOT apply.
        Professor.objects.create(name="John Smith", institution="Rutgers", external_ref="rmp:1")
        Professor.objects.create(name="John Smith", institution="Rutgers", external_ref="rmp:2")
        self.assertEqual(Professor.objects.count(), 2)

    def test_hand_added_and_crawled_same_name_both_allowed(self):
        # The known gap from commit 63e5725: one blank ref, one "rmp:1", same name + school.
        Professor.objects.create(name="John Smith", institution="Rutgers")
        Professor.objects.create(name="John Smith", institution="Rutgers", external_ref="rmp:1")
        self.assertEqual(Professor.objects.count(), 2)


class ExternalRefConstraintTests(TestCase):
    """unique external_ref — only enforced when external_ref is NOT blank."""

    def test_multiple_blank_external_refs_allowed(self):
        Professor.objects.create(name="A", institution="Rutgers", external_ref="")
        Professor.objects.create(name="B", institution="Rutgers", external_ref="")
        self.assertEqual(Professor.objects.count(), 2)

    def test_duplicate_external_ref_rejected(self):
        Professor.objects.create(name="A", institution="Rutgers", external_ref="rmp:1")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Professor.objects.create(name="B", institution="Rutgers", external_ref="rmp:1")


class OnDeleteTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name="Computer Science", code="CS")
        self.prof = Professor.objects.create(
            name="Ann Lee", institution="Rutgers", department=self.dept,
        )
        self.course = Course.objects.create(code="CS 210", title="Data Management")
        self.source = Source.objects.create(name="RateMyProfessors")
        self.review = Review.objects.create(
            professor=self.prof, course=self.course, source=self.source,
            text="Great lecturer", rating=5,
        )

    def test_deleting_department_keeps_professor(self):
        self.dept.delete()
        self.prof.refresh_from_db()
        self.assertIsNone(self.prof.department)

    def test_deleting_course_keeps_review(self):
        self.course.delete()
        self.review.refresh_from_db()
        self.assertIsNone(self.review.course)

    def test_deleting_professor_deletes_reviews(self):
        self.prof.delete()
        with self.assertRaises(Review.DoesNotExist):
            self.review.refresh_from_db()

    def test_deleting_source_with_reviews_is_blocked(self):
        with self.assertRaises(ProtectedError):
            self.source.delete()
