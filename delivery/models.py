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

    def __str__(self):
        return f"{self.project_number} - {self.name}"


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
    deadline = models.DateField()
    responsible_user = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="responsible_milestones"
    )
    priority = models.CharField(max_length=20, default="normal")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="scheduled")
    forecast_issue_date = models.DateField(null=True, blank=True)
    actual_issue_date = models.DateField(null=True, blank=True)
    invoice_required = models.BooleanField(default=False)
    director_approval_required = models.BooleanField(default=False)
    director_approval_status = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.project.project_number} - {self.milestone_type}"


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
