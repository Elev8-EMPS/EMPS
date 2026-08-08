import uuid

from django.db import models


class Tenant(models.Model):
    """
    One row per company using EPMS.
    Only one row exists today - the platform is built to support
    more without a rewrite when that becomes real.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    DASHBOARD_VISIBILITY_CHOICES = [
        ("restricted", "Restricted - people without Fee Proposal access see nothing proposal-related"),
        ("responsible_for", "Responsible for - they also see enquiries/proposals/archived projects "
                             "they're personally tied to, without fee amounts"),
    ]
    dashboard_visibility = models.CharField(
        max_length=20, choices=DASHBOARD_VISIBILITY_CHOICES, default="restricted",
        help_text="Controls what people WITHOUT Fee Proposal access see on their Command Centre.",
    )

    def __str__(self):
        return self.name


class TenantModel(models.Model):
    """
    Abstract base class - every business record inherits from this.
    Every query against a tenant-owned table MUST filter by tenant.
    This is what keeps one company's data from ever leaking into another's.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserProfile(models.Model):
    """
    Links a Django user to the tenant they belong to.
    Superusers can leave this blank/no tenant - they see everything.
    A regular user with a tenant set here gets that tenant
    auto-filled (and hidden) on every form, and only ever sees
    that tenant's records.
    """

    ROLE_CHOICES = [
        ("company_admin", "Company Administrator"),
        ("director", "Director"),
        ("project_manager", "Project Manager"),
        ("engineer", "Engineer"),
        ("administration", "Administration"),
        ("accounts", "Accounts"),
        ("external_consultant", "External Consultant"),
        ("client_user", "Client User"),
        ("read_only", "Read Only"),
    ]

    user = models.OneToOneField("auth.User", on_delete=models.CASCADE, related_name="profile")
    tenant = models.ForeignKey(Tenant, null=True, blank=True, on_delete=models.SET_NULL, related_name="users")
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, blank=True)
    can_manage_proposals = models.BooleanField(
        default=False,
        help_text="Can see and work with Fee Proposals - fee amounts, follow-ups, and (in future) "
                   "proposal letters/templates. Company Administrators and Directors always have "
                   "this regardless of this checkbox; tick it for anyone else who should be able "
                   "to create or view proposals.",
    )
    date_of_birth = models.DateField(null=True, blank=True)
    date_started = models.DateField(
        null=True, blank=True, help_text="Date they started with the company."
    )
    phone = models.CharField(max_length=50, blank=True)
    direct_manager = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="direct_reports",
        help_text="Leave requests from this person are routed to their direct manager for approval.",
    )
    modalities = models.ManyToManyField(
        "Modality", blank=True, related_name="user_profiles",
        help_text="Disciplines this person personally works in - independent of their team's modalities.",
    )

    def __str__(self):
        return f"{self.user.username} -> {self.tenant.name if self.tenant else 'no tenant'}"


class Team(models.Model):
    """
    A group of users within a tenant (e.g. 'Structural', 'Accounts').
    A user can belong to any number of teams. Used to assign a
    to-do to a whole team rather than one specific person - it then
    shows up on every member's to-do list.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="teams")
    name = models.CharField(max_length=100)
    members = models.ManyToManyField("auth.User", related_name="teams", blank=True)
    modalities = models.ManyToManyField(
        "Modality", related_name="teams", blank=True,
        help_text="Which disciplines this team covers - used to show them their relevant active projects.",
    )

    def __str__(self):
        return self.name


class Modality(models.Model):
    """
    A discipline/service type a project can involve - e.g.
    'Hydraulics', 'Structural', 'Civil'. Admin-configurable per
    tenant. Selecting a modality on a project pulls in that
    modality's 'always included' checklist items automatically.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="modalities")
    name = models.CharField(max_length=100)
    code = models.CharField(
        max_length=5, blank=True,
        help_text="Short suffix used when this discipline is added to a project after it's already "
                   "created, e.g. 'E' for Electrical -> PJ-2024-001-E.",
    )

    def __str__(self):
        return self.name


class ChecklistItemTemplate(models.Model):
    """
    A checklist item definition. If modality is blank, it's a
    universal item added to every project regardless of modality
    (e.g. 'Site photos taken'). If modality is set and
    always_included is True, it's automatically added whenever that
    modality is selected on a project (e.g. Hydraulics -> 'Sewer
    application', 'Pressure and flow application'). If
    always_included is False, it's available to add but not forced.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="checklist_templates")
    modality = models.ForeignKey(
        Modality, null=True, blank=True, on_delete=models.CASCADE, related_name="checklist_templates"
    )
    text = models.CharField(max_length=255)
    always_included = models.BooleanField(
        default=True,
        help_text="If checked, this item is added automatically whenever its modality is selected "
                   "(or to every project, if no modality is set). If unchecked, it's available to add manually.",
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "text"]

    def __str__(self):
        return self.text
