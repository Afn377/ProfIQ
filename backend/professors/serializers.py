import re

from rest_framework import serializers

from .models import Course, Department, Professor, ProfessorStats, Review

# Collapse runs of whitespace ("Jane   Doe" -> "Jane Doe").
_WS = re.compile(r"\s+")


class ProfessorListSerializer(serializers.ModelSerializer):
    # One row in the professor list / search results.

    department = serializers.CharField(source="department.name", read_only=True, default=None)
    recommendation_score = serializers.FloatField(
        source="stats.recommendation_score", read_only=True, default=0.0
    )
    review_count = serializers.IntegerField(
        source="stats.review_count", read_only=True, default=0
    )

    class Meta:
        model = Professor
        fields = [
            "id", "name", "department", "institution",
            "recommendation_score", "review_count",
            "source_avg_rating", "source_num_ratings", "external_ref",
        ]


class ProfessorCreateSerializer(serializers.ModelSerializer):
    """Input for POST /api/professors/."""

    # Not the model's default: the form must supply a school so we can dedup.
    institution = serializers.CharField(max_length=128)
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True,
    )

    class Meta:
        model = Professor
        fields = ["id", "name", "institution", "department"]
        read_only_fields = ["id"]
        # Switch off DRF's auto-generated unique-together validator (it 400s on
        # an exact duplicate). Duplicates are handled in validate() instead.
        validators = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.existing_instance = None

    def validate_name(self, value):
        cleaned = _WS.sub(" ", value.strip())
        if len(cleaned) < 2:
            raise serializers.ValidationError("Name must be at least 2 characters.")
        if not any(c.isalpha() for c in cleaned):
            raise serializers.ValidationError("Name must contain at least one letter.")
        return cleaned

    def validate_institution(self, value):
        cleaned = _WS.sub(" ", value.strip())
        if len(cleaned) < 2:
            raise serializers.ValidationError("School name must be at least 2 characters.")
        return cleaned

    def validate(self, attrs):
        # Case-insensitive duplicate check. The DB constraint is exact-case,
        # so "jane doe" @ "RUTGERS" would otherwise become a second row.
        existing = Professor.objects.filter(
            name__iexact=attrs["name"], institution__iexact=attrs["institution"],
        ).first()
        if existing is not None:
            self.existing_instance = existing
        return attrs

    def to_representation(self, instance):
        # Reply in the same shape as a list row (department as a name, etc.).
        return ProfessorListSerializer(instance).data


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "code"]


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ["id", "code", "title"]


class ReviewSerializer(serializers.ModelSerializer):
    source = serializers.CharField(source="source.name", read_only=True)
    course = serializers.CharField(source="course.code", read_only=True, default=None)

    class Meta:
        model = Review
        fields = ["id", "text", "rating", "source", "source_url", "course", "posted_at"]


class ProfessorStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfessorStats
        fields = [
            "review_count", "avg_compound",
            "positive_count", "neutral_count", "negative_count",
            "theme_counts", "recommendation_score", "updated_at",
        ]


class ProfessorDetailSerializer(serializers.ModelSerializer):
    """Full page for one professor: nested department, courses, stats, reviews."""

    department = DepartmentSerializer(read_only=True)
    courses = CourseSerializer(many=True, read_only=True)
    stats = ProfessorStatsSerializer(read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)

    class Meta:
        model = Professor
        fields = [
            "id", "name", "department", "institution", "bio",
            "courses", "stats", "reviews",
            "source_avg_rating", "source_num_ratings", "external_ref",
        ]
