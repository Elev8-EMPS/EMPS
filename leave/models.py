from django.db import models

from tenants.models import TenantModel


WEEKDAY_CHOICES = [
    (0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"),
    (4, "Friday"), (5, "Saturday"), (6, "Sunday"),
]


class LeaveRequest(TenantModel):
    """
    A request for time off, or to swap/add/remove a WFH day. All five
    kinds go through the same pending -> approved/declined workflow,
    approved by the requester's Line Manager or any Director/Company
    Administrator (see tenants.utils.can_approve_leave).
    """

    LEAVE_TYPE_CHOICES = [
        ("annual", "Annual Leave"),
        ("sick", "Sick Leave"),
        ("wfh_swap", "WFH Day Swap"),
        ("wfh_standing", "Standing WFH Day Change"),
        ("other", "Other"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("declined", "Declined"),
        ("cancelled", "Cancelled"),
    ]
    STANDING_ACTION_CHOICES = [("add", "Add"), ("remove", "Remove")]

    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPE_CHOICES)

    start_date = models.DateField()
    end_date = models.DateField()

    reason = models.TextField(
        blank=True, help_text="The purpose of the request. Required for 'Other'.",
    )

    # Only used for wfh_swap - the day they'd normally be in office/WFH
    # that they're moving out of.
    swap_original_date = models.DateField(null=True, blank=True)

    # Only used for wfh_standing - which weekday, and whether this is
    # adding it to, or removing it from, their recurring pattern.
    standing_weekday = models.IntegerField(null=True, blank=True, choices=WEEKDAY_CHOICES)
    standing_action = models.CharField(max_length=10, choices=STANDING_ACTION_CHOICES, blank=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")

    # Visible only to the requester and whoever is allowed to approve
    # their leave - see can_view_decline_reason in utils.
    decline_reason = models.TextField(blank=True)

    decided_by = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="leave_decisions",
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    # The to-do created for the approver, so it can be marked done
    # once they act on the request.
    notification_task = models.ForeignKey(
        "delivery.Task", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.user.username} - {self.get_leave_type_display()} ({self.start_date} to {self.end_date})"

    @property
    def is_wfh_related(self):
        return self.leave_type in ("wfh_swap", "wfh_standing")


class WFHDay(TenantModel):
    """An approved, standing recurring WFH day for a user. Created or
    removed automatically when a 'wfh_standing' LeaveRequest is
    approved - never edited directly."""

    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="wfh_days")
    weekday = models.IntegerField(choices=WEEKDAY_CHOICES)

    class Meta:
        unique_together = [("user", "weekday")]
        ordering = ["weekday"]

    def __str__(self):
        return f"{self.user.username} - {self.get_weekday_display()}"


class CalendarScope(models.Model):
    """A Director/Company Admin's personal filter on the team calendar
    - which teams to include. No teams selected (the default) means
    'show the whole tenancy' - this only ever narrows what they see,
    it never grants access beyond what their role already has."""

    user = models.OneToOneField("auth.User", on_delete=models.CASCADE, related_name="calendar_scope")
    included_teams = models.ManyToManyField("tenants.Team", blank=True, related_name="+")

    def __str__(self):
        return f"Calendar scope for {self.user.username}"
