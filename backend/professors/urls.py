from django.urls import path
from . import views

urlpatterns = [
    path("professors/", views.ProfessorSearchView.as_view(), name="professor-list"),
    path("professors/<int:pk>/", views.ProfessorDetailView.as_view(), name="professor-detail"),
    path("professors/<int:pk>/reviews/", views.professor_live_reviews, name="professor-live-reviews"),
    path("professors/<int:pk>/similar/", views.similar_professors, name="professor-similar"),
    path("departments/", views.DepartmentListView.as_view(), name="department-list"),
    path("institutions/", views.institutions_autocomplete, name="institutions-autocomplete"),
    path("compare/", views.compare_professors, name="professor-compare"),
    path("summary/", views.platform_summary, name="platform-summary"),
]
