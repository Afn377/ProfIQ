import re

from rest_framework import serializers

from .models import Department, Professor

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
