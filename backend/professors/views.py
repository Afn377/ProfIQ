import logging
import threading
import time
from collections import OrderedDict
from threading import Lock, Semaphore

from django.db import close_old_connections
from django.db.models import Q, Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from rest_framework.throttling import ScopedRateThrottle

from .models import Professor, ProfessorStats, Review, Department
from .serializers import (
    ProfessorListSerializer,
    ProfessorCreateSerializer,
    ProfessorDetailSerializer,
    DepartmentSerializer,
)
from scrapers.rmp import RMPClient, teacher_gid_from_legacy, _normalize_rmp_date
from scrapers.reddit_lazy import fetch_for_professor as fetch_reddit_for_professor
from sentiment.analyzer import aggregate_stats, analyze_text
from sentiment.ml import recommender as ml_recommender

logger = logging.getLogger(__name__)


# Shared RMP client for live review requests.
_rmp_client: RMPClient | None = None
_rmp_client_lock = Lock()


def _get_rmp_client() -> RMPClient:
    global _rmp_client
    with _rmp_client_lock:
        if _rmp_client is None:
            _rmp_client = RMPClient(throttle_seconds=0.35)
        return _rmp_client


# Small LRU for paged live-review responses.
_PAGE_CACHE_LIMIT = 256
_page_cache: OrderedDict[tuple, dict] = OrderedDict()
_page_cache_lock = Lock()


def _cache_get(key: tuple) -> dict | None:
    with _page_cache_lock:
        val = _page_cache.get(key)
        if val is not None:
            _page_cache.move_to_end(key)
        return val


def _cache_put(key: tuple, value: dict) -> None:
    with _page_cache_lock:
        _page_cache[key] = value
        _page_cache.move_to_end(key)
        while len(_page_cache) > _PAGE_CACHE_LIMIT:
            _page_cache.popitem(last=False)


# Short-lived Reddit result cache.
_REDDIT_CACHE_TTL_SECONDS = 30 * 60
_REDDIT_CACHE_LIMIT = 512
_reddit_cache: OrderedDict[int, tuple[float, list[dict]]] = OrderedDict()
_reddit_cache_lock = Lock()


def _reddit_cache_get(prof_id: int) -> list[dict] | None:
    with _reddit_cache_lock:
        entry = _reddit_cache.get(prof_id)
        if entry is None:
            return None
        ts, value = entry
        if time.monotonic() - ts > _REDDIT_CACHE_TTL_SECONDS:
            _reddit_cache.pop(prof_id, None)
            return None
        _reddit_cache.move_to_end(prof_id)
        return value


def _reddit_cache_put(prof_id: int, value: list[dict]) -> None:
    with _reddit_cache_lock:
        _reddit_cache[prof_id] = (time.monotonic(), value)
        _reddit_cache.move_to_end(prof_id)
        while len(_reddit_cache) > _REDDIT_CACHE_LIMIT:
            _reddit_cache.popitem(last=False)


def _get_reddit_reviews(prof: Professor, max_comments: int = 25) -> list[dict]:
    """Fetch cached Reddit comments for one professor."""
    cached = _reddit_cache_get(prof.id)
    if cached is not None:
        return cached[:max_comments]
    try:
        results = fetch_reddit_for_professor(
            prof.name,
            prof.institution or None,
            max_comments=max_comments,
        )
    except Exception as exc:
        logger.warning(
            "Reddit lazy fetch failed for prof=%d (%s @ %s): %s",
            prof.id, prof.name, prof.institution, exc,
        )
        results = []
    _reddit_cache_put(prof.id, results)
    return results


def _legacy_id_from_ref(external_ref: str) -> int | None:
    if not external_ref or not external_ref.startswith("rmp:"):
        return None
    try:
        return int(external_ref.split(":")[1])
    except (IndexError, ValueError):
        return None


# Background stats jobs started from detail-page reads.

_LAZY_ANALYZE_MAX_CONCURRENT = 4
_LAZY_ANALYZE_REVIEW_CAP = 100  # cap per prof to bound runtime
_LAZY_ANALYZE_REDDIT_CAP = 25   # additional Reddit comments analyzed per prof

_analyze_in_progress: set[int] = set()
_analyze_in_progress_lock = Lock()
_analyze_semaphore = Semaphore(_LAZY_ANALYZE_MAX_CONCURRENT)


