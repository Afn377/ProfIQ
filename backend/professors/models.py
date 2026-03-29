from django.db import models

# Create your models here.

class Department(models.Model):
    name = models.CharField(max_length=128, unique=True)
    code = models.CharField(max_length=16, blank=True)

    def __str__(self):
        return self.name


class Professor(models.Model):
    name = models.CharField(max_length=128)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="professors")
    institution = models.CharField(max_length=128)
    bio = models.TextField(blank=True, default="")
    # Format: "<source>:<id>", for example "rmp:12345".
    external_ref = models.CharField(max_length=64, blank=True, default="")
    # Profile stats copied from the source site during the directory crawl.
    source_avg_rating = models.FloatField(null=True, blank=True)
    source_num_ratings = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["name", "institution"], name="unique_professor_name_institution"),
            models.UniqueConstraint(fields=["external_ref"], name="unique_professor_external_ref"),
        ]

    def __str__(self):
        return self.name


class Source(models.Model):
    """Where a review came from, e.g. RateMyProfessors."""

    name = models.CharField(max_length=64, unique=True)
    base_url = models.URLField(blank=True)

    def __str__(self):
        return self.name


class Course(models.Model):
    code = models.CharField(max_length=32)
    title = models.CharField(max_length=200, blank=True)
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="courses"
    )
    professors = models.ManyToManyField(Professor, blank=True, related_name="courses")

    def __str__(self):
        return f"{self.code} — {self.title}"


class Review(models.Model):
    """One student review of one professor."""

    professor = models.ForeignKey(Professor, on_delete=models.CASCADE, related_name="reviews")
    course = models.ForeignKey(
        Course, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviews"
    )
    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="reviews")

    text = models.TextField()
    rating = models.FloatField(null=True, blank=True)
    source_url = models.URLField(blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    ingested_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review #{self.pk} of {self.professor.name}"


class SentimentResult(models.Model):
    """Sentiment analysis output for one review."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    LABEL_CHOICES = [
        (POSITIVE, "Positive"),
        (NEUTRAL, "Neutral"),
        (NEGATIVE, "Negative"),
    ]

    review = models.OneToOneField(Review, on_delete=models.CASCADE, related_name="sentiment")
    compound = models.FloatField()
    positive = models.FloatField(default=0.0)
    neutral = models.FloatField(default=0.0)
    negative = models.FloatField(default=0.0)
    label = models.CharField(max_length=10, choices=LABEL_CHOICES)
    themes = models.JSONField(default=list, blank=True)
    analyzed_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Sentiment({self.label}, {self.compound:.2f}) for Review #{self.review_id}"


class ProfessorStats(models.Model):
    """Aggregated dashboard numbers for one professor."""

    professor = models.OneToOneField(Professor, on_delete=models.CASCADE, related_name="stats")
    review_count = models.IntegerField(default=0)
    avg_compound = models.FloatField(default=0.0)
    positive_count = models.IntegerField(default=0)
    neutral_count = models.IntegerField(default=0)
    negative_count = models.IntegerField(default=0)
    theme_counts = models.JSONField(default=dict, blank=True)
    recommendation_score = models.FloatField(default=0.0)  # 0-100
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Stats for {self.professor.name}: {self.recommendation_score:.1f}"