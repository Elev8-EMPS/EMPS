from django.db import models

from tenants.models import TenantModel
from crm.models import Organisation
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
    notes = models.TextField(blank=True)

    @property
    def outstanding_amount(self):
        return self.total - self.amount_paid

    def __str__(self):
        return self.invoice_number


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