def _enqueue_lazy_analyze(prof: Professor) -> bool:
    """Start a background stats job when needed."""
    if not prof.external_ref or not prof.external_ref.startswith("rmp:"):
        return False
    # Score-only rows can still be replaced with full theme stats.
    existing_stats = ProfessorStats.objects.filter(professor_id=prof.id).first()
    if existing_stats is not None and existing_stats.theme_counts:
        return False
    with _analyze_in_progress_lock:
        if prof.id in _analyze_in_progress:
            return False
        _analyze_in_progress.add(prof.id)

    threading.Thread(
        target=_run_lazy_analyze,
        args=(prof.id,),
        daemon=True,
        name=f"analyze-prof-{prof.id}",
    ).start()
    return True


def _run_lazy_analyze(prof_id: int) -> None:
    """Background worker — fetch RMP reviews, aggregate, persist stats."""
    try:
        with _analyze_semaphore:
            try:
                prof = Professor.objects.get(pk=prof_id)
            except Professor.DoesNotExist:
                return

            legacy_id = _legacy_id_from_ref(prof.external_ref)
            if legacy_id is None:
                return

            gid = teacher_gid_from_legacy(legacy_id)
            client = _get_rmp_client()

            sentiments: list[dict] = []
            rmp_count = 0
            try:
                for rating in client.iter_ratings(
                    gid, page_size=20, max_reviews=_LAZY_ANALYZE_REVIEW_CAP,
                ):
                    comment = (rating.get("comment") or "").strip()
                    if comment:
                        sentiments.append(
                            analyze_text(comment, rating=_quality_rating(rating))
                        )
                        rmp_count += 1
            except Exception as exc:
                logger.warning(
                    "Lazy analyze: RMP fetch failed for prof=%d (rmp:%s): %s",
                    prof_id, legacy_id, exc,
                )

            # Reddit comments do not include star ratings.
            reddit_count = 0
            try:
                reddit_reviews = _get_reddit_reviews(
                    prof, max_comments=_LAZY_ANALYZE_REDDIT_CAP,
                )
                for r in reddit_reviews:
                    text = (r.get("text") or "").strip()
                    if text:
                        sentiments.append(analyze_text(text))
                        reddit_count += 1
            except Exception as exc:
                logger.warning(
                    "Lazy analyze: Reddit fetch failed for prof=%d: %s",
                    prof_id, exc,
                )

            if not sentiments:
                return

            stats_dict = aggregate_stats(sentiments)
            ProfessorStats.objects.update_or_create(
                professor_id=prof_id,
                defaults=stats_dict,
            )
            logger.info(
                "Lazy analyze: prof=%d stored — %d reviews (rmp=%d, reddit=%d), score=%.1f",
                prof_id, len(sentiments), rmp_count, reddit_count,
                stats_dict["recommendation_score"],
            )
    except Exception:
        logger.exception("Lazy analyze: unhandled error for prof=%d", prof_id)
    finally:
        # Close the DB connection opened by this worker thread.
        close_old_connections()
        with _analyze_in_progress_lock:
            _analyze_in_progress.discard(prof_id)


class ProfessorSearchView(generics.ListCreateAPIView):
    """List, search, and create professor records."""

    throttle_scope = "professor_create"

    def get_throttles(self):
        # Throttle writes only.
        if self.request.method == "POST":
            return [ScopedRateThrottle()]
        return []

    def get_serializer_class(self):
        return (
            ProfessorCreateSerializer
            if self.request.method == "POST"
            else ProfessorListSerializer
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Duplicate submissions return the existing professor.
        existing = serializer.existing_instance
        if existing is not None:
            payload = ProfessorListSerializer(existing).data
            payload["created"] = False
            return Response(payload, status=status.HTTP_200_OK)

        instance = serializer.save()
        # Start stats in the background when possible.
        try:
            _enqueue_lazy_analyze(instance)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to enqueue lazy analyze for new professor %s", instance.pk)

        payload = ProfessorListSerializer(instance).data
        payload["created"] = True
        return Response(payload, status=status.HTTP_201_CREATED)

    def get_queryset(self):
        qs = Professor.objects.select_related("department", "stats")

        q = self.request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(institution__icontains=q)
                | Q(department__name__icontains=q)
                | Q(courses__code__icontains=q)
            ).distinct()

        dept = self.request.query_params.get("department")
        if dept:
            qs = qs.filter(department_id=dept)

        institution = self.request.query_params.get("institution", "").strip()
        if institution:
            qs = qs.filter(institution__iexact=institution)

        sort = self.request.query_params.get("sort", "score")
        if sort == "name":
            qs = qs.order_by("name")
        elif sort == "reviews":
            qs = qs.order_by("-stats__review_count", "name")
        else:  # score (default)
            qs = qs.order_by("-stats__recommendation_score", "name")
        return qs


