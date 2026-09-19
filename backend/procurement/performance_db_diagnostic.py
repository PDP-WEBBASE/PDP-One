from __future__ import annotations

import json
from types import SimpleNamespace
from time import perf_counter

from django.core.cache import cache
from django.db import connection
from django.http import QueryDict

from .analysis_run_service import active_run
from .performance_metrics import DatabaseQueryStats
from .views_bulk_workflow import _user_dismissed_notice_ids
from .views_compact_ui import _compact_notice_queryset

DIAGNOSTIC_CACHE_KEY = "pdp:performance-assurance:v1:inquiry-recommended-db-diagnostic"
DIAGNOSTIC_CACHE_TTL_SECONDS = 10 * 60
DIAGNOSTIC_PAGE_SIZE = 50
MAX_PLAN_NODES = 80


def _request(user):
    query = QueryDict("", mutable=True)
    query["notice_type"] = "inquiry"
    query["workflow"] = "recommended"
    query["page"] = "1"
    query["page_size"] = str(DIAGNOSTIC_PAGE_SIZE)
    query["ordering"] = "-publication_sort,-last_seen_at,-id"
    return SimpleNamespace(query_params=query, user=user)


def _build_queryset(request):
    queryset = _compact_notice_queryset(request)
    dismissed_ids = _user_dismissed_notice_ids(request, "recommended")
    if dismissed_ids:
        queryset = queryset.exclude(pk__in=dismissed_ids)
    return queryset


def _summarize_plan(raw_plan):
    if not isinstance(raw_plan, list) or not raw_plan:
        return {"available": False, "reason": "unexpected_plan_shape", "nodes": []}
    root = raw_plan[0].get("Plan") if isinstance(raw_plan[0], dict) else None
    if not isinstance(root, dict):
        return {"available": False, "reason": "missing_plan_root", "nodes": []}

    nodes = []

    def walk(node, depth=0):
        if not isinstance(node, dict) or len(nodes) >= MAX_PLAN_NODES:
            return
        item = {
            "depth": depth,
            "node_type": str(node.get("Node Type") or ""),
            "relation": str(node.get("Relation Name") or ""),
            "index": str(node.get("Index Name") or ""),
            "join_type": str(node.get("Join Type") or ""),
            "estimated_rows": int(node.get("Plan Rows") or 0),
            "startup_cost": float(node.get("Startup Cost") or 0),
            "total_cost": float(node.get("Total Cost") or 0),
        }
        nodes.append(item)
        for child in node.get("Plans") or []:
            walk(child, depth + 1)

    walk(root)
    seq_scan_relations = sorted({
        item["relation"]
        for item in nodes
        if item["node_type"] == "Seq Scan" and item["relation"]
    })
    used_indexes = sorted({
        item["index"]
        for item in nodes
        if item["index"]
    })
    return {
        "available": True,
        "root_node_type": str(root.get("Node Type") or ""),
        "root_total_cost": float(root.get("Total Cost") or 0),
        "root_estimated_rows": int(root.get("Plan Rows") or 0),
        "node_count": len(nodes),
        "seq_scan_relations": seq_scan_relations,
        "used_indexes": used_indexes,
        "nodes": nodes,
    }


def _explain_query(queryset):
    if connection.vendor != "postgresql":
        return {"available": False, "reason": "postgresql_required", "nodes": []}
    try:
        plan_text = queryset[: DIAGNOSTIC_PAGE_SIZE + 1].explain(
            format="json",
            analyze=False,
            verbose=False,
            costs=True,
            buffers=False,
        )
        return _summarize_plan(json.loads(plan_text))
    except Exception as exc:
        return {
            "available": False,
            "reason": "explain_failed",
            "safe_error": exc.__class__.__name__,
            "nodes": [],
        }


