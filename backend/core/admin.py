from django.contrib import admin
from .models import AnalysisReport, AuditEvent, Contract

admin.site.register(Contract)
admin.site.register(AnalysisReport)
admin.site.register(AuditEvent)

