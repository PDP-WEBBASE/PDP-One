from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .analysis_megabatch_benchmark import (
    create_megabatch_benchmark,
    get_megabatch_benchmark_batch,
    megabatch_benchmark_status,
    submit_megabatch_benchmark_results,
)


def _allowed(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (getattr(user, "is_staff", False) or getattr(user, "username", "") == "chatgpt-service")
    )


def _deny(request):
    if not _allowed(request.user):
        return Response(
            {"detail": "این عملیات فقط برای مدیر سامانه یا سرویس رسمی ChatGPT مجاز است."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def start_megabatch_benchmark(request):
    denied = _deny(request)
    if denied:
        return denied
    try:
        result = create_megabatch_benchmark(
            run_id=str(request.data.get("run_id") or ""),
            corpus_size=int(request.data.get("corpus_size") or 5000),
        )
    except (TypeError, ValueError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"benchmark": result}, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def megabatch_benchmark_batch(request, benchmark_id):
    denied = _deny(request)
    if denied:
        return denied
    try:
        result = get_megabatch_benchmark_batch(
            benchmark_id=str(benchmark_id),
            stage_size=int(request.query_params.get("stage_size") or 50),
            offset=int(request.query_params.get("offset") or 0),
        )
    except (TypeError, ValueError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"batch": result})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_megabatch_benchmark(request, benchmark_id):
    denied = _deny(request)
    if denied:
        return denied
    try:
        result = submit_megabatch_benchmark_results(
            benchmark_id=str(benchmark_id),
            stage_size=int(request.data.get("stage_size") or 50),
            offset=int(request.data.get("offset") or 0),
            results=list(request.data.get("results") or []),
        )
    except (TypeError, ValueError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"stage": result}, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def megabatch_benchmark_status_view(request, benchmark_id):
    denied = _deny(request)
    if denied:
        return denied
    try:
        result = megabatch_benchmark_status(str(benchmark_id))
    except (TypeError, ValueError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    return Response({"benchmark": result})
