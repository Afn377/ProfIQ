import re

from rest_framework import serializers
from .canary_data import (
    FICTIONAL_INSTITUTIONS_NORMALISED,
    KNOWN_JOKES,
    OBVIOUS_FICTIONAL,
    normalise_name,
)
from .models import (
    Department, Professor, Course, Source, Review, SentimentResult, ProfessorStats,
)


# Collapse pasted whitespace before validation.
_WS = re.compile(r"\s+")


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "code"]


class SourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Source
        fields = ["id", "name", "base_url"]


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ["id", "code", "title"]


class SentimentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SentimentResult
        fields = ["compound", "positive", "neutral", "negative", "label", "themes"]


class ReviewSerializer(serializers.ModelSerializer):
    source = serializers.CharField(source="source.name", read_only=True)
    course = serializers.CharField(source="course.code", read_only=True, default=None)
    sentiment = SentimentSerializer(read_only=True)

    class Meta:
        model = Review
        fields = [
            "id", "text", "rating", "source", "source_url",
            "course", "posted_at", "sentiment",
        ]


class ProfessorStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfessorStats
        fields = [
            "review_count", "avg_compound",
            "positive_count", "neutral_count", "negative_count",
            "theme_counts", "recommendation_score", "updated_at",
        ]


class ProfessorListSerializer(serializers.ModelSerializer):
    """Serializer for professor list rows."""

    department = serializers.CharField(source="department.name", read_only=True, default=None)
    recommendation_score = serializers.FloatField(
        source="stats.recommendation_score", read_only=True, default=0.0
    )
    review_count = serializers.IntegerField(
        source="stats.review_count", read_only=True, default=0
    )
    avg_compound = serializers.FloatField(
        source="stats.avg_compound", read_only=True, default=0.0
    )

    class Meta:
        model = Professor
        fields = [
            "id", "name", "department", "institution",
            "recommendation_score", "review_count", "avg_compound",
            "source_avg_rating", "source_num_ratings", "external_ref",
        ]


class ProfessorCreateSerializer(serializers.ModelSerializer):
    """Serializer for add-professor submissions."""

    # User submissions need a school for deduplication.
    institution = serializers.CharField(
        max_length=128, allow_blank=False, trim_whitespace=False,
    )
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(),
        required=False, allow_null=True,
    )

    class Meta:
        model = Professor
        fields = ["id", "name", "institution", "department"]
        read_only_fields = ["id"]
        # Dedup is handled manually in validate().
        validators: list = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.existing_instance: Professor | None = None

    def validate_name(self, value: str) -> str:
        cleaned = _WS.sub(" ", (value or "").strip())
        if len(cleaned) < 2:
            raise serializers.ValidationError(
                "Name must be at least 2 characters."
            )
        if len(cleaned) > 128:
            raise serializers.ValidationError(
                "Name must be at most 128 characters."
            )
        # Require at least one letter.
        if not any(c.isalpha() for c in cleaned):
            raise serializers.ValidationError(
                "Name must contain at least one letter."
            )
        # Block only high-confidence placeholder names.
        norm = normalise_name(cleaned)
        if norm in OBVIOUS_FICTIONAL or norm in KNOWN_JOKES:
            raise serializers.ValidationError(
                "That name looks like a known fictional or placeholder "
                "name. Please double-check the spelling."
            )
        return cleaned

    def validate_institution(self, value: str) -> str:
        cleaned = _WS.sub(" ", (value or "").strip())
        if len(cleaned) < 2:
            raise serializers.ValidationError(
                "School name must be at least 2 characters."
            )
        if len(cleaned) > 128:
            raise serializers.ValidationError(
                "School name must be at most 128 characters."
            )
        if normalise_name(cleaned) in FICTIONAL_INSTITUTIONS_NORMALISED:
            raise serializers.ValidationError(
                "That school does not appear to be a real institution."
            )
        return cleaned

    def validate(self, attrs):
        # Store the duplicate row for the view to return.
        name = attrs.get("name", "")
        institution = attrs.get("institution", "")
        if name and institution:
            existing = (
                Professor.objects
                .filter(name__iexact=name, institution__iexact=institution)
                .first()
            )
            if existing is not None:
                self.existing_instance = existing
        return attrs

    def to_representation(self, instance):
        # Match the search-result shape.
        return ProfessorListSerializer(instance, context=self.context).data


class ProfessorDetailSerializer(serializers.ModelSerializer):
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
