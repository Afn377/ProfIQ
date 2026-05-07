import hashlib
import logging
import threading
from collections import OrderedDict
from threading import Lock

from django.db import close_old_connections
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from django.db.models import Count, Prefetch, Q
from django.db.models.functions import Lower
from django.core.cache import cache
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
            qs = qs.alias(inst_lower=Lower("institution")).filter(inst_lower=institution.lower())

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

    def retrieve(self, request, *args, **kwargs):
        prof = self.get_object()
        response = super().retrieve(request, *args, **kwargs)
        # Imported seed stats carry counts but no themes, so treat them like
        # missing stats and let the live pass replace them on first visit.
        stats = getattr(prof, "stats", None)
        needs_live = stats is None or stats.analysis_source == ProfessorStats.SEED
        if needs_live and prof.external_ref.startswith("rmp:"):
            if _enqueue_analyze(prof.id):
                response["X-ProfIQ-Analyze"] = "queued"
        return response

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


def _prefix_upper_bound(prefix: str) -> str:
    """Exclusive upper bound for a prefix range: 'rut' -> 'ruu'.

    lower(col) >= 'rut' AND lower(col) < 'ruu' matches exactly the strings
    starting with 'rut', and unlike LIKE 'rut%' it can use the expression
    index.
    """
    return prefix[:-1] + chr(ord(prefix[-1]) + 1)


@api_view(["GET"])
def institutions_autocomplete(request):
    # GET /api/institutions/?q=rut&limit=15 — school names with professor counts.
    q = request.query_params.get("q", "").strip().lower()
    try:
        limit = max(1, min(50, int(request.query_params.get("limit", 15))))
    except ValueError:
        limit = 15
    base = Professor.objects.exclude(institution="")
    if q:
        base = base.alias(inst_lower=Lower("institution")).filter(
            inst_lower__gte=q, inst_lower__lt=_prefix_upper_bound(q),
        )
    rows = base.values("institution").annotate(count=Count("id")).order_by("-count", "institution")[:limit]
    return Response([{"name": r["institution"], "professor_count": r["count"]} for r in rows])


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


SUMMARY_CACHE_SECONDS = 600


@api_view(["GET"])
def platform_summary(request):
    # GET /api/summary/?institution=<name> — landing-page numbers, optionally scoped to one school.
    institution = request.query_params.get("institution", "").strip()
    # The summary is the first call on every page load, costs seconds on
    # CockroachDB and barely changes, so keep each answer for a few minutes.
    # The cache is per process: a fresh instance fills it on its first call.
    cache_key = "summary:" + hashlib.sha1(institution.lower().encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)
    profs = Professor.objects.all()
    if institution:
        profs = profs.alias(inst_lower=Lower("institution")).filter(inst_lower=institution.lower())
    analyzed = profs.filter(
        stats__review_count__gte=3, stats__analysis_source=ProfessorStats.LIVE_RMP,
    )
    top = (
        analyzed.select_related("department", "stats")
        .order_by("-stats__recommendation_score")[:5]
    )
    from django.db.models import Sum
    payload = {
        "professor_count": profs.count(),
        "review_count": analyzed.aggregate(total=Sum("stats__review_count"))["total"] or 0,
        "analyzed_count": analyzed.count(),
        "top_professors": list(ProfessorListSerializer(top, many=True).data),
        # The home page only shows how many departments there are. This used
        # to be a top 8 list, so the tile always said 8.
        "department_count": profs.exclude(department=None).values("department").distinct().count(),
    }
    cache.set(cache_key, payload, SUMMARY_CACHE_SECONDS)
    return Response(payload)


# ---------------------------------------------------------------------------
# Live reviews: fetched from RMP on demand, never stored.

from scrapers.rmp import RMPClient, teacher_gid_from_legacy
from sentiment.analyzer import analyze_text

_rmp_client = RMPClient(throttle_seconds=0.35)
logger = logging.getLogger(__name__)

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
            "sentiment": {
                "label": s["label"], "compound": s["compound"], "themes": s["themes"],
                "ml_label": s["ml_label"], "ml_confidence": s["ml_confidence"],
            },
        })
    payload = {"results": results, "next_cursor": next_cursor, "has_more": has_more}
    _cache_put(cache_key, payload)
    return Response(payload)


# ---------------------------------------------------------------------------
# Lazy analysis: build a professor's stats the first time someone looks.

from sentiment.analyzer import aggregate_stats

