from django.db import models

from tenants.models import TenantModel
from crm.models import Organisation, Contact, Proposal


class Project(TenantModel):
    """Blueprint section 13 - Project module."""

    STATUS_CHOICES = [
        ("setup", "Setup"),
        ("active", "Active"),
        ("on_hold", "On Hold"),
        ("at_risk", "At Risk"),
        ("completed", "Completed"),
        ("closed", "Closed"),
        ("cancelled", "Cancelled"),
        ("archived", "Archived"),
    ]

    project_number = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True)
    client_organisation = models.ForeignKey(Organisation, on_delete=models.PROTECT, related_name="projects")
    billing_organisation = models.ForeignKey(
        Organisation, null=True, blank=True, on_delete=models.SET_NULL, related_name="billed_projects",
        help_text="Who actually gets invoiced, if different from the client organisation.",
    )
    primary_contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL)
    project_manager = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="managed_projects"
    )
    director = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="directed_projects"
    )
    original_proposal = models.ForeignKey(Proposal, null=True, blank=True, on_delete=models.SET_NULL)
    original_fee = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    modalities = models.ManyToManyField("tenants.Modality", blank=True, related_name="projects")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="setup")
    start_date = models.DateField(null=True, blank=True)
    target_completion_date = models.DateField(null=True, blank=True)
    completion_date = models.DateField(null=True, blank=True)
    archive_date = models.DateField(null=True, blank=True)
    activated_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Set automatically the first time this project's status becomes Active.",
    )

    def __str__(self):
        return f"{self.project_number} - {self.name}"

    def save(self, *args, **kwargs):
        old_status = None
        if self.pk:
            old_status = Project.objects.filter(pk=self.pk).values_list("status", flat=True).first()
        if self.status == "active" and old_status != "active" and not self.activated_at:
            from django.utils import timezone
            self.activated_at = timezone.now()
        super().save(*args, **kwargs)


class Milestone(TenantModel):
    """Blueprint section 14 - Milestones and Outlook deadlines."""

    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("in_progress", "In Progress"),
        ("on_track", "On Track"),
        ("at_risk", "At Risk"),
        ("overdue", "Overdue"),
        ("ready_for_review", "Ready for Review"),
        ("ready_to_issue", "Ready to Issue"),
        ("issued", "Issued"),
        ("invoice_review_required", "Invoice Review Required"),
        ("approved_to_invoice", "Approved to Invoice"),
        ("invoiced", "Invoiced"),
        ("paid", "Paid"),
        ("closed", "Closed"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    milestone_type = models.CharField(max_length=100)
    category = models.ForeignKey(
        "tenants.DeadlineCategory", null=True, blank=True, on_delete=models.SET_NULL, related_name="milestones",
        help_text="What kind of deadline/meeting this is.",
    )
    deadline = models.DateField()
    deadline_time = models.TimeField(
        null=True, blank=True,
        help_text="Optional - if set, people involved get an in-app popup reminder around this time on the day.",
    )
    responsible_user = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="responsible_milestones"
    )
    created_by = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="created_milestones"
    )
    priority = models.CharField(max_length=20, default="normal")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="scheduled")
    forecast_issue_date = models.DateField(null=True, blank=True)
    actual_issue_date = models.DateField(null=True, blank=True)
    invoice_required = models.BooleanField(default=False)
    payment_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="What % of the project's total fee this stage represents, for the payment schedule. "
                   "Only relevant when 'Invoice required' is ticked.",
    )
    director_approval_required = models.BooleanField(default=False)
    director_approval_status = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.project.project_number} - {self.milestone_type}"

    @property
    def stage_value(self):
        """This stage's share of the project's total fee, if both the
        fee and this stage's payment percentage are known."""
        fee = self.project.original_proposal.fee_amount if self.project.original_proposal_id else None
        if fee is None or self.payment_percentage is None:
            return None
        return fee * self.payment_percentage / 100

    @property
    def invoiced_for_stage(self):
        from django.db.models import Sum
        return self.invoices.exclude(status__in=["draft", "cancelled"]).aggregate(total=Sum("total"))["total"] or 0

    @property
    def still_to_invoice(self):
        value = self.stage_value
        if value is None:
            return None
        return value - self.invoiced_for_stage