def _postgres_runtime_summary():
    if connection.vendor != "postgresql":
        return {
            "available": False,
            "reason": "postgresql_required",
            "activity": {},
            "tables": [],
            "indexes": [],
        }

    result = {
        "available": True,
        "activity": {},
        "tables": [],
        "indexes": [],
        "database": {},
    }
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE pid <> pg_backend_pid()) AS sessions,
                    COUNT(*) FILTER (WHERE pid <> pg_backend_pid() AND state = 'active') AS active_sessions,
                    COUNT(*) FILTER (
                        WHERE pid <> pg_backend_pid()
                          AND wait_event_type IS NOT NULL
                    ) AS waiting_sessions,
                    COUNT(*) FILTER (
                        WHERE pid <> pg_backend_pid()
                          AND cardinality(pg_blocking_pids(pid)) > 0
                    ) AS blocked_sessions
                FROM pg_stat_activity
                WHERE datname = current_database()
                """
            )
            row = cursor.fetchone() or (0, 0, 0, 0)
            result["activity"] = {
                "sessions": int(row[0] or 0),
                "active_sessions": int(row[1] or 0),
                "waiting_sessions": int(row[2] or 0),
                "blocked_sessions": int(row[3] or 0),
            }

            cursor.execute(
                """
                SELECT
                    wait_event_type,
                    wait_event,
                    COUNT(*)
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND pid <> pg_backend_pid()
                  AND wait_event_type IS NOT NULL
                GROUP BY wait_event_type, wait_event
                ORDER BY COUNT(*) DESC, wait_event_type, wait_event
                LIMIT 12
                """
            )
            result["activity"]["wait_events"] = [
                {
                    "wait_event_type": str(wait_type or ""),
                    "wait_event": str(wait_event or ""),
                    "sessions": int(count or 0),
                }
                for wait_type, wait_event, count in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT
                    relname,
                    COALESCE(n_live_tup, 0),
                    COALESCE(n_dead_tup, 0),
                    COALESCE(seq_scan, 0),
                    COALESCE(idx_scan, 0),
                    last_autovacuum,
                    last_autoanalyze
                FROM pg_stat_user_tables
                WHERE relname IN (
                    'procurement_noticeanalysisdraft',
                    'procurement_procurementnotice'
                )
                ORDER BY relname
                """
            )
            result["tables"] = [
                {
                    "relation": str(relname),
                    "live_rows_estimate": int(live_rows or 0),
                    "dead_rows_estimate": int(dead_rows or 0),
                    "seq_scan_count": int(seq_scan or 0),
                    "index_scan_count": int(idx_scan or 0),
                    "last_autovacuum": last_autovacuum.isoformat() if last_autovacuum else None,
                    "last_autoanalyze": last_autoanalyze.isoformat() if last_autoanalyze else None,
                }
                for relname, live_rows, dead_rows, seq_scan, idx_scan, last_autovacuum, last_autoanalyze in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT
                    ui.relname,
                    ui.indexrelname,
                    COALESCE(ui.idx_scan, 0),
                    pg_relation_size(ui.indexrelid)
                FROM pg_stat_user_indexes ui
                WHERE ui.relname = 'procurement_noticeanalysisdraft'
                ORDER BY ui.idx_scan DESC, ui.indexrelname
                """
            )
            result["indexes"] = [
                {
                    "relation": str(relname),
                    "index": str(index_name),
                    "scan_count": int(scan_count or 0),
                    "size_bytes": int(size_bytes or 0),
                }
                for relname, index_name, scan_count, size_bytes in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT
                    COALESCE(blks_read, 0),
                    COALESCE(blks_hit, 0),
                    COALESCE(temp_files, 0),
                    COALESCE(temp_bytes, 0),
                    COALESCE(deadlocks, 0),
                    COALESCE(conflicts, 0)
                FROM pg_stat_database
                WHERE datname = current_database()
                """
            )
            db = cursor.fetchone() or (0, 0, 0, 0, 0, 0)
            result["database"] = {
                "blocks_read": int(db[0] or 0),
                "blocks_hit": int(db[1] or 0),
                "temp_files": int(db[2] or 0),
                "temp_bytes": int(db[3] or 0),
                "deadlocks": int(db[4] or 0),
                "conflicts": int(db[5] or 0),
            }
    except Exception as exc:
        return {
            "available": False,
            "reason": "postgres_stats_unavailable",
            "safe_error": exc.__class__.__name__,
            "activity": {},
            "tables": [],
            "indexes": [],
        }
    return result


def _analysis_state():
    run = active_run()
    if run is None:
        return {"active": False}
    counters = run.counters or {}
    return {
        "active": True,
        "run_id": str(run.id),
        "status": run.status,
        "remaining": int(counters.get("remaining", 0) or 0),
        "claimed": int(counters.get("claimed", 0) or 0),
        "completed": int(counters.get("completed", 0) or 0),
        "retry": int(counters.get("retry", 0) or 0),
    }


def collect_inquiry_recommended_db_diagnostic(user, *, force=False):
    """Collect one bounded read-only diagnostic for Inquiry -> Recommended.

    The diagnostic has no arbitrary SQL input, never returns SQL text or query
    parameters, uses EXPLAIN without ANALYZE, and caches results for ten minutes.
    """

    if not force:
        cached = cache.get(DIAGNOSTIC_CACHE_KEY)
        if isinstance(cached, dict):
            return {**cached, "cache_hit": True}

    request = _request(user)
    queryset = _build_queryset(request)

    stats = DatabaseQueryStats()
    started = perf_counter()
    with connection.execute_wrapper(stats):
        rows = list(queryset[: DIAGNOSTIC_PAGE_SIZE + 1])
    duration_ms = (perf_counter() - started) * 1000.0

    plan = _explain_query(queryset)
    postgres = _postgres_runtime_summary()
    analysis = _analysis_state()

    db_share = (stats.duration_ms / duration_ms * 100.0) if duration_ms > 0 else 0.0
    diagnosis = []
    if postgres.get("activity", {}).get("blocked_sessions", 0):
        diagnosis.append("blocking_present_at_snapshot")
    if postgres.get("activity", {}).get("waiting_sessions", 0):
        diagnosis.append("database_waits_present_at_snapshot")
    if "procurement_noticeanalysisdraft" in set(plan.get("seq_scan_relations") or []):
        diagnosis.append("analysis_draft_sequential_scan_in_plan")
    if duration_ms >= 1500 and db_share >= 70:
        diagnosis.append("reproduced_db_stall")
    if duration_ms < 1000:
        diagnosis.append("current_bounded_query_within_budget")

    result = {
        "schema": "pdp-one.inquiry-recommended-db-diagnostic.v1",
        "cache_hit": False,
        "read_only": True,
        "stress_test": False,
        "page_size": DIAGNOSTIC_PAGE_SIZE,
        "explain_analyze_used": False,
        "sql_text_recorded": False,
        "sql_params_recorded": False,
        "business_payload_recorded": False,
        "query_sample": {
            "duration_ms": round(duration_ms, 1),
            "db_ms": round(stats.duration_ms, 1),
            "db_share_pct": round(db_share, 1),
            "query_count": int(stats.count),
            "rows": min(len(rows), DIAGNOSTIC_PAGE_SIZE),
            "has_more": len(rows) > DIAGNOSTIC_PAGE_SIZE,
        },
        "plan": plan,
        "postgres": postgres,
        "analysis": analysis,
        "diagnosis_signals": diagnosis,
    }
    cache.set(DIAGNOSTIC_CACHE_KEY, result, DIAGNOSTIC_CACHE_TTL_SECONDS)
    return result
