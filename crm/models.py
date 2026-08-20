from datetime import timedelta

from django.db import models
from django.utils import timezone

from tenants.models import TenantModel, Modality


def add_working_days(start_date, n):
    """Adds n working days (Mon-Fri) to start_date. Does not account
    for public holidays - a limitation worth knowing about."""
    d = start_date
    added = 0
    while added < n:
        d = d + timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


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

    organisation = models.ForeignKey(
        Organisation, null=True, blank=True, on_delete=models.CASCADE, related_name="contacts"
    )
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

    # --- Structured Fee Proposal generator fields (cover page / fees / T&Cs) ---
    project_title = models.CharField(
        max_length=255, blank=True, help_text="e.g. 'Proposed mixed use development' - shown on the cover page.",
    )
    project_address = models.TextField(blank=True)
    enquiry_received_date = models.DateField(
        null=True, blank=True, help_text="Feeds the T&C clause referencing when the enquiry/info was received.",
    )
    is_individual_client = models.BooleanField(
        default=False, help_text="If ticked, the 'Client:' line is dropped from the cover page - use for a person, not a company.",
    )
    project_budget = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="The project construction budget referenced in the standard T&Cs (distinct from the fee amount).",
    )
    BUDGET_MODE_CHOICES = [("lump_sum", "One combined budget"), ("per_modality", "Split by modality")]
    budget_mode = models.CharField(max_length=20, choices=BUDGET_MODE_CHOICES, default="lump_sum")
    modalities = models.ManyToManyField(
        Modality, blank=True, related_name="proposals",
        help_text="Which disciplines this proposal covers - drives which Our Scope / Exclusions sections are included.",
    )
    deselected_scope_items = models.ManyToManyField(
        "FPScopeItem", blank=True, related_name="deselected_on_proposals",
        help_text="Items that WOULD be included by the selected modalities, but have been individually unticked.",
    )
    deselected_exclusion_items = models.ManyToManyField(
        "FPExclusionItem", blank=True, related_name="deselected_on_proposals",
    )
    included_term_clauses = models.ManyToManyField(
        "FPTermClause", blank=True, related_name="included_on_proposals",
        help_text="Which of the standard T&C clauses appear on this proposal.",
    )
    payment_term_override_text = models.TextField(
        blank=True, help_text="Any additional payment terms note, on top of the selected options below.",
    )
    CA_FEE_TYPE_CHOICES = [("fixed", "Fixed Fee"), ("hourly", "Hourly Rates")]
    contract_administration_included = models.BooleanField(default=False)
    ca_fee_type = models.CharField(max_length=10, choices=CA_FEE_TYPE_CHOICES, blank=True)
    ca_fixed_fee = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    novation_included = models.BooleanField(default=False)
    signing_director = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="signed_proposals",
        help_text="Whose name/signature block appears at the end of the T&Cs.",
    )

    def __str__(self):
        return self.proposal_number

    def save(self, *args, **kwargs):
        old_status = None
        if self.pk:
            old_status = Proposal.objects.filter(pk=self.pk).values_list("status", flat=True).first()
        super().save(*args, **kwargs)

        terminal_statuses = ["accepted", "declined", "lost", "withdrawn", "expired"]

        # Transitioned INTO 'issued' -> schedule the first follow-up, 3 working days out.
        if old_status != "issued" and self.status == "issued":
            ProposalFollowUp.objects.create(
                tenant=self.tenant, proposal=self, follow_up_number=1,
                due_date=add_working_days(timezone.now().date(), 3),
            )

        # Transitioned INTO a terminal status -> close any still-scheduled follow-up.
        if self.status in terminal_statuses and old_status not in terminal_statuses:
            self.follow_ups.filter(status="scheduled").update(status="closed")


class ProposalFollowUp(TenantModel):
    """
    An automatically-scheduled follow-up on a proposal that's been
    sent but not yet accepted/declined. The first is created 3
    working days after the proposal is marked 'issued'; actioning it
    with an outcome (if the proposal is still undecided) schedules
    the next one 7 working days later. Closes automatically once the
    proposal reaches a terminal status (accepted, declined, etc).
    """

    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("done", "Done"),
        ("closed", "Closed"),
    ]
    OUTCOME_CHOICES = [
        ("tender", "On tender"),
        ("with_client", "With client"),
        ("pending", "Pending"),
        ("on_hold", "On hold"),
        ("other", "Other"),
    ]

    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name="follow_ups")
    follow_up_number = models.PositiveIntegerField(default=1)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled")
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES, blank=True)
    outcome_notes = models.TextField(blank=True)
    actioned_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL)
    actioned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due_date"]

    def __str__(self):
        return f"Follow-up #{self.follow_up_number} for {self.proposal.proposal_number}"


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


