from datetime import date, timedelta

from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from delivery.models import Milestone, Project, Task
from tenants.models import Team, Tenant
from tenants.utils import get_user_role, get_user_tenant

from .models import CalendarEventType, CalendarPreference, CalendarSettings, LeaveRequest, LeaveType, PublicHoliday, WFHChangeRequest, WFHSchedule

MANAGEMENT_ROLES = {"company_admin", "director", "project_manager"}
APPROVER_ROLES = {"company_admin", "director", "project_manager"}

DEFAULT_EVENT_TYPES = [
    ("leave", "Leave", "#7c3aed"),
    ("wfh", "WFH", "#059669"),
    ("deadline", "Project deadline", "#2563eb"),
    ("task", "Task", "#d97706"),
    ("followup", "Follow-up", "#0891b2"),
    ("approval", "Approval required", "#dc2626"),
]

DEFAULT_LEAVE_TYPES = [
    ("annual", "Annual Leave", "#7c3aed", True),
    ("personal", "Personal / Carer's Leave", "#db2777", True),
    ("sick", "Sick Leave", "#dc2626", False),
    ("long_service", "Long Service Leave", "#4f46e5", True),
    ("unpaid", "Unpaid Leave", "#6b7280", True),
    ("parental", "Parental Leave", "#0f766e", True),
    ("bereavement", "Bereavement / Compassionate Leave", "#475569", True),
    ("family_domestic_violence", "Family & Domestic Violence Leave", "#be123c", True),
    ("community_service", "Community Service / Jury Duty", "#0369a1", True),
    ("study", "Study / Professional Development Leave", "#0284c7", True),
    ("purchased", "Purchased / Additional Leave", "#4338ca", True),
    ("other", "Other Leave", "#64748b", False),
]


def ensure_calendar_defaults(tenant):
    """Create defaults idempotently; admins can then customise them."""
    for code, name, colour in DEFAULT_EVENT_TYPES:
        CalendarEventType.objects.get_or_create(
            tenant=tenant, code=code,
            defaults={"name": name, "colour": colour, "text_colour": "#ffffff"},
        )
    for code, name, colour, counts in DEFAULT_LEAVE_TYPES:
        LeaveType.objects.get_or_create(
            tenant=tenant, code=code,
            defaults={"name": name, "colour": colour, "counts_toward_leave": counts},
        )


def get_or_create_preference(user, tenant):
    preference, created = CalendarPreference.objects.get_or_create(
        user=user, tenant=tenant,
        defaults={"show_company_wide": get_user_role(user) in {"company_admin", "director"}},
    )
    return preference


def manager_is_available(manager, start_date, end_date):
    if not manager or not manager.is_active:
        return False
    leave = LeaveRequest.objects.filter(
        tenant=manager.profile.tenant,
        requester=manager,
        status="approved",
        start_date__lte=end_date,
        end_date__gte=start_date,
    ).exists()
    return not leave


def find_approver(user, start_date, end_date):
    """Resolve the normal approver deterministically.

    Direct manager wins. If unavailable, an active director is selected.
    If no director exists, a company administrator is selected. The selected
    approver is stored on the request, so later organisational changes do not
    silently change an already-submitted approval route.
    """
    profile = getattr(user, "profile", None)
    tenant = profile.tenant if profile else None
    if not tenant:
        return None
    manager = profile.direct_manager if profile else None
    if manager and getattr(getattr(manager, "profile", None), "tenant_id", None) == tenant.id:
        if manager_is_available(manager, start_date, end_date):
            return manager
    director = User.objects.filter(
        profile__tenant=tenant, profile__role="director", is_active=True,
    ).order_by("username").first()
    if director:
        return director
    return User.objects.filter(
        profile__tenant=tenant, profile__role="company_admin", is_active=True,
    ).order_by("username").first()


def user_can_access_management(user):
    return user.is_superuser or get_user_role(user) in MANAGEMENT_ROLES


