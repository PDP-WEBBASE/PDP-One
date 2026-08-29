import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("procurement", "0026_correct_negated_opportunity_evidence"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProcurementDomainRevision",
            fields=[
                ("domain", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("revision", models.PositiveBigIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="ProcurementWriteLease",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("conversation_key", models.CharField(max_length=160)),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("scope", models.JSONField(default=list)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="procurement_write_leases", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="ProcurementPendingAction",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("conversation_key", models.CharField(max_length=160)),
                ("command", models.CharField(max_length=120)),
                ("command_version", models.PositiveSmallIntegerField(default=1)),
                ("candidates", models.JSONField(default=list)),
                ("requested_payload", models.JSONField(default=dict)),
                ("status", models.CharField(choices=[("awaiting_confirmation", "در انتظار تایید"), ("confirmed", "تایید شده"), ("cancelled", "لغو شده"), ("expired", "منقضی"), ("executed", "اجرا شده")], default="awaiting_confirmation", max_length=32)),
                ("expires_at", models.DateTimeField()),
                ("confirmed_notice", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="confirmed_pending_actions", to="procurement.procurementnotice")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="procurement_pending_actions", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="ProcurementChangeJournal",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("domain", models.CharField(default="procurement", max_length=64)),
                ("revision", models.PositiveBigIntegerField()),
                ("entity_type", models.CharField(max_length=100)),
                ("entity_id", models.CharField(max_length=100)),
                ("action", models.CharField(max_length=120)),
                ("affected_contexts", models.JSONField(default=list)),
                ("correlation_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)),
                ("payload", models.JSONField(default=dict)),
            ],
            options={"ordering": ["-revision", "-created_at"]},
        ),
        migrations.CreateModel(
            name="ProcurementOutboxEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("event_type", models.CharField(max_length=120)),
                ("aggregate_type", models.CharField(max_length=100)),
                ("aggregate_id", models.CharField(max_length=100)),
                ("correlation_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)),
                ("payload", models.JSONField(default=dict)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_error", models.CharField(blank=True, max_length=500)),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.AddIndex(model_name="procurementwritelease", index=models.Index(fields=["user", "conversation_key", "expires_at"], name="proc_write_lease_scope_idx")),
        migrations.AddIndex(model_name="procurementpendingaction", index=models.Index(fields=["user", "conversation_key", "status"], name="proc_pending_action_scope_idx")),
        migrations.AddIndex(model_name="procurementchangejournal", index=models.Index(fields=["domain", "revision"], name="proc_change_domain_rev_idx")),
        migrations.AddConstraint(model_name="procurementchangejournal", constraint=models.UniqueConstraint(fields=("domain", "revision"), name="proc_change_domain_rev_uniq")),
        migrations.AddIndex(model_name="procurementoutboxevent", index=models.Index(fields=["published_at", "created_at"], name="proc_outbox_pending_idx")),
    ]
