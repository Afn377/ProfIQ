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


