from django.urls import path

from . import views

urlpatterns = [
    path("professors/", views.ProfessorListView.as_view(), name="professor-list"),
]
