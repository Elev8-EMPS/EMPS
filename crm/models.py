from django.db import models

from tenants.models import TenantModel


class Organisation(TenantModel):
    """Blueprint section 9 - Organisation and CRM module."""

    CLIENT_STATUS_CHOICES = [
        ("prospect", "Prospect"),
        ("active", "Active"),
        ("inactive", "Inactive"),
    ]

    legal_name = models.CharField(max_length=255)
    trading_name = models.CharField(max_length=255, blank=True)
    registration_number = models.CharField(max_length=100, blank=True)
    organisation_type = models.CharField(max_length=100, blank=True)
    industry = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    client_status = models.CharField(max_length=20, choices=CLIENT_STATUS_CHOICES, default="prospect")
    vip_level = models.CharField(max_length=50, blank=True)
    relationship_owner = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="owned_organisations"
    )
    client_since = models.DateField(null=True, blank=True)
    last_contact = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.legal_name


class Contact(TenantModel):
    """Blueprint section 10 - Contacts module."""

    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name="contacts")
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    job_title = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    mobile = models.CharField(max_length=50, blank=True)
    office_phone = models.CharField(max_length=50, blank=True)
    is_proposal_recipient = models.BooleanField(default=False)
    is_invoice_recipient = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    last_contact = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Enquiry(TenantModel):
    """Blueprint section 11 - Enquiries module."""

    STATUS_CHOICES = [
        ("new", "New"),
        ("under_review", "Under Review"),
        ("clarification_required", "Clarification Required"),
        ("ready_to_price", "Ready to Price"),
        ("proposal_required", "Proposal Required"),
        ("proposal_created", "Proposal Created"),
        ("declined", "Declined"),
        ("closed", "Closed"),
    ]

    enquiry_number = models.CharField(max_length=50, unique=True)
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name="enquiries")
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL)
    project_address = models.TextField(blank=True)
    description = models.TextField(blank=True)
    services_required = models.TextField(blank=True)
    source = models.CharField(max_length=100, blank=True)
    date_received = models.DateField()
    proposal_due_date = models.DateField(null=True, blank=True)
    responsible_director = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="director_enquiries"
    )
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="new")
    next_action = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.enquiry_number


class Proposal(TenantModel):
    """Blueprint section 12 - Fee Proposal module."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("internal_review", "Internal Review"),
        ("director_review", "Director Review"),
        ("approved", "Approved"),
        ("issued", "Issued"),
        ("follow_up_due", "Follow-up Due"),
        ("revised", "Revised"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
        ("lost", "Lost"),
        ("withdrawn", "Withdrawn"),
        ("expired", "Expired"),
    ]

    proposal_number = models.CharField(max_length=50, unique=True)
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name="proposals")
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL)
    enquiry = models.ForeignKey(Enquiry, null=True, blank=True, on_delete=models.SET_NULL, related_name="proposals")
    scope = models.TextField(blank=True)
    fee_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    exclusions = models.TextField(blank=True)
    assumptions = models.TextField(blank=True)
    validity_period_days = models.PositiveIntegerField(default=30)
    version = models.PositiveIntegerField(default=1)
    issue_date = models.DateField(null=True, blank=True)
    follow_up_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    director_approved_by = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="approved_proposals"
    )

    def __str__(self):
        return self.proposal_number


class Communication(TenantModel):
    """
    Blueprint section 17 - Email and communications module.
    Manually logged for now (emails and calls); designed so that a
    future Outlook/Gmail integration can populate the same fields
    automatically instead of replacing this model.
    """

    TYPE_CHOICES = [
        ("email", "Email"),
        ("phone_call", "Phone call"),
        ("meeting", "Meeting"),
        ("note", "Note"),
    ]
    DIRECTION_CHOICES = [
        ("outgoing", "Outgoing"),
        ("incoming", "Incoming"),
    ]

    communication_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="note")
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES, blank=True)
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField(blank=True)
    organisation = models.ForeignKey(
        Organisation, null=True, blank=True, on_delete=models.SET_NULL, related_name="communications"
    )
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL)
    related_project = models.ForeignKey(
        "delivery.Project", null=True, blank=True, on_delete=models.SET_NULL, related_name="communications"
    )
    sender = models.CharField(max_length=255, blank=True)
    recipients = models.CharField(max_length=500, blank=True)
    occurred_at = models.DateTimeField()
    logged_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]

    def __str__(self):
        return self.subject or f"{self.get_communication_type_display()} on {self.occurred_at:%Y-%m-%d}"
