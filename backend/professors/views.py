from collections import OrderedDict
from threading import Lock

from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from django.db.models import Count, Prefetch, Q
from .models import Department, Professor, ProfessorStats, Review
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

        # Keep the seed batch out of the plain Browse gallery; an explicit
        # search can still find those professors by name.
        if not self.request.query_params.get("q", "").strip():
            qs = qs.exclude(stats__analysis_source=ProfessorStats.SEED)

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
    analyzed = Professor.objects.filter(
        stats__review_count__gte=3, stats__analysis_source=ProfessorStats.LIVE_RMP,
    )
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


# ---------------------------------------------------------------------------
# Live reviews: fetched from RMP on demand, never stored.

from scrapers.rmp import RMPClient, teacher_gid_from_legacy
from sentiment.analyzer import analyze_text

_rmp_client = RMPClient(throttle_seconds=0.35)

# Small LRU for review pages: the same (professor, cursor, limit) is asked for
# again every time someone refreshes, and RMP rate-limits us.
_PAGE_CACHE_LIMIT = 256
_page_cache: OrderedDict = OrderedDict()
_page_cache_lock = Lock()


def _cache_get(key):
    with _page_cache_lock:
        val = _page_cache.get(key)
        if val is not None:
            _page_cache.move_to_end(key)      # mark as recently used
        return val


def _cache_put(key, value):
    with _page_cache_lock:
        _page_cache[key] = value
        _page_cache.move_to_end(key)
        while len(_page_cache) > _PAGE_CACHE_LIMIT:
            _page_cache.popitem(last=False)   # evict the least recently used


def _quality_rating(rating: dict) -> float | None:
    vals = [v for v in (rating.get("helpfulRating"), rating.get("clarityRating")) if isinstance(v, (int, float))]
    return round(sum(vals) / len(vals), 2) if vals else None


@api_view(["GET"])
def professor_live_reviews(request, pk: int):
    # GET /api/professors/<id>/reviews/?cursor=&limit= — one page of reviews from RMP.
    prof = get_object_or_404(Professor, pk=pk)
    if not prof.external_ref.startswith("rmp:"):
        return Response({"detail": "Professor has no RateMyProfessors reference."}, status=404)
    legacy_id = int(prof.external_ref.split(":")[1])

    cursor = request.query_params.get("cursor") or None
    try:
        limit = max(1, min(50, int(request.query_params.get("limit", 20))))
    except ValueError:
        limit = 20

    cache_key = (pk, cursor or "", limit)
    cached = _cache_get(cache_key)
    if cached is not None:
        return Response(cached)

    try:
        nodes, next_cursor, has_more = _rmp_client.fetch_ratings_page(
            teacher_gid_from_legacy(legacy_id), cursor=cursor, count=limit,
        )
    except Exception as exc:
        # The failure is upstream, not ours: 502, not 500.
        return Response(
            {"detail": "Upstream review source unavailable.", "error": type(exc).__name__},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    results = []
    for n in nodes:
        comment = (n.get("comment") or "").strip()
        if not comment:
            continue
        rating = _quality_rating(n)
        s = analyze_text(comment, rating=rating)
        results.append({
            "text": comment, "rating": rating, "course": (n.get("class") or "").strip() or None,
            "posted_at": n.get("date"),
            "sentiment": {"label": s["label"], "compound": s["compound"], "themes": s["themes"]},
        })
    payload = {"results": results, "next_cursor": next_cursor, "has_more": has_more}
    _cache_put(cache_key, payload)
    return Response(payload)
