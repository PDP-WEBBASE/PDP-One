from django.contrib import admin

from .models import (
    NoticeSourceLink,
    ProcurementCase,
    ProcurementConnector,
    ProcurementNotice,
    ProcurementSource,
    SourceNotice,
    SourceNoticeRevision,
)
from .opportunity_types import HUMAN_SOURCE


@admin.register(ProcurementSource)
class ProcurementSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "enabled", "status", "last_success_at", "last_failure_at")
    list_filter = ("enabled", "status")
    search_fields = ("name", "key", "base_url")
    readonly_fields = ("id", "created_at", "updated_at", "last_success_at", "last_failure_at")


@admin.register(ProcurementConnector)
class ProcurementConnectorAdmin(admin.ModelAdmin):
    list_display = ("key", "source", "notice_type", "enabled", "status", "parser_version")
    list_filter = ("source", "notice_type", "enabled", "status")
    search_fields = ("key", "source__name", "list_url_template")
    readonly_fields = ("id", "created_at", "updated_at", "last_success_at", "last_failure_at")


@admin.register(SourceNotice)
class SourceNoticeAdmin(admin.ModelAdmin):
    list_display = ("source_record_id", "connector", "title_raw", "detail_status", "last_seen_at", "is_active")
    list_filter = ("connector", "detail_status", "is_active")
    search_fields = ("source_record_id", "title_raw", "employer_raw", "province_raw")
    readonly_fields = ("id", "created_at", "updated_at", "raw_payload")


@admin.register(SourceNoticeRevision)
class SourceNoticeRevisionAdmin(admin.ModelAdmin):
    list_display = ("source_notice", "revision_number", "parser_version", "captured_at")
    list_filter = ("parser_version",)
    search_fields = ("source_notice__source_record_id", "content_hash")
    readonly_fields = ("id", "created_at", "updated_at", "raw_payload", "parsed_payload", "changed_fields")


@admin.register(ProcurementNotice)
class ProcurementNoticeAdmin(admin.ModelAdmin):
    list_display = ("title", "resolved_notice_type", "business_opportunity_type", "employer_name", "submission_deadline", "processing_status", "is_recommended")
    list_filter = ("resolved_notice_type", "business_opportunity_type", "business_opportunity_type_source", "type_resolution_status", "processing_status", "is_recommended", "retention_protected")
    search_fields = ("title", "normalized_title", "employer_name", "notice_number", "province")
    readonly_fields = ("id", "created_at", "updated_at", "first_seen_at", "last_seen_at")

    def save_model(self, request, obj, form, change):
        if "business_opportunity_type" in form.changed_data:
            obj.business_opportunity_type_source = HUMAN_SOURCE
            obj.business_opportunity_type_confidence = None
            obj.business_opportunity_type_reason = "نوع فرصت توسط مدیر سامانه تعیین شده است."
        super().save_model(request, obj, form, change)


@admin.register(NoticeSourceLink)
class NoticeSourceLinkAdmin(admin.ModelAdmin):
    list_display = ("procurement_notice", "source_notice", "match_type", "confidence", "confirmed_by")
    list_filter = ("match_type",)
    search_fields = ("procurement_notice__title", "source_notice__source_record_id")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ProcurementCase)
class ProcurementCaseAdmin(admin.ModelAdmin):
    list_display = ("notice", "stage", "responsible", "next_action_due", "progress")
    list_filter = ("stage", "responsible", "protected_from_retention")
    search_fields = ("notice__title", "notice__employer_name", "next_action", "decision_reason")
    readonly_fields = ("id", "created_at", "updated_at", "created_by", "protected_from_retention")