def user_can_approve(user, request_obj):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    role = get_user_role(user)
    if role not in APPROVER_ROLES:
        return False
    profile = getattr(user, "profile", None)
    tenant = profile.tenant if profile else None
    if not tenant or request_obj.tenant_id != tenant.id:
        return False
    if role == "company_admin":
        return get_calendar_settings(request_obj.tenant).allow_company_admin_override or request_obj.current_approver_id == user.id
    return request_obj.current_approver_id == user.id


def visible_users(user, tenant):
    role = get_user_role(user)
    qs = User.objects.filter(profile__tenant=tenant, is_active=True).select_related("profile").distinct()
    if role in {"company_admin", "director"} or user.is_superuser:
        return qs
    if role == "project_manager":
        team_ids = Team.objects.filter(tenant=tenant, manager=user).values_list("id", flat=True)
        member_team_ids = user.teams.filter(tenant=tenant).values_list("id", flat=True)
        return qs.filter(Q(id=user.id) | Q(profile__direct_manager=user) | Q(teams__id__in=team_ids) | Q(teams__id__in=member_team_ids)).distinct()
    member_team_ids = user.teams.filter(tenant=tenant).values_list("id", flat=True)
    return qs.filter(Q(id=user.id) | Q(teams__id__in=member_team_ids)).distinct()


def visible_projects(user, tenant):
    role = get_user_role(user)
    qs = Project.objects.filter(tenant=tenant, status__in=["setup", "active", "on_hold", "at_risk"]).prefetch_related("modalities").select_related("project_manager", "director", "client_organisation")
    if user.is_superuser:
        return qs
    if role in {"company_admin", "director"}:
        preference = CalendarPreference.objects.filter(user=user, tenant=tenant).first()
        if preference is None or preference.show_company_wide:
            return qs
        team_modalities = Team.objects.filter(tenant=tenant, manager=user).values_list("modalities__id", flat=True)
        return qs.filter(Q(project_manager=user) | Q(director=user) | Q(modalities__id__in=team_modalities)).distinct()
    team_modalities = user.teams.filter(tenant=tenant).values_list("modalities__id", flat=True)
    if role == "project_manager":
        team_modalities = list(team_modalities) + list(Team.objects.filter(tenant=tenant, manager=user).values_list("modalities__id", flat=True))
    direct_modalities = getattr(getattr(user, "profile", None), "modalities", Team.objects.none()).values_list("id", flat=True)
    return qs.filter(
        Q(project_manager=user) | Q(director=user) | Q(modalities__id__in=team_modalities) |
        Q(modalities__id__in=direct_modalities) | Q(tasks__owner=user) | Q(tasks__assigned_team__members=user)
    ).distinct()



def visible_tasks(user, tenant):
    """Tasks visible to the user according to their project/team scope."""
    role = get_user_role(user)
    qs = Task.objects.filter(tenant=tenant)
    if user.is_superuser:
        return qs
    if role in {"company_admin", "director"}:
        preference = CalendarPreference.objects.filter(user=user, tenant=tenant).first()
        if preference is None or preference.show_company_wide:
            return qs
    return qs.filter(
        Q(owner=user) | Q(assigned_team__members=user) | Q(related_project__in=visible_projects(user, tenant)) | Q(created_by=user)
    ).distinct()

def visible_leave_requests(user, tenant, start_date=None, end_date=None):
    qs = LeaveRequest.objects.filter(tenant=tenant).select_related("requester", "requester__profile", "leave_type", "current_approver")
    if start_date:
        qs = qs.filter(end_date__gte=start_date)
    if end_date:
        qs = qs.filter(start_date__lte=end_date)
    if user.is_superuser:
        return qs
    return qs.filter(requester_id__in=visible_users(user, tenant).values_list("id", flat=True))


def visible_wfh_requests(user, tenant, start_date=None, end_date=None):
    qs = WFHChangeRequest.objects.filter(tenant=tenant).select_related("requester", "requester__profile", "current_approver")
    if start_date:
        qs = qs.filter(requested_date__gte=start_date)
    if end_date:
        qs = qs.filter(requested_date__lte=end_date)
    if user.is_superuser:
        return qs
    return qs.filter(requester_id__in=visible_users(user, tenant).values_list("id", flat=True))


