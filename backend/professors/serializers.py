from rest_framework import serializers

from .models import Professor


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
