from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from django.db.models import Count, Prefetch, Q
from .models import Department, Professor, Review
from .serializers import (
    DepartmentSerializer,
    ProfessorCreateSerializer,
    ProfessorDetailSerializer,
    ProfessorListSerializer,
)
from rest_framework.exceptions import ValidationError


class ProfessorListView(generics.ListCreateAPIView):
    # GET  /api/professors/ — paginated list (query params: q, department, institution, sort)
    # POST /api/professors/ — create one professor

    # Rate-limit creates to 20/hour per client (see REST_FRAMEWORK in settings).
    throttle_scope = "professor_create"

    def get_throttles(self):
        # Only writes are throttled; browsing the catalog is never limited.
        if self.request.method == "POST":
            return [ScopedRateThrottle()]
        return []

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProfessorCreateSerializer
        return ProfessorListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Duplicate: hand back the existing professor rather than a 400.
        existing = serializer.existing_instance
        if existing is not None:
            payload = ProfessorListSerializer(existing).data
            payload["created"] = False
            return Response(payload, status=status.HTTP_200_OK)

        instance = serializer.save()
        payload = ProfessorListSerializer(instance).data
        payload["created"] = True
        return Response(payload, status=status.HTTP_201_CREATED)

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


class ProfessorDetailView(generics.RetrieveAPIView):
    # GET /api/professors/<id>/ — one professor with courses, stats, reviews.

    serializer_class = ProfessorDetailSerializer

    def get_queryset(self):
        return Professor.objects.select_related("department", "stats").prefetch_related(
            "courses",
            Prefetch(
                "reviews",
                queryset=Review.objects.select_related("source", "course")
                .order_by("-posted_at", "-id"),
            ),
        )


class DepartmentListView(generics.ListAPIView):
    # GET /api/departments/ — every department, unpaginated (it feeds a dropdown).

    queryset = Department.objects.all().order_by("name")
    serializer_class = DepartmentSerializer
    pagination_class = None


@api_view(["GET"])
def compare_professors(request):
    # GET /api/compare/?ids=1,2,3 — compact rows for several professors at once.
    raw = request.query_params.get("ids", "")
    try:
        ids = [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise ValidationError({"ids": "Must be comma-separated integers."})
    if not ids:
        raise ValidationError({"ids": "Provide at least one id."})

    profs = Professor.objects.select_related("department", "stats").filter(id__in=ids)
    data = ProfessorListSerializer(profs, many=True).data
    theme_by_id = {p.id: (p.stats.theme_counts if hasattr(p, "stats") else {}) for p in profs}
    for row in data:
        row["theme_counts"] = theme_by_id.get(row["id"], {})
    return Response(data)


@api_view(["GET"])
def platform_summary(request):
    # GET /api/summary/ — landing-page numbers.
    analyzed = Professor.objects.filter(stats__review_count__gte=3)
    top = (
        analyzed.select_related("department", "stats")
        .order_by("-stats__recommendation_score")[:5]
    )
    departments = (
        Department.objects.annotate(count=Count("professors"))
        .order_by("-count")[:8]
    )
    return Response({
        "professor_count": Professor.objects.count(),
        "analyzed_count": analyzed.count(),
        "top_professors": ProfessorListSerializer(top, many=True).data,
        "departments": [
            {"id": d.id, "name": d.name, "professor_count": d.count} for d in departments
        ],
    })