def working_days_between(start_date, end_date):
    count = 0
    current = start_date
    while current <= end_date:
        if current.weekday() < 5 and not PublicHoliday.objects.filter(tenant=tenant, date=current).exists():
            count += 1
        current += timedelta(days=1)
    return count


def leave_conflicts(request_obj):
    """Approved/pending overlap check; cancelled/declined records do not block."""
    return LeaveRequest.objects.filter(
        tenant=request_obj.tenant,
        requester=request_obj.requester,
        status__in=["pending", "approved"],
        start_date__lte=request_obj.end_date,
        end_date__gte=request_obj.start_date,
    ).exclude(pk=request_obj.pk).exists()



def validate_wfh_change(obj):
    """Validate a one-off WFH exception against recurring WFH, leave and duplicates."""
    schedule = getattr(obj.requester, "wfh_schedule", None)
    if obj.requested_date.weekday() > 4:
        raise ValueError("WFH changes must use a Monday-Friday date.")
    if obj.original_date and obj.original_date.weekday() > 4:
        raise ValueError("The original WFH date must be Monday-Friday.")
    if LeaveRequest.objects.filter(
        tenant=obj.tenant, requester=obj.requester, status="approved",
        start_date__lte=obj.requested_date, end_date__gte=obj.requested_date,
    ).exists():
        raise ValueError("The requested WFH date falls during approved leave.")
    if WFHChangeRequest.objects.filter(
        tenant=obj.tenant, requester=obj.requester, status__in=["pending", "approved"],
        requested_date=obj.requested_date,
    ).exclude(pk=obj.pk).exists():
        raise ValueError("There is already a pending or approved WFH change for that date.")
    recurring_requested = bool(schedule and schedule.weekday_enabled(obj.requested_date.weekday()))
    if obj.change_type == "add" and recurring_requested:
        raise ValueError("That date is already a recurring WFH day.")
    if obj.change_type == "remove" and obj.original_date is None and not recurring_requested:
        raise ValueError("That date is not a recurring WFH day.")
    if obj.change_type == "swap":
        if not schedule or not schedule.weekday_enabled(obj.original_date.weekday()):
            raise ValueError("The original date is not in the employee's recurring WFH schedule.")
        if recurring_requested:
            raise ValueError("The requested date is already a recurring WFH day.")


def get_calendar_settings(tenant):
    settings, _ = CalendarSettings.objects.get_or_create(
        tenant=tenant,
        defaults={
            "reminder_after_business_days": tenant.leave_approval_reminder_days,
            "escalation_after_business_days": tenant.leave_approval_escalation_days,
        },
    )
    return settings


def business_days_since(start, end):
    if not start or not end or end <= start:
        return 0
    count = 0
    current = start.date() if hasattr(start, "date") else start
    finish = end.date() if hasattr(end, "date") else end
    while current < finish:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def process_approval_escalations(tenant):
    """Raise in-app admin tasks for stale approvals. Safe to call repeatedly."""
    from delivery.models import Task
    settings = get_calendar_settings(tenant)
    now = timezone.now()
    admin_users = User.objects.filter(profile__tenant=tenant, profile__role="company_admin", is_active=True)
    if not admin_users.exists():
        return 0
    created = 0
    for obj in list(LeaveRequest.objects.filter(tenant=tenant, status="pending").select_related("requester", "current_approver")) + list(WFHChangeRequest.objects.filter(tenant=tenant, status="pending").select_related("requester", "current_approver")):
        age = business_days_since(obj.submitted_at, now)
        if age >= settings.escalation_after_business_days:
            for admin in admin_users:
                marker = f"Approval escalation #{obj.pk}"
                if not Task.objects.filter(tenant=tenant, owner=admin, title__startswith=marker, status__in=["not_started", "in_progress", "waiting"]).exists():
                    Task.objects.create(tenant=tenant, title=marker, description=f"Approval for {obj.requester.get_full_name() or obj.requester.username} has been pending for {age} business days and needs follow-up.", category="internal", priority="high", owner=admin, due_date=timezone.localdate())
                    created += 1
            if not obj.escalated_at:
                obj.escalated_at = now
                obj.save(update_fields=["escalated_at", "updated_at"])
        elif age >= settings.reminder_after_business_days:
            if not obj.last_reminder_at or (now - obj.last_reminder_at).days >= 1:
                approver = obj.current_approver
                if approver and not Task.objects.filter(tenant=tenant, owner=approver, title__startswith=f"Approval reminder #{obj.pk}", status__in=["not_started", "in_progress", "waiting"]).exists():
                    Task.objects.create(tenant=tenant, title=f"Approval reminder #{obj.pk}", description=f"Approval for {obj.requester.get_full_name() or obj.requester.username} is still pending.", category="internal", priority="normal", owner=approver, due_date=timezone.localdate())
                    obj.last_reminder_at = now
                    obj.save(update_fields=["last_reminder_at", "updated_at"])
                    created += 1
    return created


