from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from tenants.models import TenantModel


class CalendarEventType(TenantModel):
    """Tenant-configurable visual definition for a calendar event category."""
    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=100)
    colour = models.CharField(max_length=20, default="#2563eb")
    text_colour = models.CharField(max_length=20, default="#ffffff")
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "code"], name="uniq_calendar_event_type_tenant_code")]

    def __str__(self):
        return self.name


class LeaveType(TenantModel):
    """Configurable leave category (annual, sick, WFH-related leave, etc.)."""
    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=100)
    colour = models.CharField(max_length=20, default="#7c3aed")
    counts_toward_leave = models.BooleanField(default=True)
    requires_reason = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "code"], name="uniq_leave_type_tenant_code")]

    def __str__(self):
        return self.name


class PublicHoliday(TenantModel):
    """Tenant-configurable public holiday. Leave/WFH calculations exclude these dates."""
    date = models.DateField()
    name = models.CharField(max_length=150)

    class Meta:
        ordering = ["date"]
        constraints = [models.UniqueConstraint(fields=["tenant", "date"], name="uniq_public_holiday_tenant_date")]

    def __str__(self):
        return f"{self.date} — {self.name}"


class LeaveRequest(TenantModel):
    """Employee leave application and its current approval state."""
    PART_CHOICES = [("full", "Full day"), ("am", "Morning (half day)"), ("pm", "Afternoon (half day)")]
    STATUS_CHOICES = [
        ("pending", "Pending approval"),
        ("approved", "Approved"),
        ("declined", "Declined"),
        ("cancelled", "Cancelled"),
    ]

    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="leave_requests")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="requests")
    start_date = models.DateField()
    end_date = models.DateField()
    start_part = models.CharField(max_length=4, choices=PART_CHOICES, default="full")
    end_part = models.CharField(max_length=4, choices=PART_CHOICES, default="full")
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    current_approver = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pending_leave_approvals",
    )
    submitted_at = models.DateTimeField(default=timezone.now)
    decided_at = models.DateTimeField(null=True, blank=True)
    decline_reason = models.TextField(blank=True)
    last_reminder_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["tenant", "status", "start_date"]),
            models.Index(fields=["tenant", "current_approver", "status"]),
        ]

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError("The end date cannot be before the start date.")
        if self.start_date == self.end_date and self.end_part != "full":
            if self.start_part != self.end_part:
                raise ValidationError("For a single-day half-day request, choose either morning or afternoon.")
            if self.start_part == "full":
                raise ValidationError("A full day does not need a half-day selection.")
        if self.leave_type_id and self.reason == "" and self.leave_type.requires_reason:
            raise ValidationError({"reason": "A reason is required for this leave type."})

    @property
    def working_days(self):
        if not self.start_date or not self.end_date:
            return 0
        holidays = set(PublicHoliday.objects.filter(tenant=self.tenant, date__range=[self.start_date, self.end_date]).values_list("date", flat=True))
        total = 0
        current = self.start_date
        while current <= self.end_date:
            if current.weekday() < 5 and current not in holidays:
                total += 1
            current += timedelta(days=1)
        if total == 0:
            return 0
        if self.start_date == self.end_date:
            return 0.5 if self.start_part in {"am", "pm"} else 1
        if self.start_part in {"am", "pm"}:
            total -= 0.5
        if self.end_part in {"am", "pm"}:
            total -= 0.5
        return max(total, 0)

    @property
    def is_half_day(self):
        return self.working_days % 1 != 0

    def __str__(self):
        return f"{self.requester.get_full_name() or self.requester.username} - {self.leave_type.name}"


class LeaveApproval(TenantModel):
    """Immutable-ish approval history; the current request status is a convenience."""
    ACTION_CHOICES = [("approved", "Approved"), ("declined", "Declined"), ("cancelled", "Cancelled"), ("reassigned", "Reassigned")]

    request = models.ForeignKey(LeaveRequest, on_delete=models.CASCADE, related_name="approval_history")
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="leave_approval_actions")
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    reason = models.TextField(blank=True)
    acted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-acted_at"]


class WFHSchedule(TenantModel):
    """Recurring weekly WFH pattern for one employee."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wfh_schedule")
    monday = models.BooleanField(default=False)
    tuesday = models.BooleanField(default=False)
    wednesday = models.BooleanField(default=False)
    thursday = models.BooleanField(default=False)
    friday = models.BooleanField(default=False)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)

    def weekday_enabled(self, weekday):
        return [self.monday, self.tuesday, self.wednesday, self.thursday, self.friday][weekday]

    def clean(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError("WFH effective-to cannot be before effective-from.")

    def __str__(self):
        return f"WFH - {self.user.get_full_name() or self.user.username}"


class WFHChangeRequest(TenantModel):
    """One-off WFH addition/removal/swap; it does not rewrite the recurring pattern."""
    TYPE_CHOICES = [("swap", "Swap WFH day"), ("add", "Additional WFH day"), ("remove", "Remove WFH day")]
    STATUS_CHOICES = [("pending", "Pending approval"), ("approved", "Approved"), ("declined", "Declined"), ("cancelled", "Cancelled")]

    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="wfh_change_requests")
    change_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default="swap")
    original_date = models.DateField(null=True, blank=True)
    requested_date = models.DateField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    current_approver = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pending_wfh_approvals",
    )
    submitted_at = models.DateTimeField(default=timezone.now)
    decided_at = models.DateTimeField(null=True, blank=True)
    decline_reason = models.TextField(blank=True)
    last_reminder_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]
        indexes = [models.Index(fields=["tenant", "status", "requested_date"])]

    def clean(self):
        if self.change_type == "swap" and not self.original_date:
            raise ValidationError({"original_date": "A WFH swap needs the day being swapped."})
        if self.change_type == "swap" and self.original_date == self.requested_date:
            raise ValidationError("The original and requested WFH dates must be different.")

    def __str__(self):
        return f"{self.requester.get_full_name() or self.requester.username} - {self.get_change_type_display()}"


class CalendarSettings(TenantModel):
    """Tenant-wide calendar/approval settings. Configuration UI can be expanded later."""
    reminder_after_business_days = models.PositiveIntegerField(default=2)
    escalation_after_business_days = models.PositiveIntegerField(default=3)
    allow_company_admin_override = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant"], name="uniq_calendar_settings_tenant")]


class CalendarPreference(TenantModel):
    """Saved per-user calendar visibility and presentation choices."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="calendar_preference")
    show_leave = models.BooleanField(default=True)
    show_wfh = models.BooleanField(default=True)
    show_deadlines = models.BooleanField(default=True)
    show_tasks = models.BooleanField(default=True)
    show_followups = models.BooleanField(default=True)
    show_projects = models.BooleanField(default=True)
    show_fee_proposals = models.BooleanField(default=False)
    show_company_wide = models.BooleanField(default=False)

    def __str__(self):
        return f"Calendar preferences - {self.user.username}"
