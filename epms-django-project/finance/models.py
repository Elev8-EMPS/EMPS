from django.db import models
from django.utils import timezone

from tenants.models import TenantModel
from crm.models import Organisation, add_working_days
from delivery.models import Project, Milestone


class Invoice(TenantModel):
    """Blueprint section 21 - Invoices, payments and debtors."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("awaiting_approval", "Awaiting Approval"),
        ("approved", "Approved"),
        ("issued", "Issued"),
        ("part_paid", "Part Paid"),
        ("paid", "Paid"),
        ("overdue", "Overdue"),
        ("disputed", "Disputed"),
        ("cancelled", "Cancelled"),
        ("written_off", "Written Off"),
    ]

    invoice_number = models.CharField(max_length=50, unique=True)
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="invoices")
    organisation = models.ForeignKey(Organisation, on_delete=models.PROTECT, related_name="invoices")
    milestone = models.ForeignKey(
        Milestone, null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices"
    )
    po_number = models.CharField(max_length=100, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    amount_excl_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    accounting_reference = models.CharField(max_length=100, blank=True)  # Xero/MYOB reference
    xero_reminders_sent = models.PositiveIntegerField(default=0)
    statement_sent = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    @property
    def outstanding_amount(self):
        return self.total - self.amount_paid

    def __str__(self):
        return self.invoice_number

    def save(self, *args, **kwargs):
        old_status = None
        if self.pk:
            old_status = Invoice.objects.filter(pk=self.pk).values_list("status", flat=True).first()
        super().save(*args, **kwargs)

        closed_statuses = ["paid", "cancelled", "written_off"]

        if old_status != "issued" and self.status == "issued":
            InvoiceFollowUp.objects.create(
                tenant=self.tenant, invoice=self, follow_up_number=1,
                due_date=add_working_days(timezone.now().date(), 7),
            )

        if self.status in closed_statuses and old_status not in closed_statuses:
            self.follow_ups.filter(status="scheduled").update(status="closed")


class InvoiceFollowUp(TenantModel):
    """
    An automatically-scheduled payment follow-up: the first is
    created 7 working days after an invoice is marked 'issued'.
    Actioning it (if still unpaid) schedules the next one 7 working
    days later. Closes automatically once the invoice is paid,
    cancelled, or written off.
    """

    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("done", "Done"),
        ("closed", "Closed"),
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="follow_ups")
    follow_up_number = models.PositiveIntegerField(default=1)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled")
    outcome_notes = models.TextField(blank=True)
    actioned_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL)
    actioned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due_date"]

    def __str__(self):
        return f"Follow-up #{self.follow_up_number} for {self.invoice.invoice_number}"


class Payment(TenantModel):
    """Payment received against an invoice."""

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    payment_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=50, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    accounting_transaction_id = models.CharField(max_length=100, blank=True)  # Stripe/Xero txn id

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.amount}"
