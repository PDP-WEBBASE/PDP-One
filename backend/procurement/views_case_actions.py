from rest_framework import mixins
from rest_framework.exceptions import ValidationError

from core.models import AuditEvent

from .models import ProcurementCase, ProcurementNotice
from .views import ProcurementCaseViewSet as BaseProcurementCaseViewSet


class ProcurementCaseViewSet(mixins.DestroyModelMixin, BaseProcurementCaseViewSet):
    """Extend the normal case API with a guarded 'remove from selected' action.

    Deleting a case never deletes the procurement notice. It only removes the
    human-created workflow case while it is still before submission and has no
    stored submission documents.
    """

    REMOVABLE_STAGES = {
        ProcurementCase.Stage.SELECTED,
        ProcurementCase.Stage.EVALUATING,
        ProcurementCase.Stage.PARTICIPATE,
        ProcurementCase.Stage.PREPARING,
        ProcurementCase.Stage.READY_TO_SUBMIT,
    }

    def perform_destroy(self, instance):
        if instance.stage not in self.REMOVABLE_STAGES:
            raise ValidationError(
                {
                    "detail": (
                        "پرونده‌ای که وارد مرحله ارسال یا نتیجه شده است از مسیر «حذف از منتخب» "
                        "قابل حذف نیست. برای حفظ سابقه، وضعیت آن را در گردش‌کار مدیریت کنید."
                    )
                }
            )
        if instance.submission_documents.exists():
            raise ValidationError(
                {
                    "detail": (
                        "برای این پرونده سند ذخیره شده است؛ برای حفظ سابقه مدارک، حذف از منتخب مجاز نیست."
                    )
                }
            )

        notice_id = instance.notice_id
        case_id = str(instance.id)
        stage = instance.stage
        instance.delete()
        ProcurementNotice.objects.filter(pk=notice_id).update(retention_protected=False)
        AuditEvent.objects.create(
            actor=self.request.user.username,
            action="procurement.case.remove_from_selected",
            target_type="procurement_case",
            target_id=case_id,
            payload={
                "notice_id": str(notice_id),
                "stage_before": stage,
                "notice_deleted": False,
            },
        )
