import logging
from collections import deque
from statistics import median
from time import perf_counter
from typing import Any

from django.core.cache import cache
from django.db import connection
from django.utils import timezone

logger = logging.getLogger("procurement.performance")

WARNING_MS = 500.0
HIGH_MS = 1500.0
CRITICAL_MS = 3000.0
SAMPLE_LIMIT = 120
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
CACHE_INDEX_KEY = "pdp:performance-assurance:v1:metric-index"

# Risk-based budgets: targets guide engineering; only the severe threshold is
# intended to act as a hard promotion signal for critical interactive paths.
PERFORMANCE_BUDGETS: dict[str, dict[str, Any]] = {
    "procurement.ui.revision": {
        "risk": "hot_path",
        "target_ms": 250.0,
        "warning_ms": 750.0,
        "severe_ms": 1500.0,
    },
    "procurement.ui.dashboard.v2": {
        "risk": "hot_path",
        "target_ms": 500.0,
        "warning_ms": 1500.0,
        "severe_ms": 3000.0,
    },
    "procurement.ui.notices.v2": {
        "risk": "hot_path",
        "target_ms": 1000.0,
        "warning_ms": 1500.0,
        "severe_ms": 3000.0,
    },
    "procurement.ui.notices.pagination-metadata.v1": {
        "risk": "standard",
        "target_ms": 1500.0,
        "warning_ms": 2500.0,
        "severe_ms": 5000.0,
    },
    "procurement.ui.direct.list": {
        "risk": "hot_path",
        "target_ms": 1000.0,
        "warning_ms": 1500.0,
        "severe_ms": 3000.0,
    },
}

DEFAULT_BUDGET = {
    "risk": "standard",
    "target_ms": 1000.0,
    "warning_ms": 2000.0,
    "severe_ms": 5000.0,
}


class DatabaseQueryStats:
    def __init__(self):
        self.count = 0
        self.duration_ms = 0.0

    def __call__(self, execute, sql, params, many, context):
        started = perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            self.count += 1
            self.duration_ms += (perf_counter() - started) * 1000.0


def _budget(metric_name: str) -> dict[str, Any]:
    return dict(PERFORMANCE_BUDGETS.get(metric_name, DEFAULT_BUDGET))


def _severity(metric_name: str, duration_ms: float) -> str:
    budget = _budget(metric_name)
    if duration_ms >= float(budget["severe_ms"]):
        return "critical"
    if duration_ms >= float(budget["warning_ms"]):
        return "warning"
    if duration_ms > float(budget["target_ms"]):
        return "watch"
    return "normal"


def _sample_cache_key(metric_name: str) -> str:
    return f"pdp:performance-assurance:v1:samples:{metric_name}"


def _record_sample(
    metric_name: str,
    *,
    duration_ms: float,
    db_ms: float,
    query_count: int,
    status_code: int,
) -> None:
    # This is deliberately low-cardinality and sanitized: no SQL, params,
    # URLs, user identifiers, business payloads or request bodies are stored.
    sample = {
        "at": timezone.now().isoformat(),
        "duration_ms": round(duration_ms, 1),
        "db_ms": round(db_ms, 1),
        "query_count": int(query_count),
        "status_code": int(status_code),
        "severity": _severity(metric_name, duration_ms),
    }
    key = _sample_cache_key(metric_name)
    current = cache.get(key, [])
    values = deque(current if isinstance(current, list) else [], maxlen=SAMPLE_LIMIT)
    values.append(sample)
    cache.set(key, list(values), CACHE_TTL_SECONDS)

    metric_index = cache.get(CACHE_INDEX_KEY, [])
    names = list(metric_index) if isinstance(metric_index, list) else []
    if metric_name not in names:
        names.append(metric_name)
        cache.set(CACHE_INDEX_KEY, names[-100:], CACHE_TTL_SECONDS)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = int(round((len(ordered) - 1) * percentile))
    return ordered[max(0, min(index, len(ordered) - 1))]


