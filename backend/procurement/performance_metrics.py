import logging
from functools import wraps
from time import perf_counter

from django.db import connection

logger = logging.getLogger("procurement.performance")

WARNING_MS = 500.0
HIGH_MS = 1500.0
CRITICAL_MS = 3000.0


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


def _severity(duration_ms: float) -> str:
    if duration_ms >= CRITICAL_MS:
        return "critical"
    if duration_ms >= HIGH_MS:
        return "high"
    if duration_ms >= WARNING_MS:
        return "warning"
    return "normal"


def instrument_procurement_endpoint(metric_name: str):
    """Attach safe latency/query telemetry without logging SQL or business data."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            stats = DatabaseQueryStats()
            started = perf_counter()
            with connection.execute_wrapper(stats):
                response = view_func(*args, **kwargs)
            duration_ms = (perf_counter() - started) * 1000.0
            response["Server-Timing"] = f'pdp;dur={duration_ms:.1f};desc="{metric_name}", db;dur={stats.duration_ms:.1f}'
            response["X-PDP-Query-Count"] = str(stats.count)
            response["X-PDP-Latency-Class"] = _severity(duration_ms)
            if duration_ms >= WARNING_MS:
                logger.warning(
                    "procurement_endpoint_latency metric=%s duration_ms=%.1f db_ms=%.1f query_count=%d severity=%s",
                    metric_name,
                    duration_ms,
                    stats.duration_ms,
                    stats.count,
                    _severity(duration_ms),
                )
            return response

        return wrapped

    return decorator
