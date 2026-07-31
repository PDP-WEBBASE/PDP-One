from rest_framework import serializers

from .analysis_review import human_review_metadata
from .models_analysis import NoticeAnalysisDraft
from .serializers_analysis import NoticeAnalysisDraftSerializer


class AIReviewDraftSerializer(NoticeAnalysisDraftSerializer):
    notice_employer_name = serializers.CharField(source="notice.employer_name", read_only=True)
    notice_type = serializers.CharField(source="notice.resolved_notice_type", read_only=True)
    notice_type_label = serializers.CharField(source="notice.get_resolved_notice_type_display", read_only=True)
    notice_province = serializers.CharField(source="notice.province", read_only=True)
    submission_deadline = serializers.DateTimeField(source="notice.submission_deadline", read_only=True)
    needs_revision = serializers.SerializerMethodField()
    review_note = serializers.SerializerMethodField()
    reviewed_by = serializers.SerializerMethodField()
    reviewed_at = serializers.SerializerMethodField()
    case_id = serializers.SerializerMethodField()
    case_stage = serializers.SerializerMethodField()
    case_stage_label = serializers.SerializerMethodField()
    can_select = serializers.SerializerMethodField()

    class Meta(NoticeAnalysisDraftSerializer.Meta):
        fields = NoticeAnalysisDraftSerializer.Meta.fields + [
            "notice_employer_name",
            "notice_type",
            "notice_type_label",
            "notice_province",
            "submission_deadline",
            "needs_revision",
            "review_note",
            "reviewed_by",
            "reviewed_at",
            "case_id",
            "case_stage",
            "case_stage_label",
            "can_select",
        ]
        read_only_fields = fields

    def get_needs_revision(self, obj):
        return (
            obj.review_status == NoticeAnalysisDraft.ReviewStatus.AI_DRAFT
            and human_review_metadata(obj).get("decision") == "needs_revision"
        )

    def get_review_note(self, obj):
        return str(human_review_metadata(obj).get("note", ""))

    def get_reviewed_by(self, obj):
        return str(human_review_metadata(obj).get("reviewed_by", ""))

    def get_reviewed_at(self, obj):
        return human_review_metadata(obj).get("reviewed_at")

    @staticmethod
    def _case(obj):
        try:
            return obj.notice.case
        except AttributeError:
            return None

    def get_case_id(self, obj):
        case = self._case(obj)
        return str(case.id) if case else None

    def get_case_stage(self, obj):
        case = self._case(obj)
        return case.stage if case else None

    def get_case_stage_label(self, obj):
        case = self._case(obj)
        return case.get_stage_display() if case else None

    def get_can_select(self, obj):
        return bool(
            obj.is_recommended
            and obj.review_status in {
                NoticeAnalysisDraft.ReviewStatus.REVIEWED,
                NoticeAnalysisDraft.ReviewStatus.PUBLISHED,
            }
            and self._case(obj) is None
        )
