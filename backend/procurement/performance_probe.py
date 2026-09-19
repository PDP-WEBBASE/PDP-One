from __future__ import annotations

from types import SimpleNamespace
from time import perf_counter

from django.core.cache import cache
from django.db import connection
from django.http import QueryDict

from .analysis_run_service import active_run
from .performance_metrics import DatabaseQueryStats
from .serializers_direct import DirectOpportunityListSerializer
from .views_bulk_workflow import VIEW_DISMISS_WORKFLOWS, _user_dismissed_notice_ids
from .views_compact_ui import CompactNoticeSerializer, _compact_notice_queryset
from .views_dashboard_read_model import DASHBOARD_CACHE_KEY, _dashboard_payload
from .views_direct import DirectOpportunityViewSet

PROBE_CACHE_KEY = "pdp:performance-assurance:v1:operator-probe"
PROBE_CACHE_TTL_SECONDS = 60 * 60
NOTICE_TYPES = ("tender", "inquiry")
NOTICE_WORKFLOWS = ("recent", "recommended", "selected", "submitted", "results")
DIRECT_WORKFLOWS = ("all", "recommended", "selected", "submitted", "results", "active")
PROBE_PAGE_SIZE = 50


def _request(user, **params):
    query = QueryDict("", mutable=True)
    for key, value in params.items():
        query[key] = str(value)
    return SimpleNamespace(query_params=query, user=user)


def _classification(duration_ms: float, db_ms: float, query_count: int) -> dict:
    db_share = (db_ms / duration_ms * 100.0) if duration_ms > 0 else 0.0
    if db_share >= 70.0:
        dominant = "database"
    elif db_share <= 30.0:
        dominant = "python_or_serialization"
    else:
        dominant = "mixed"

    if duration_ms >= 3000.0:
        status = "critical"
    elif duration_ms >= 1500.0:
        status = "warning"
    elif duration_ms > 1000.0:
        status = "watch"
    else:
        status = "normal"

    return {
        "status": status,
        "dominant_layer": dominant,
        "db_share_pct": round(db_share, 1),
        "query_count_high": query_count > 20,
    }


def _measure_notice(user, notice_type: str, workflow: str) -> dict:
    request = _request(
        user,
        notice_type=notice_type,
        workflow=workflow,
        page=1,
        page_size=PROBE_PAGE_SIZE,
    )
    stats = DatabaseQueryStats()
    started = perf_counter()
    with connection.execute_wrapper(stats):
        queryset = _compact_notice_queryset(request)
        if workflow in VIEW_DISMISS_WORKFLOWS:
            dismissed_ids = _user_dismissed_notice_ids(request, workflow)
            if dismissed_ids:
                queryset = queryset.exclude(pk__in=dismissed_ids)
        rows = list(queryset[: PROBE_PAGE_SIZE + 1])
        visible_rows = rows[:PROBE_PAGE_SIZE]
        serializer = CompactNoticeSerializer(
            visible_rows,
            many=True,
            context={"request": request},
        )
        # Force serialization inside the measured region.
        list(serializer.data)
    duration_ms = (perf_counter() - started) * 1000.0
    result = {
        "path": f"notices.{notice_type}.{workflow}",
        "duration_ms": round(duration_ms, 1),
        "db_ms": round(stats.duration_ms, 1),
        "query_count": stats.count,
        "rows": len(visible_rows),
        "has_more": len(rows) > PROBE_PAGE_SIZE,
    }
    result.update(_classification(duration_ms, stats.duration_ms, stats.count))
    return result


def _measure_direct(user, workflow: str) -> dict:
    request = _request(user, workflow_view="" if workflow == "all" else workflow)
    stats = DatabaseQueryStats()
    started = perf_counter()
    with connection.execute_wrapper(stats):
        view = DirectOpportunityViewSet()
        view.action = "list"
        view.request = request
        queryset = view.get_queryset()
        rows = list(queryset[: PROBE_PAGE_SIZE + 1])
        visible_rows = rows[:PROBE_PAGE_SIZE]
        serializer = DirectOpportunityListSerializer(
            visible_rows,
            many=True,
            context={"request": request},
        )
        list(serializer.data)
    duration_ms = (perf_counter() - started) * 1000.0
    result = {
        "path": f"direct.{workflow}",
        "duration_ms": round(duration_ms, 1),
        "db_ms": round(stats.duration_ms, 1),
        "query_count": stats.count,
        "rows": len(visible_rows),
        "has_more": len(rows) > PROBE_PAGE_SIZE,
    }
    result.update(_classification(duration_ms, stats.duration_ms, stats.count))
    return result


