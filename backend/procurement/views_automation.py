from rest_framework import mixins
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

    def perform_update(self, serializer):
        before = {
            "enabled": serializer.instance.enabled,
            "cadence": serializer.instance.cadence,
            "interval_minutes": serializer.instance.interval_minutes,
            "daily_time": str(serializer.instance.daily_time or ""),
            "analysis_delay_minutes": serializer.instance.analysis_delay_minutes,
        }
        settings = serializer.save()
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.automation_settings.update",
            target_type="procurement_automation_settings",
            target_id=str(settings.id),
            payload={
                "before": before,
                "after": {
                    "enabled": settings.enabled,
                    "cadence": settings.cadence,
                    "interval_minutes": settings.interval_minutes,
                    "daily_time": str(settings.daily_time or ""),
                    "analysis_delay_minutes": settings.analysis_delay_minutes,
                    "manual_command": "PDP",
                },
            },
        )
