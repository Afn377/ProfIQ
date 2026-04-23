"""Database models for ProfIQ."""
from django.db import models


class Source(models.Model):
    """Review source such as RMP or Reddit."""

    name = models.CharField(max_length=64, unique=True)
    base_url = models.URLField(blank=True)

    def __str__(self) -> str:
        return self.name


class Department(models.Model):
    name = models.CharField(max_length=128, unique=True)
    code = models.CharField(max_length=16, blank=True)

    def __str__(self) -> str:
        return self.name


class Professor(models.Model):
    name = models.CharField(max_length=128, db_index=True)
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="professors",
    )
    institution = models.CharField(max_length=128, blank=True, db_index=True)
    bio = models.TextField(blank=True)
    # Format: "<source>:<id>", for example "rmp:12345".
    external_ref = models.CharField(
        max_length=64, blank=True, db_index=True,
    )
    # Source profile stats from the directory crawl.
    source_avg_rating = models.FloatField(null=True, blank=True)
    source_num_ratings = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "institution"],
                name="uniq_professor_name_institution",
            ),
            models.UniqueConstraint(
                fields=["external_ref"],
                name="uniq_professor_external_ref",
                condition=~models.Q(external_ref=""),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.department.name if self.department else 'N/A'})"


class Course(models.Model):
    code = models.CharField(max_length=32, db_index=True)
    title = models.CharField(max_length=200, blank=True)
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="courses",
    )
    professors = models.ManyToManyField(Professor, related_name="courses", blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["code"], name="uniq_course_code"),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.title}"


class Review(models.Model):
    """One review or comment for a professor."""

    professor = models.ForeignKey(Professor, on_delete=models.CASCADE, related_name="reviews")
    course = models.ForeignKey(
        Course, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviews"
    )
    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="reviews")

    text = models.TextField()
    # Nullable because Reddit comments do not have stars.
    rating = models.FloatField(null=True, blank=True)
    source_url = models.URLField(blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    ingested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["professor", "source"]),
            models.Index(fields=["posted_at"]),
        ]
        constraints = [
            # Prevent duplicate source URLs.
            models.UniqueConstraint(
                fields=["source", "source_url"],
                name="uniq_source_url",
                condition=~models.Q(source_url=""),
            )
        ]

    def __str__(self) -> str:
        return f"Review #{self.pk} of {self.professor.name} from {self.source.name}"


class SentimentResult(models.Model):
    """Sentiment output for one review."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    LABEL_CHOICES = [
        (POSITIVE, "Positive"),
        (NEUTRAL, "Neutral"),
        (NEGATIVE, "Negative"),
    ]

    review = models.OneToOneField(
        Review, on_delete=models.CASCADE, related_name="sentiment"
    )
    compound = models.FloatField()
    positive = models.FloatField(default=0.0)
    neutral = models.FloatField(default=0.0)
    negative = models.FloatField(default=0.0)
    label = models.CharField(max_length=10, choices=LABEL_CHOICES)
    # Detected theme names.
    themes = models.JSONField(default=list, blank=True)
    analyzed_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Sentiment({self.label}, {self.compound:.2f}) for Review #{self.review_id}"


class ProfessorStats(models.Model):
    """Aggregated dashboard stats for one professor."""

    professor = models.OneToOneField(
        Professor, on_delete=models.CASCADE, related_name="stats"
    )
    review_count = models.IntegerField(default=0)
    avg_compound = models.FloatField(default=0.0)
    positive_count = models.IntegerField(default=0)
    neutral_count = models.IntegerField(default=0)
    negative_count = models.IntegerField(default=0)
    # Theme frequency map.
    theme_counts = models.JSONField(default=dict, blank=True)
    recommendation_score = models.FloatField(default=0.0)  # 0–100
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Stats for {self.professor.name}: {self.recommendation_score:.1f}"