# --- Fee Proposal content library ---
# Reusable, tenant-editable building blocks the Fee Proposal generator
# assembles a proposal from. Seeded once from the real template, then
# reviewed/corrected via Admin - not meant to be re-seeded blindly.

class FPScopeItem(TenantModel):
    """One selectable 'Our Scope' bullet under a modality. modality=None
    means it's a 'General' item that applies regardless of which
    disciplines are selected."""
    modality = models.ForeignKey(Modality, null=True, blank=True, on_delete=models.CASCADE, related_name="fp_scope_items")
    text = models.TextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["modality_id", "order"]

    def __str__(self):
        return self.text[:80]


class FPExclusionItem(TenantModel):
    """One selectable Exclusions bullet. Same modality=None convention
    as FPScopeItem; a modality of None with is_miscellaneous=True is
    the 'Miscellaneous' catch-all group rather than 'General'."""
    modality = models.ForeignKey(Modality, null=True, blank=True, on_delete=models.CASCADE, related_name="fp_exclusion_items")
    is_miscellaneous = models.BooleanField(default=False)
    is_contract_administration = models.BooleanField(default=False)
    is_novation = models.BooleanField(default=False)
    text = models.TextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["modality_id", "order"]

    def __str__(self):
        return self.text[:80]


class FPTermClause(TenantModel):
    """One numbered Terms & Conditions clause. `mandatory` clauses are
    always included and can't be unticked when building a proposal -
    starts False for every clause until reviewed and marked."""
    number = models.PositiveIntegerField()
    text = models.TextField()
    mandatory = models.BooleanField(default=False)

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return f"{self.number}. {self.text[:70]}"


class FPPaymentTermOption(TenantModel):
    """One of the selectable Invoice & Payment Terms options (e.g.
    '25% Deposit shall be paid prior to commencement...'). The
    percentage is editable per-proposal via Proposal.payment_term_override_text."""
    text = models.TextField()
    default_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.text[:80]


class ProposalFeeLine(TenantModel):
    """One row of the Project Fees table: a dollar amount for one
    stage, either for the whole project (modality=None, used when
    Proposal.budget_mode='lump_sum') or for one specific modality
    (used when budget_mode='per_modality')."""
    STAGE_CHOICES = [
        ("site_inspection", "Site Inspection & Report"),
        ("design_development", "Design Development"),
        ("contract_design_documentation", "Contract Design & Documentation"),
    ]
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name="fee_lines")
    stage = models.CharField(max_length=40, choices=STAGE_CHOICES)
    modality = models.ForeignKey(Modality, null=True, blank=True, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    included = models.BooleanField(default=True, help_text="Whether this stage appears on the proposal at all.")

    class Meta:
        ordering = ["stage", "modality_id"]

    def __str__(self):
        return f"{self.get_stage_display()} - {self.modality or 'Combined'}: ${self.amount}"


class ProposalPaymentTermSelection(TenantModel):
    """One payment-term option included on a proposal's schedule, e.g.
    '25% Deposit...' - a proposal typically combines several of these
    (25% + 50% + 25% etc.) rather than picking just one, with each
    percentage editable per-proposal."""
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name="payment_term_selections")
    option = models.ForeignKey(FPPaymentTermOption, on_delete=models.CASCADE)
    percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Overrides the option's default percentage for this proposal - leave blank to use the default.",
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        pct = self.percentage if self.percentage is not None else self.option.default_percentage
        return f"{pct}% - {self.option.text[:60]}"


class ProposalScopeItemOverride(TenantModel):
    """Custom wording for one FPScopeItem, on one proposal only - the
    master library text is untouched, this just overrides the display
    text when this specific proposal is generated."""
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name="scope_item_overrides")
    scope_item = models.ForeignKey(FPScopeItem, on_delete=models.CASCADE)
    custom_text = models.TextField()

    class Meta:
        unique_together = [("proposal", "scope_item")]

    def __str__(self):
        return self.custom_text[:80]


class ProposalExclusionItemOverride(TenantModel):
    """Custom wording for one FPExclusionItem, on one proposal only -
    same pattern as ProposalScopeItemOverride."""
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name="exclusion_item_overrides")
    exclusion_item = models.ForeignKey(FPExclusionItem, on_delete=models.CASCADE)
    custom_text = models.TextField()

    class Meta:
        unique_together = [("proposal", "exclusion_item")]

    def __str__(self):
        return self.custom_text[:80]
