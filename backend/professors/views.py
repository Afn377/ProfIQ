from rest_framework import generics
from django.db.models import Q
from .models import Professor
from .serializers import ProfessorListSerializer


class ProfessorListView(generics.ListAPIView):
    # GET /api/professors/ — paginated list of professors.
    # Optional query params: q, department, institution, sort

    serializer_class = ProfessorListSerializer

    def get_queryset(self):
        qs = Professor.objects.all()

        # ?q= free-text search across name, institution, and department name
        q = self.request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(institution__icontains=q) | Q(department__name__icontains=q))

        # ?department=<id> exact department
        department = self.request.query_params.get("department", "").strip()
        if department:
            qs = qs.filter(department_id=department)

        # ?institution= exact school name, case-insensitive
        institution = self.request.query_params.get("institution", "").strip()
        if institution:
            qs = qs.filter(institution__iexact=institution)

        # ?sort=name for alphabetical; default is best recommendation score first
        sort = self.request.query_params.get("sort", "score")
        if sort == "name":
            qs = qs.order_by("name")
        else:
            qs = qs.order_by("-stats__recommendation_score", "name")

        return qs
