from django.urls import path

from . import views

urlpatterns = [
    path("professors/", views.ProfessorListView.as_view(), name="professor-list"),
    path("professors/<int:pk>/", views.ProfessorDetailView.as_view(), name="professor-detail"),
    path("departments/", views.DepartmentListView.as_view(), name="department-list"),
    path("compare/", views.compare_professors, name="professor-compare"),
    path("summary/", views.platform_summary, name="platform-summary"),
]
