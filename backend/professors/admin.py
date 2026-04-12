from django.contrib import admin
from .models import (
    Source, Department, Professor, Course, Review, SentimentResult, ProfessorStats,
)

admin.site.register(Source)
admin.site.register(Department)
admin.site.register(Course)
admin.site.register(Review)
admin.site.register(SentimentResult)


@admin.register(Professor)
class ProfessorAdmin(admin.ModelAdmin):
    list_display = ("name", "department", "institution")
    search_fields = ("name", "institution")


@admin.register(ProfessorStats)
class ProfessorStatsAdmin(admin.ModelAdmin):
    list_display = ("professor", "review_count", "avg_compound", "recommendation_score")