class Task(TenantModel):
    """Blueprint section 15 - Tasks, reminders and to-do module."""

    STATUS_CHOICES = [
        ("not_started", "Not Started"),
        ("in_progress", "In Progress"),
        ("waiting", "Waiting"),
        ("blocked", "Blocked"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]
    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("normal", "Normal"),
        ("high", "High"),
        ("critical", "Critical"),
    ]
    CATEGORY_CHOICES = [
        ("administration", "Administration"),
        ("accounts", "Accounts"),
        ("client_follow_up", "Client follow-up"),
        ("proposal", "Proposal"),
        ("project_delivery", "Project delivery"),
        ("authority", "Authority"),
        ("compliance", "Compliance"),
        ("internal", "Internal"),
        ("personal", "Personal"),
        ("site_visit", "Site visit"),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="normal")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="not_started")
    created_by = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="created_tasks"
    )
    owner = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    assigned_team = models.ForeignKey(
        "tenants.Team", null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks"
    )
    due_date = models.DateField(null=True, blank=True)
    reminder_at = models.DateTimeField(null=True, blank=True)
    related_project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.CASCADE, related_name="tasks"
    )
    related_milestone = models.ForeignKey(
        Milestone, null=True, blank=True, on_delete=models.CASCADE, related_name="tasks"
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.title


class TaskComment(TenantModel):
    """
    A response/comment on a to-do - never overwrites the original
    action, just adds to a visible thread. This is how someone
    responds to the assignee, the team, or the creator without
    losing the original request.
    """

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment on {self.task.title} by {self.author}"


class Document(TenantModel):
    """Blueprint section 16 - Documents module."""

    original_filename = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255, blank=True)
    category = models.CharField(max_length=100, blank=True)
    document_type = models.CharField(max_length=100, blank=True)
    revision = models.CharField(max_length=20, blank=True)
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=50, blank=True)
    uploaded_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    issued_date = models.DateField(null=True, blank=True)
    confidentiality = models.CharField(max_length=50, blank=True)
    related_project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.CASCADE, related_name="documents"
    )
    file = models.FileField(upload_to="documents/%Y/%m/", null=True, blank=True)
    checksum = models.CharField(max_length=64, blank=True)

    def __str__(self):
        return self.display_name or self.original_filename


class ProjectChecklistItem(TenantModel):
    """
    An actual checklist line on a specific project - generated from
    ChecklistItemTemplate when the project is created (or a modality
    is added later), but stores its own copy of the text so editing
    a template later doesn't rewrite history on existing projects.
    """

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="checklist_items")
    modality = models.ForeignKey(
        "tenants.Modality", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    text = models.CharField(max_length=255)
    is_done = models.BooleanField(default=False)
    done_by = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    done_at = models.DateTimeField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "text"]

    def __str__(self):
        return self.text


class ProjectStakeholder(TenantModel):
    """
    Every person tied to a project, in one place - the client
    contact, billing contact, architect, builder, consultant, etc.
    Can link to an existing Contact record, OR just capture a name/
    email for someone external who isn't in the CRM yet (very common
    for architects, builders, and other third parties).
    """

    ROLE_CHOICES = [
        ("requesting_contact", "Requesting contact"),
        ("client_contact", "Client contact"),
        ("billing_contact", "Billing contact"),
        ("architect", "Architect"),
        ("builder", "Builder"),
        ("designer", "Designer"),
        ("consultant", "Consultant"),
        ("authority_contact", "Authority contact"),
        ("site_contact", "Site contact"),
        ("other", "Other"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="stakeholders")
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default="other")
    contact = models.ForeignKey(
        "crm.Contact", null=True, blank=True, on_delete=models.SET_NULL, related_name="project_stakeholder_roles"
    )
    external_name = models.CharField(max_length=255, blank=True, help_text="If not an existing Contact.")
    external_company = models.CharField(max_length=255, blank=True)
    external_email = models.EmailField(blank=True)
    external_phone = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    is_archived = models.BooleanField(default=False)

    def display_name(self):
        if self.contact:
            return f"{self.contact.first_name} {self.contact.last_name}"
        return self.external_name or "(unnamed)"

    def __str__(self):
        return f"{self.get_role_display()}: {self.display_name()}"


class ProjectScopeAddition(TenantModel):
    """
    Tracks each modality's inclusion on a project. Modalities picked
    at project creation are 'original scope' - part of the base
    project code, no suffix. A modality added later gets its own
    suffixed code (e.g. PJ-2024-001-E) and its own budget line,
    since it represents extra scope beyond the original fee proposal.
    """

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="scope_additions")
    modality = models.ForeignKey("tenants.Modality", on_delete=models.CASCADE, related_name="+")
    is_original_scope = models.BooleanField(default=True)
    suffix = models.CharField(max_length=10, blank=True)
    budget_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    added_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("project", "modality")]
        ordering = ["is_original_scope", "suffix"]

    @property
    def full_code(self):
        if self.is_original_scope or not self.suffix:
            return self.project.project_number
        return f"{self.project.project_number}-{self.suffix}"

    def __str__(self):
        return f"{self.full_code} ({self.modality.name})"
