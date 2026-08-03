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

    user = models.OneToOneField("auth.User", on_delete=models.CASCADE, related_name="profile")
    tenant = models.ForeignKey(Tenant, null=True, blank=True, on_delete=models.SET_NULL, related_name="users")

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
