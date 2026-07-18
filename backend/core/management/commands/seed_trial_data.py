import os
from datetime import date

from django.core.management.base import BaseCommand

from core.models import AuditEvent, Contract, Receivable


class Command(BaseCommand):
    help = "Create an idempotent, clearly-labelled PDP One trial dataset when PDP_TRIAL_MODE is enabled."

    def handle(self, *args, **options):
        if os.getenv("PDP_TRIAL_MODE", "false").lower() not in {"1", "true", "yes"}:
            self.stdout.write("Trial data is disabled.")
            return

        contract, contract_created = Contract.objects.get_or_create(
            code="TEST-1405-001",
            defaults={
                "title": "قرارداد آزمایشی مطالعات و طراحی دفتر مرکزی",
                "employer": "شرکت نمونه آزمایشی",
                "field": "معماری",
                "value_rials": 12_500_000_000,
                "progress": 0,
                "due_date": date(2026, 12, 21),
                "status": Contract.Status.DRAFT,
            },
        )

        receivable = Receivable.objects.filter(
            contract_code=contract.code,
            statement_title="صورت‌وضعیت آزمایشی شماره ۱",
        ).first()
        receivable_created = receivable is None
        if receivable_created:
            receivable = Receivable.objects.create(
                contract_code=contract.code,
                contract_title=contract.title,
                employer=contract.employer,
                statement_title="صورت‌وضعیت آزمایشی شماره ۱",
                amount_rials=5_000_000_000,
                received_rials=0,
                due_date=date(2026, 8, 15),
                status=Receivable.Status.DRAFT,
            )

        if contract_created:
            AuditEvent.objects.create(
                actor="system-trial-seed",
                action="contract.create_trial_draft",
                target_type="contract",
                target_id=str(contract.id),
                payload={"code": contract.code, "test_data": True},
            )
        if receivable_created:
            AuditEvent.objects.create(
                actor="system-trial-seed",
                action="receivable.create_trial_draft",
                target_type="receivable",
                target_id=str(receivable.id),
                payload={"contract_code": contract.code, "test_data": True},
            )

        self.stdout.write(self.style.SUCCESS("PDP One trial dataset is ready."))
