from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import AuditEvent
from procurement.models import ProcurementCase, ProcurementNotice
from procurement.models_analysis import AnalysisBatch, AnalysisContextSnapshot, AnalysisRequest, NoticeAnalysisDraft
from procurement.models_direct import DirectOpportunity
from procurement.analysis_run_service import COMPACT_CLAIM_SCHEMA
from procurement.opportunity_types import (
    CONSULTING,
    CONSTRUCTION,
    EPC,
    HUMAN_SOURCE,
    UNCLASSIFIED,
    classify_business_opportunity_type,
)


class BusinessOpportunityTypeClassifierTests(SimpleTestCase):
    def test_analysis_contract_exposes_bounded_types_and_human_override(self):
        contract = COMPACT_CLAIM_SCHEMA["business_opportunity_type_contract"]
        self.assertEqual(
            contract["allowed"],
            [CONSULTING, EPC, CONSTRUCTION, UNCLASSIFIED],
        )
        self.assertIn("hot", " ".join(contract["rules"]))
        self.assertEqual(contract["required_result_fields"], ["ot", "otr", "otc"])

    def test_explicit_analysis_type_wins_with_reviewable_reason(self):
        classification = classify_business_opportunity_type(
            explicit="EPC",
            explicit_confidence=93,
            explicit_reason="دامنه مهندسی، تأمین و ساخت است.",
            evidence_values=("مطالعات",),
        )
        self.assertEqual(classification.value, EPC)
        self.assertEqual(classification.confidence, 93)
        self.assertIn("مهندسی", classification.reason)

    def test_historical_analysis_evidence_is_conservative(self):
        consulting = classify_business_opportunity_type(
            evidence_values=("خدمات مشاوره مطالعات و نظارت", "بررسی اسناد توسط مشاور"),
        )
        ambiguous = classify_business_opportunity_type(
            evidence_values=("تأمین کالای عمومی", "اطلاعات تکمیلی موجود نیست"),
        )
        self.assertEqual(consulting.value, CONSULTING)
        self.assertEqual(ambiguous.value, UNCLASSIFIED)

    def test_invalid_explicit_type_fails_closed_even_with_supporting_text(self):
        classification = classify_business_opportunity_type(
            explicit="invalid-type",
            evidence_values=("خدمات مشاوره مطالعات و نظارت",),
        )
        self.assertEqual(classification.value, UNCLASSIFIED)
        self.assertIn("معتبر نیست", classification.reason)

    def test_purchase_only_with_negated_design_reference_stays_unclassified(self):
        classification = classify_business_opportunity_type(
            evidence_values=(
                "استعلام ادوات ایستگاه هیدرومتری مطابق لیست پیوست",
                "خرید تجهیزات پایش منابع آب",
                "موضوع خرید تجهیزات آماده است نه خدمات مطالعه یا طراحی.",
            ),
        )
        self.assertEqual(classification.value, UNCLASSIFIED)
        self.assertIn("خرید", classification.reason)


class BusinessOpportunityTypeFilteringTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="opportunity-filter-manager", password="test-pass", is_staff=True
        )
        self.client.force_authenticate(self.user)
        self.now = timezone.now()
        self.context = AnalysisContextSnapshot.objects.create(
            version=9924,
            status=AnalysisContextSnapshot.Status.ACTIVE,
            role_text="تحلیلگر آزمون",
            base_instructions="خروجی فقط پیش‌نویس است.",
            analysis_prompt="نوع فرصت را تعیین کن.",
        )
        request = AnalysisRequest.objects.create(
            trigger=AnalysisRequest.Trigger.MANUAL_WEB,
            status=AnalysisRequest.Status.PROCESSING,
            context_snapshot=self.context,
            requested_by=self.user,
        )
        self.batch = AnalysisBatch.objects.create(
            request=request,
            context_snapshot=self.context,
            status=AnalysisBatch.Status.PROCESSING,
            sequence=1,
        )

    def notice(self, workflow, opportunity_type, index):
        notice = ProcurementNotice.objects.create(
            resolved_notice_type=ProcurementNotice.NoticeType.TENDER,
            title=f"{workflow}-{opportunity_type}-{index}",
            employer_name="کارفرمای آزمون",
            published_date=timezone.localdate(),
            submission_deadline=self.now + timedelta(days=5),
            business_opportunity_type=opportunity_type,
            business_opportunity_type_source=HUMAN_SOURCE,
            first_seen_at=self.now,
            last_seen_at=self.now,
        )
        stage_by_workflow = {
            "selected": ProcurementCase.Stage.SELECTED,
            "submitted": ProcurementCase.Stage.SUBMITTED,
            "results": ProcurementCase.Stage.WON,
        }
        if workflow in stage_by_workflow:
            ProcurementCase.objects.create(
                notice=notice,
                stage=stage_by_workflow[workflow],
                next_action="بررسی",
                created_by=self.user,
            )
        if workflow == "recommended":
            NoticeAnalysisDraft.objects.create(
                notice=notice,
                batch=self.batch,
                context_snapshot=self.context,
                notice_content_hash=(f"{index}{opportunity_type}" * 64)[:64],
                is_recommended=True,
                score=88,
                priority=NoticeAnalysisDraft.Priority.HIGH,
                fit_for_pdp="متناسب",
                category="آزمون",
                business_opportunity_type=opportunity_type,
                business_opportunity_type_confidence=90,
                business_opportunity_type_reason="آزمون",
                reason="متناسب",
                recommended_action="بازبینی",
                confidence=90,
            )
            notice.is_recommended = True
            notice.save(update_fields=["is_recommended", "updated_at"])
        return notice

    def test_multi_select_filters_every_notice_workflow_on_server(self):
        for workflow in ("recent", "recommended", "selected", "submitted", "results"):
            expected = {
                str(self.notice(workflow, CONSULTING, 1).id),
                str(self.notice(workflow, EPC, 2).id),
            }
            self.notice(workflow, CONSTRUCTION, 3)
            response = self.client.get(
                "/api/v1/procurement/ui/notices/",
                [
                    ("notice_type", "tender"),
                    ("workflow", workflow),
                    ("business_opportunity_type", CONSULTING),
                    ("business_opportunity_type", EPC),
                ],
            )
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual({row["id"] for row in response.data["results"]}, expected)
            self.assertTrue(all("business_opportunity_type_label" in row for row in response.data["results"]))

    def test_direct_referrals_use_the_same_business_type_filter(self):
        consulting = DirectOpportunity.objects.create(
            title="مطالعات طرح",
            employer_name="کارفرما",
            next_action="تماس",
            business_opportunity_type=CONSULTING,
            business_opportunity_type_source=HUMAN_SOURCE,
            responsible=self.user,
        )
        epc = DirectOpportunity.objects.create(
            title="طرح و ساخت",
            employer_name="کارفرما",
            next_action="جلسه",
            business_opportunity_type=EPC,
            business_opportunity_type_source=HUMAN_SOURCE,
            responsible=self.user,
        )
        DirectOpportunity.objects.create(
            title="عملیات اجرایی",
            employer_name="کارفرما",
            next_action="بازدید",
            business_opportunity_type=CONSTRUCTION,
            business_opportunity_type_source=HUMAN_SOURCE,
            responsible=self.user,
        )
        response = self.client.get(
            "/api/v1/procurement/direct-opportunities/",
            [
                ("business_opportunity_type", CONSULTING),
                ("business_opportunity_type", EPC),
            ],
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            {row["id"] for row in response.data["results"]},
            {str(consulting.id), str(epc.id)},
        )

    def test_invalid_filter_value_fails_closed(self):
        self.notice("recent", CONSULTING, 20)
        response = self.client.get(
            "/api/v1/procurement/ui/notices/",
            {"notice_type": "tender", "workflow": "recent", "business_opportunity_type": "invalid"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)

    def test_authenticated_human_can_set_notice_type_with_audit_event(self):
        notice = self.notice("recent", UNCLASSIFIED, 30)
        response = self.client.post(
            f"/api/v1/procurement/tenders/{notice.id}/business-opportunity-type/",
            {"business_opportunity_type": EPC, "reason": "تأیید اسناد طرح و ساخت"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        notice.refresh_from_db()
        self.assertEqual(notice.business_opportunity_type, EPC)
        self.assertEqual(notice.business_opportunity_type_source, HUMAN_SOURCE)
        self.assertIsNone(notice.business_opportunity_type_confidence)
        self.assertEqual(
            AuditEvent.objects.filter(
                action="procurement.business_opportunity_type.set_human",
                target_id=str(notice.id),
            ).count(),
            1,
        )

    def test_direct_human_type_survives_unrelated_updates(self):
        opportunity = DirectOpportunity.objects.create(
            title="فرصت نامشخص",
            employer_name="کارفرما",
            next_action="بررسی",
            responsible=self.user,
        )
        first = self.client.patch(
            f"/api/v1/procurement/direct-opportunities/{opportunity.id}/",
            {"business_opportunity_type": CONSULTING},
            format="json",
        )
        self.assertEqual(first.status_code, 200, first.data)
        second = self.client.patch(
            f"/api/v1/procurement/direct-opportunities/{opportunity.id}/",
            {"title": "عنوان اصلاح‌شده"},
            format="json",
        )
        self.assertEqual(second.status_code, 200, second.data)
        opportunity.refresh_from_db()
        self.assertEqual(opportunity.business_opportunity_type, CONSULTING)
        self.assertEqual(opportunity.business_opportunity_type_source, HUMAN_SOURCE)
