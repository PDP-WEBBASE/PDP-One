from datetime import time

from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from core.models import AuditEvent

from .models_automation import ProcurementAutomationSettings
from .permissions import IsSystemAdministratorOrReadOnly
from .serializers_automation import ProcurementAutomationSettingsSerializer


class ProcurementAutomationSettingsViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    queryset = ProcurementAutomationSettings.objects.select_related("updated_by").all()
    serializer_class = ProcurementAutomationSettingsSerializer
    permission_classes = [IsSystemAdministratorOrReadOnly]

    @staticmethod
    def _snapshot(settings):
        return {
            "enabled": settings.enabled,
            "cadence": settings.cadence,
            "interval_minutes": settings.interval_minutes,
            "daily_time": str(settings.daily_time or ""),
            "analysis_delay_minutes": settings.analysis_delay_minutes,
        }

    def _record_update_audit(self, settings, before, *, created=False):
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.automation_settings.update",
            target_type="procurement_automation_settings",
            target_id=str(settings.id),
            payload={
                "created_default_record": created,
                "before": before,
                "after": {
                    **self._snapshot(settings),
                    "manual_command": "PDP",
                },
            },
        )

    def perform_update(self, serializer):
        before = self._snapshot(serializer.instance)
        settings = serializer.save()
        self._record_update_audit(settings, before)

    @action(detail=False, methods=["get", "patch"], url_path="default")
    def default_settings(self, request):
        """Read or safely repair/update the single user-facing automation settings record."""
        settings = self.get_queryset().filter(key="default").first()

        if request.method == "GET":
            if settings is None:
                return Response(
                    {"detail": "رکورد تنظیمات خودکارسازی هنوز ایجاد نشده است."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response(self.get_serializer(settings).data)

        created = False
        if settings is None:
            settings, created = ProcurementAutomationSettings.objects.get_or_create(
                key="default",
                defaults={
                    "enabled": False,
                    "cadence": ProcurementAutomationSettings.Cadence.DAILY,
                    "interval_minutes": 60,
                    "daily_time": time(11, 0),
                    "timezone_name": "Asia/Tehran",
                    "analysis_delay_minutes": 60,
                    "scheduled_task_enabled": True,
                    "manual_command": "PDP",
                },
            )

        before = self._snapshot(settings)
        serializer = self.get_serializer(settings, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        settings = serializer.save()
        self._record_update_audit(settings, before, created=created)
        return Response(self.get_serializer(settings).data)