_LAZY_REVIEW_CAP = 100

# v2: remember which professors are being analyzed right now, so a burst of
# refreshes starts one thread, not one per request. The set is shared by all
# request threads, so the check-and-add has to happen under a lock or two
# requests can both see "not in progress" and both start.
_in_progress: set[int] = set()
_in_progress_lock = threading.Lock()

# v3: at most this many analyses run at once. The rest wait their turn
# instead of all hitting RMP and the database in the same second.
_MAX_CONCURRENT = 4
_analyze_slots = threading.Semaphore(_MAX_CONCURRENT)


def _enqueue_analyze(prof_id: int) -> bool:
    with _in_progress_lock:
        if prof_id in _in_progress:
            return False
        _in_progress.add(prof_id)
    threading.Thread(target=_analyze_professor, args=(prof_id,), daemon=True).start()
    return True


def _analyze_professor(prof_id: int) -> None:
    with _analyze_slots:
        print(f"[analyze] thread {threading.get_ident()} starting prof {prof_id}", flush=True)
        _analyze_professor_inner(prof_id)


def _analyze_professor_inner(prof_id: int) -> None:
    try:
        prof = Professor.objects.get(pk=prof_id)
        legacy_id = int(prof.external_ref.split(":")[1])
        sentiments = []
        for r in _rmp_client.iter_ratings(teacher_gid_from_legacy(legacy_id), max_reviews=_LAZY_REVIEW_CAP):
            comment = (r.get("comment") or "").strip()
            if comment:
                sentiments.append(analyze_text(comment, rating=_quality_rating(r)))
        if sentiments:
            ProfessorStats.objects.update_or_create(
                professor_id=prof_id,
                defaults={**aggregate_stats(sentiments), "analysis_source": ProfessorStats.LIVE_RMP},
            )
    finally:
        # Each thread gets its own DB connection; nothing else will close it.
        close_old_connections()
        # Always release the slot, even if the fetch blew up, or this
        # professor could never be analyzed again until restart.
        with _in_progress_lock:
            _in_progress.discard(prof_id)


# ---------------------------------------------------------------------------
# Similar professors

from sentiment.ml import recommender as ml_recommender


@api_view(["GET"])
def similar_professors(request, pk: int):
    # GET /api/professors/<id>/similar/?k=5 — neighbours by review language, same school only.
    prof = get_object_or_404(Professor, pk=pk)
    try:
        k = max(1, min(20, int(request.query_params.get("k", 5))))
    except ValueError:
        k = 5
    if not ml_recommender.is_available() or not prof.external_ref:
        return Response({"available": False, "results": []})
    source = {"department": prof.department.name if prof.department else None, "institution": prof.institution}

    # Not in the offline index? Embed them now from their live reviews.
    warmed = False
    if not ml_recommender.is_indexed(prof.external_ref):
        legacy_id = int(prof.external_ref.split(":")[1])
        texts = []
        try:
            for r in _rmp_client.iter_ratings(teacher_gid_from_legacy(legacy_id), max_reviews=30):
                t = (r.get("comment") or "").strip()
                if t:
                    texts.append(t)
        except Exception as exc:
            logger.warning("similar: fetch failed for %s: %s", prof.external_ref, exc)
        warmed = ml_recommender.add_professor(prof.external_ref, f"{prof.name} @ {prof.institution}", texts)

    # Only professors at the same school are candidates, since a student can
    # only take classes there. Filtered before scoring so a same school match
    # is never lost for ranking low against the whole index. No fallback to
    # other schools: an empty panel is more honest.
    peers = (
        Professor.objects.alias(inst_lower=Lower("institution"))
        .filter(inst_lower=(prof.institution or "").strip().lower())
        .exclude(pk=prof.pk).exclude(external_ref="")
        .select_related("department", "stats")
    )
    by_ref = {p.external_ref: p for p in peers}
    out = []
    for n in ml_recommender.similar(prof.external_ref, k=k, among=set(by_ref)):
        p = by_ref[n.external_ref]
        out.append({"id": p.id, "name": p.name, "department": p.department.name if p.department else None,
                    "institution": p.institution, "score": round(n.score, 3),
                    "review_count": p.stats.review_count if hasattr(p, "stats") else 0,
                    "recommendation_score": p.stats.recommendation_score if hasattr(p, "stats") else None})
    return Response({"available": True, "warmed": warmed, "match_level": "institution", "source": source, "results": out})
