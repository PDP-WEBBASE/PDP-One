from django.contrib import admin
from .models import AnalysisReport, AuditEvent, Contract, PaymentReceipt, Receivable

admin.site.register(Contract)
admin.site.register(AnalysisReport)
admin.site.register(AuditEvent)
admin.site.register(Receivable)
admin.site.register(PaymentReceipt)