def wfh_users_on_date(user, tenant, target_date):
    """Return visible users whose effective WFH status is on for one date."""
    if target_date.weekday() > 4 or PublicHoliday.objects.filter(tenant=tenant, date=target_date).exists():
        return []
    users = list(visible_users(user, tenant))
    user_ids = {u.id for u in users}
    schedules = {s.user_id: s for s in WFHSchedule.objects.filter(tenant=tenant, user_id__in=user_ids)}
    changes = list(WFHChangeRequest.objects.filter(tenant=tenant, requester_id__in=user_ids, status="approved").filter(Q(requested_date=target_date) | Q(original_date=target_date)))
    swaps_to_remove = {c.requester_id for c in changes if c.change_type == "swap" and c.original_date == target_date}
    removed = {c.requester_id for c in changes if c.change_type == "remove"}
    added = {c.requester_id for c in changes if c.change_type in {"add", "swap"}}
    leave_users = set(LeaveRequest.objects.filter(tenant=tenant, requester_id__in=user_ids, status="approved", start_date__lte=target_date, end_date__gte=target_date).values_list("requester_id", flat=True))
    result = []
    for person in users:
        schedule = schedules.get(person.id)
        enabled = bool(schedule and schedule.weekday_enabled(target_date.weekday()))
        if person.id in swaps_to_remove or person.id in removed:
            enabled = False
        if person.id in added:
            enabled = True
        if enabled and person.id not in leave_users:
            result.append(person)
    return result

def get_scope_codes(project, milestone=None):
    modalities = list(milestone.modalities.all()) if milestone is not None and milestone.modalities.exists() else list(project.modalities.all())
    return " + ".join(sorted({m.code or m.name[:1].upper() for m in modalities if m.code or m.name}))


def grouped_deadlines(user, tenant, start_date, end_date):
    """One calendar event per project/milestone type/date, with scope codes merged."""
    milestones = Milestone.objects.filter(
        tenant=tenant,
        deadline__gte=start_date,
        deadline__lte=end_date,
    ).exclude(status__in=["closed", "paid", "issued"]).select_related("project").prefetch_related("project__modalities", "modalities")
    visible = visible_projects(user, tenant)
    allowed = set(visible.values_list("id", flat=True))
    groups = {}
    for milestone in milestones:
        if milestone.project_id not in allowed:
            continue
        key = (milestone.project_id, milestone.milestone_type, milestone.deadline)
        groups.setdefault(key, []).append(milestone)
    result = []
    for (project_id, milestone_type, deadline), items in groups.items():
        project = items[0].project
        codes = set()
        responsible = False
        statuses = set()
        for item in items:
            code_string = get_scope_codes(project, item)
            if code_string:
                codes.update(part.strip() for part in code_string.split("+"))
            responsible = responsible or item.responsible_user_id == user.id or project.project_manager_id == user.id or project.director_id == user.id
            statuses.add(item.status)
        result.append({
            "date": deadline,
            "title": f"{milestone_type} — {project.project_number}",
            "project": project,
            "scope": " + ".join(sorted(codes)),
            "requires_action": responsible,
            "status": "overdue" if "overdue" in statuses or deadline < timezone.localdate() else ("at_risk" if "at_risk" in statuses else "scheduled"),
        })
    return sorted(result, key=lambda x: (x["date"], x["project"].project_number))
