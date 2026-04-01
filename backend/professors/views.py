from rest_framework import generics
from django.db.models import Q
from .models import Professor
from .serializers import ProfessorListSerializer
from rest_framework.exceptions import ValidationError


class ProfessorListView(generics.ListAPIView):
    # GET /api/professors/ — paginated list of professors.
    # Optional query params: q, department, institution, sort

    serializer_class = ProfessorListSerializer

    def get_queryset(self):
        # select_related JOINs department and stats into the same query, so the
        # serializer doesn't fire one extra lookup per professor (N+1).
        qs = Professor.objects.select_related("department", "stats")

        # ?q= free-text search across name, institution, department name, and course code
        q = self.request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(institution__icontains=q)
                | Q(department__name__icontains=q)
                | Q(courses__code__icontains=q)
            ).distinct()  # the join to courses yields one row per matching course

        # ?department=<id> exact department
        department = self.request.query_params.get("department", "").strip()
        if department:
            if not department.isdigit():
                raise ValidationError({"department": "Must be a number."})
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
