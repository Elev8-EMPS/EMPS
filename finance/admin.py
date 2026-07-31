from django.contrib import admin

from tenants.admin_mixins import ExportCsvMixin
from .models import Invoice, Payment


@admin.register(Invoice)
class InvoiceAdmin(ExportCsvMixin, admin.ModelAdmin):
    list_display = ("invoice_number", "project", "organisation", "status", "total", "amount_paid", "outstanding_amount", "due_date", "tenant")
    list_filter = ("status", "tenant")
    search_fields = ("invoice_number", "organisation__legal_name", "project__project_number", "po_number")
    date_hierarchy = "due_date"


@admin.register(Payment)
class PaymentAdmin(ExportCsvMixin, admin.ModelAdmin):
    list_display = ("invoice", "payment_date", "amount", "method", "reference", "tenant")
    list_filter = ("method", "tenant")
    search_fields = ("invoice__invoice_number", "reference")
    date_hierarchy = "payment_date"