def _measure_dashboard() -> list[dict]:
    stats = DatabaseQueryStats()
    started = perf_counter()
    with connection.execute_wrapper(stats):
        payload = _dashboard_payload()
    cold_ms = (perf_counter() - started) * 1000.0
    cold = {
        "path": "dashboard.cold",
        "duration_ms": round(cold_ms, 1),
        "db_ms": round(stats.duration_ms, 1),
        "query_count": stats.count,
        "rows": len(payload.get("active_cases") or []),
        "has_more": False,
    }
    cold.update(_classification(cold_ms, stats.duration_ms, stats.count))

    cache.set(DASHBOARD_CACHE_KEY, payload, 20)
    warm_started = perf_counter()
    cached = cache.get(DASHBOARD_CACHE_KEY)
    warm_ms = (perf_counter() - warm_started) * 1000.0
    warm = {
        "path": "dashboard.warm",
        "duration_ms": round(warm_ms, 1),
        "db_ms": 0.0,
        "query_count": 0,
        "rows": len((cached or {}).get("active_cases") or []),
        "has_more": False,
        "status": "normal" if warm_ms < 500.0 else "warning",
        "dominant_layer": "cache",
        "db_share_pct": 0.0,
        "query_count_high": False,
    }
    return [cold, warm]


def _background_state() -> dict:
    run = active_run()
    if run is None:
        return {"analysis_active": False}
    counters = run.counters or {}
    return {
        "analysis_active": True,
        "analysis_run_id": str(run.id),
        "analysis_status": run.status,
        "analysis_remaining": int(counters.get("remaining", 0) or 0),
        "analysis_completed": int(counters.get("completed", 0) or 0),
        "analysis_claimed": int(counters.get("claimed", 0) or 0),
    }


def collect_operator_performance_probe(user, *, force: bool = False) -> dict:
    """Collect one bounded read-only runtime baseline across operational subviews.

    The probe executes one first-page read per whitelisted view, never performs
    exact COUNT(*) pagination work, never runs EXPLAIN, never logs SQL text or
    business payloads, and is cached for one hour to prevent diagnostic load.
    """

    if not force:
        cached = cache.get(PROBE_CACHE_KEY)
        if isinstance(cached, dict):
            return {**cached, "cache_hit": True}

    measurements = []
    for notice_type in NOTICE_TYPES:
        for workflow in NOTICE_WORKFLOWS:
            measurements.append(_measure_notice(user, notice_type, workflow))
    for workflow in DIRECT_WORKFLOWS:
        measurements.append(_measure_direct(user, workflow))
    measurements.extend(_measure_dashboard())

    ordered = sorted(measurements, key=lambda item: item["duration_ms"], reverse=True)
    db_dominant = [
        item["path"] for item in ordered
        if item["dominant_layer"] == "database" and item["duration_ms"] >= 250.0
    ]
    high_query = [item["path"] for item in ordered if item["query_count_high"]]
    critical = [item["path"] for item in ordered if item["status"] == "critical"]
    warning = [item["path"] for item in ordered if item["status"] in {"warning", "watch"}]

    result = {
        "schema": "pdp-one.performance-operator-probe.v1",
        "cache_hit": False,
        "page_size": PROBE_PAGE_SIZE,
        "stress_test": False,
        "exact_count_used": False,
        "sql_text_recorded": False,
        "business_payload_recorded": False,
        "background_workload": _background_state(),
        "summary": {
            "measured_paths": len(measurements),
            "critical_paths": critical,
            "warning_or_watch_paths": warning,
            "database_dominant_paths": db_dominant,
            "high_query_count_paths": high_query,
            "slowest_paths": [
                {
                    "path": item["path"],
                    "duration_ms": item["duration_ms"],
                    "db_ms": item["db_ms"],
                    "query_count": item["query_count"],
                    "dominant_layer": item["dominant_layer"],
                }
                for item in ordered[:5]
            ],
        },
        "measurements": measurements,
    }
    cache.set(PROBE_CACHE_KEY, result, PROBE_CACHE_TTL_SECONDS)
    return result
