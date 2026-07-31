from django.contrib import admin

from .models import Invoice, Payment


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "project", "organisation", "status", "total", "outstanding_amount", "tenant")
    list_filter = ("status", "tenant")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("invoice", "payment_date", "amount", "method", "tenant")
    list_filter = ("tenant",)