class ProfessorDetailView(generics.RetrieveAPIView):
    serializer_class = ProfessorDetailSerializer

    def get_queryset(self):
        return Professor.objects.select_related("department", "stats").prefetch_related(
            "courses",
            Prefetch(
                "reviews",
                queryset=Review.objects
                    .select_related("source", "course", "sentiment")
                    .order_by("-posted_at", "-id"),
            ),
        )

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        # Start stats after building the response.
        instance = self.get_object()
        stats = getattr(instance, "stats", None)
        needs_review_text_stats = stats is None or not (stats.theme_counts or {})
        if needs_review_text_stats:
            queued = _enqueue_lazy_analyze(instance)
            if queued:
                response["X-ProfIQ-Analyze"] = "queued"
        return response


class DepartmentListView(generics.ListAPIView):
    queryset = Department.objects.all().order_by("name")
    serializer_class = DepartmentSerializer
    pagination_class = None


@api_view(["GET"])
def institutions_autocomplete(request):
    """Return institution autocomplete results."""
    from django.db.models import Count

    q = request.query_params.get("q", "").strip()
    try:
        limit = max(1, min(50, int(request.query_params.get("limit", 15))))
    except ValueError:
        limit = 15

    base = Professor.objects.exclude(institution="")
    if q:
        rows = list(
            base.filter(institution__istartswith=q)
            .values("institution")
            .annotate(count=Count("id"))
            .order_by("-count", "institution")[:limit]
        )
        if not rows and len(q) >= 4:
            rows = list(
                base.filter(institution__icontains=q)
                .values("institution")
                .annotate(count=Count("id"))
                .order_by("-count", "institution")[:limit]
            )
    else:
        # Default dropdown values.
        rows = list(
            base.values("institution")
            .annotate(count=Count("id"))
            .order_by("-count", "institution")[:limit]
        )

    return Response([
        {"name": r["institution"], "professor_count": r["count"]}
        for r in rows
    ])