def performance_assurance_snapshot(*, compact: bool = False) -> dict[str, Any]:
    metric_index = cache.get(CACHE_INDEX_KEY, [])
    names = list(PERFORMANCE_BUDGETS)
    for name in metric_index if isinstance(metric_index, list) else []:
        if name not in names:
            names.append(name)

    metrics: dict[str, Any] = {}
    critical_metrics = 0
    warning_metrics = 0
    for metric_name in names:
        raw_samples = cache.get(_sample_cache_key(metric_name), [])
        samples = raw_samples if isinstance(raw_samples, list) else []
        durations = [float(item.get("duration_ms", 0.0)) for item in samples]
        db_times = [float(item.get("db_ms", 0.0)) for item in samples]
        queries = [int(item.get("query_count", 0)) for item in samples]
        budget = _budget(metric_name)

        p50 = round(_percentile(durations, 0.50), 1)
        p95 = round(_percentile(durations, 0.95), 1)
        last = samples[-1] if samples else None
        current_class = _severity(metric_name, p95) if samples else "no_data"
        if current_class == "critical":
            critical_metrics += 1
        elif current_class in {"warning", "watch"}:
            warning_metrics += 1

        baseline_samples = durations[: min(10, len(durations))]
        baseline_ms = round(median(baseline_samples), 1) if baseline_samples else None
        regression_pct = None
        if baseline_ms and p50:
            regression_pct = round(((p50 - baseline_ms) / baseline_ms) * 100.0, 1)

        item = {
            "risk": budget["risk"],
            "target_ms": budget["target_ms"],
            "warning_ms": budget["warning_ms"],
            "severe_ms": budget["severe_ms"],
            "sample_count": len(samples),
            "p50_ms": p50,
            "p95_ms": p95,
            "max_ms": round(max(durations), 1) if durations else 0.0,
            "db_p95_ms": round(_percentile(db_times, 0.95), 1),
            "max_query_count": max(queries) if queries else 0,
            "baseline_p50_ms": baseline_ms,
            "regression_pct": regression_pct,
            "status": current_class,
            "last_sample": last,
        }
        if not compact:
            item["recent_samples"] = samples[-20:]
        metrics[metric_name] = item

    return {
        "schema": "pdp-one.performance-assurance.v1",
        "generated_at": timezone.now().isoformat(),
        "policy": {
            "mode": "risk_based",
            "light": "smoke_record_only",
            "standard": "measure_and_warn_by_default",
            "hot_path": "block_only_on_severe_material_regression",
            "stress_test_production": False,
            "sql_text_recorded": False,
            "business_payload_recorded": False,
        },
        "summary": {
            "metric_count": len(metrics),
            "critical_metrics": critical_metrics,
            "warning_or_watch_metrics": warning_metrics,
        },
        "metrics": metrics,
    }


def instrument_procurement_endpoint(metric_name: str):
    """Attach safe latency/query telemetry without logging SQL or business data."""

    def decorator(view_func):
        from functools import wraps

        @wraps(view_func)
        def wrapped(*args, **kwargs):
            stats = DatabaseQueryStats()
            started = perf_counter()
            with connection.execute_wrapper(stats):
                response = view_func(*args, **kwargs)
            duration_ms = (perf_counter() - started) * 1000.0
            severity = _severity(metric_name, duration_ms)
            status_code = int(getattr(response, "status_code", 200) or 200)
            _record_sample(
                metric_name,
                duration_ms=duration_ms,
                db_ms=stats.duration_ms,
                query_count=stats.count,
                status_code=status_code,
            )
            response["Server-Timing"] = (
                f'pdp;dur={duration_ms:.1f};desc="{metric_name}", '
                f'db;dur={stats.duration_ms:.1f}'
            )
            response["X-PDP-Query-Count"] = str(stats.count)
            response["X-PDP-Latency-Class"] = severity
            response["X-PDP-Performance-Risk"] = str(_budget(metric_name)["risk"])
            if severity in {"warning", "critical"}:
                logger.warning(
                    "procurement_endpoint_latency metric=%s duration_ms=%.1f db_ms=%.1f query_count=%d severity=%s",
                    metric_name,
                    duration_ms,
                    stats.duration_ms,
                    stats.count,
                    severity,
                )
            return response

        return wrapped

    return decorator
