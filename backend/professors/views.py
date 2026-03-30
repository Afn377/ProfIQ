from rest_framework import generics

from .models import Professor
from .serializers import ProfessorListSerializer


class ProfessorListView(generics.ListAPIView):
    # GET /api/professors/ — paginated list of professors.

    serializer_class = ProfessorListSerializer

    def get_queryset(self):
        qs = Professor.objects.all().order_by("name")
        # TODO(you): search (?q=), filters (?department=, ?institution=), sorting (?sort=)
        return qs