@api_view(["GET"])
def compare_professors(request):
    """GET /api/compare/?ids=1,2,3 — returns compact stats for multiple professors."""
    raw = request.query_params.get("ids", "")
    try:
        ids = [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        return Response({"detail": "ids must be comma-separated integers"},
                        status=status.HTTP_400_BAD_REQUEST)
    if not ids:
        return Response({"detail": "provide at least one id"},
                        status=status.HTTP_400_BAD_REQUEST)

    profs = Professor.objects.select_related("department", "stats").filter(id__in=ids)
    data = ProfessorListSerializer(profs, many=True).data
    # Include theme counts for the comparison chart.
    theme_by_id = {
        p.id: (p.stats.theme_counts if hasattr(p, "stats") else {}) for p in profs
    }
    for row in data:
        row["theme_counts"] = theme_by_id.get(row["id"], {})
    return Response(data)


@api_view(["GET"])
def professor_live_reviews(request, pk: int):
    """Return one live review page for a professor."""
    prof = get_object_or_404(Professor, pk=pk)
    legacy_id = _legacy_id_from_ref(prof.external_ref)
    if legacy_id is None:
        return Response(
            {"detail": "Professor has no RateMyProfessors reference."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Make sure aggregate stats are being built too.
    _enqueue_lazy_analyze(prof)

    cursor = request.query_params.get("cursor") or None
    try:
        limit = max(1, min(50, int(request.query_params.get("limit", 25))))
    except ValueError:
        limit = 25

    cache_key = (pk, cursor or "", limit)
    cached = _cache_get(cache_key)
    if cached is not None:
        return Response(cached)

    gid = teacher_gid_from_legacy(legacy_id)
    client = _get_rmp_client()

    try:
        nodes, next_cursor, has_more = client.fetch_ratings_page(
            gid, cursor=cursor, count=limit,
        )
    except Exception as exc:
        logger.exception(
            "RMP live fetch failed for prof=%s (legacy=%s): %s: %s",
            pk, legacy_id, type(exc).__name__, exc,
        )
        return Response(
            {
                "detail": "Upstream review source unavailable.",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    results = []

    # Reddit results are shown once at the top of the live feed.
    if cursor is None:
        for r in _get_reddit_reviews(prof, max_comments=15):
            text = (r.get("text") or "").strip()
            if not text:
                continue
            sentiment = analyze_text(text)
            results.append({
                "text": text,
                "source": "reddit",
                "rating": None,
                "course": None,
                "posted_at": r.get("posted_at"),
                "source_url": r.get("source_url"),
            "sentiment": {
                "label": sentiment["label"],
                "compound": sentiment["compound"],
                "themes": sentiment["themes"],
                "ml_label": sentiment.get("ml_label"),
                "ml_confidence": sentiment.get("ml_confidence"),
                "ml_model": sentiment.get("ml_model"),
            },
        })

    for n in nodes:
        comment = (n.get("comment") or "").strip()
        if not comment:
            continue
        rating_val = _quality_rating(n)
        sentiment = analyze_text(comment, rating=rating_val)
        results.append({
            "text": comment,
            "source": "rmp",
            "rating": rating_val,
            "course": (n.get("class") or "").strip() or None,
            "posted_at": _normalize_rmp_date(n.get("date")),
            "source_url": (
                f"https://www.ratemyprofessors.com/professor/{legacy_id}"
                f"#rating-{n.get('legacyId')}" if n.get("legacyId") else None
            ),
            "sentiment": {
                "label": sentiment["label"],
                "compound": sentiment["compound"],
                "themes": sentiment["themes"],
                "ml_label": sentiment.get("ml_label"),
                "ml_confidence": sentiment.get("ml_confidence"),
                "ml_model": sentiment.get("ml_model"),
            },
        })

    payload = {
        "results": results,
        "next_cursor": next_cursor,
        "has_more": has_more,
    }
    _cache_put(cache_key, payload)
    return Response(payload)


def _quality_rating(rating: dict) -> float | None:
    """Average RMP helpfulness and clarity ratings."""
    helpful = rating.get("helpfulRating")
    clarity = rating.get("clarityRating")
    vals = [v for v in (helpful, clarity) if isinstance(v, (int, float))]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)


@api_view(["GET"])
def similar_professors(request, pk: int):
    """Return embedding-based similar professors."""
    prof = get_object_or_404(Professor, pk=pk)
    try:
        k = max(1, min(20, int(request.query_params.get("k", 5))))
    except ValueError:
        k = 5

    scope = (request.query_params.get("scope") or "department").lower()
    if scope not in ("department", "institution", "global"):
        scope = "department"

    if not ml_recommender.is_available():
        return Response({
            "available": False, "results": [],
            "scope": scope, "match_level": scope,
        })

    if not prof.external_ref:
        return Response({
            "available": True, "results": [],
            "scope": scope, "match_level": scope, "warmed": False,
        })

    # Build a temporary embedding for professors outside the saved index.
    warmed = False
    want_warm = request.query_params.get("warm", "1") not in ("0", "false", "no")
    if want_warm and not ml_recommender.is_indexed(prof.external_ref):
        warmed = _warm_up_recommender(prof)

    if not ml_recommender.is_indexed(prof.external_ref):
        return Response({
            "available": True, "results": [],
            "scope": scope, "match_level": scope, "warmed": warmed,
        })

    # Fetch extra neighbors before applying DB-level filters.
    candidate_k = max(50, min(ml_recommender.num_indexed() - 1, 300))
    raw = ml_recommender.similar_by_external_ref(prof.external_ref, k=candidate_k) or []
    if not raw:
        return Response({
            "available": True, "results": [],
            "scope": scope, "match_level": scope, "warmed": warmed,
        })

    # Load candidate rows in one query.
    refs = [n.external_ref for n in raw]
    by_ref = {
        p.external_ref: p
        for p in Professor.objects
            .select_related("department", "stats")
            .filter(external_ref__in=refs)
    }

    same_inst = (prof.institution or "").strip().lower()
    same_dept_id = prof.department_id

    def _filter(want_inst: bool, want_dept: bool):
        out = []
        for n in raw:
            p = by_ref.get(n.external_ref)
            if p is None:
                continue
            if want_inst and (p.institution or "").strip().lower() != same_inst:
                continue
            if want_dept and p.department_id != same_dept_id:
                continue
            out.append((n, p))
            if len(out) >= k:
                break
        return out

    # Try the requested scope, then widen if needed.
    match_level = scope
    if scope == "department":
        filtered = _filter(want_inst=bool(same_inst), want_dept=bool(same_dept_id))
        if not filtered and same_inst:
            match_level = "institution"
            filtered = _filter(want_inst=True, want_dept=False)
        if not filtered:
            match_level = "global"
            filtered = _filter(want_inst=False, want_dept=False)
    elif scope == "institution":
        filtered = _filter(want_inst=bool(same_inst), want_dept=False) if same_inst else []
        if not filtered:
            match_level = "global"
            filtered = _filter(want_inst=False, want_dept=False)
    else:
        filtered = _filter(want_inst=False, want_dept=False)

    out = []
    for n, p in filtered:
        out.append({
            "id": p.id,
            "external_ref": p.external_ref,
            "name": p.name,
            "department": p.department.name if p.department else None,
            "institution": p.institution,
            "score": round(n.score, 4),
            "recommendation_score": (
                p.stats.recommendation_score if hasattr(p, "stats") else None
            ),
            "review_count": (
                p.stats.review_count if hasattr(p, "stats") else 0
            ),
        })

    return Response({
        "available": True,
        "results": out,
        "model": "all-MiniLM-L6-v2",
        "warmed": warmed,
        "scope": scope,
        "match_level": match_level,
        "source": {
            "institution": prof.institution or None,
            "department": prof.department.name if prof.department else None,
        },
    })


# On-demand embedding for professors missing from the saved index.

_WARM_MAX_CONCURRENT = 2
_WARM_REVIEW_CAP = 30
_WARM_DOC_MAX_CHARS = 4000

_warm_in_progress: set[str] = set()
_warm_in_progress_lock = Lock()
_warm_semaphore = Semaphore(_WARM_MAX_CONCURRENT)


def _warm_up_recommender(prof: Professor) -> bool:
    """Add one professor to the live recommender index."""
    if not prof.external_ref:
        return False
    if not ml_recommender.encoder_available():
        return False

    legacy_id = _legacy_id_from_ref(prof.external_ref)
    if legacy_id is None:
        return False

    with _warm_in_progress_lock:
        if prof.external_ref in _warm_in_progress:
            # Wait briefly for the other request to finish.
            for _ in range(20):
                if ml_recommender.is_indexed(prof.external_ref):
                    return True
                time.sleep(0.1)
            return ml_recommender.is_indexed(prof.external_ref)
        _warm_in_progress.add(prof.external_ref)

    acquired = _warm_semaphore.acquire(timeout=5.0)
    if not acquired:
        with _warm_in_progress_lock:
            _warm_in_progress.discard(prof.external_ref)
        return False

    try:
        gid = teacher_gid_from_legacy(legacy_id)
        client = _get_rmp_client()
        chunks: list[str] = []
        used = 0
        try:
            for rating in client.iter_ratings(
                gid, page_size=20, max_reviews=_WARM_REVIEW_CAP,
            ):
                txt = (rating.get("comment") or "").strip()
                if not txt:
                    continue
                if used + len(txt) > _WARM_DOC_MAX_CHARS and chunks:
                    break
                chunks.append(txt)
                used += len(txt)
        except Exception as exc:
            logger.warning(
                "Recommender warm-up: RMP fetch failed for prof=%s (%s): %s",
                prof.id, prof.external_ref, exc,
            )
            return False

        if not chunks:
            logger.info(
                "Recommender warm-up: no usable reviews for prof=%s (%s)",
                prof.id, prof.external_ref,
            )
            return False

        label = f"{prof.name} @ {prof.institution}" if prof.institution else prof.name
        ok = ml_recommender.add_embedding(
            prof.external_ref,
            label,
            "  ".join(chunks),
        )
        if ok:
            logger.info(
                "Recommender warm-up: indexed prof=%s (%s) from %d reviews",
                prof.id, prof.external_ref, len(chunks),
            )
        return ok
    finally:
        _warm_semaphore.release()
        with _warm_in_progress_lock:
            _warm_in_progress.discard(prof.external_ref)


@api_view(["GET"])
def platform_summary(request):
    """GET /api/summary/ — lightweight landing-page stats."""
    from django.db.models import Count, Avg
    total_profs = Professor.objects.count()
    total_reviews = Review.objects.count()
    top = (
        Professor.objects.select_related("department", "stats")
        .filter(stats__review_count__gte=3)
        .order_by("-stats__recommendation_score")[:5]
    )
    depts_with_counts = (
        Department.objects.annotate(count=Count("professors"))
        .order_by("-count")[:8]
    )
    return Response({
        "professor_count": total_profs,
        "review_count": total_reviews,
        "top_professors": ProfessorListSerializer(top, many=True).data,
        "departments": [
            {"id": d.id, "name": d.name, "professor_count": d.count}
            for d in depts_with_counts
        ],
    })
