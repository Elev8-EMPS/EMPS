import calendar as calendar_module
import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from tenants.models import Team
from tenants.utils import get_user_tenant, can_view_confidential, can_approve_leave, get_display_names
from delivery.models import Milestone, Project, Task
from .models import LeaveRequest, WFHDay, CalendarScope, WEEKDAY_CHOICES


ACTIVE_STATUSES = ["pending", "approved"]


def _week_bounds(d):
    """Returns (monday, sunday) of the Mon-Sun week containing date d."""
    monday = d - datetime.timedelta(days=d.weekday())
    return monday, monday + datetime.timedelta(days=6)


def _visible_users(request_user, tenant):
    """Whose leave/WFH this person can see on the team calendar.
    Directors/Company Admins see the whole tenant (narrowable via
    CalendarScope); everyone else sees their direct reports."""
    if can_view_confidential(request_user):
        scope, _ = CalendarScope.objects.get_or_create(user=request_user)
        teams = scope.included_teams.all()
        if teams.exists():
            return User.objects.filter(profile__tenant=tenant, teams__in=teams).distinct()
        return User.objects.filter(profile__tenant=tenant)
    return User.objects.filter(profile__tenant=tenant, profile__manager=request_user)


def _create_notification_task(leave_request, tenant):
    """Puts the request on the right person's to-do list: their Line
    Manager if they have one, otherwise every Director/Company Admin
    in the tenant so nothing falls through the cracks."""
    profile = getattr(leave_request.user, "profile", None)
    manager = profile.manager if profile else None

    title = f"Leave request: {leave_request.user.get_full_name() or leave_request.user.username} - {leave_request.get_leave_type_display()}"
    description = f"{leave_request.start_date} to {leave_request.end_date}. {leave_request.reason}".strip()

    if manager:
        task = Task.objects.create(
            tenant=tenant, title=title, description=description, category="internal",
            priority="normal", owner=manager, due_date=leave_request.start_date,
            created_by=leave_request.user,
        )
    else:
        admins = User.objects.filter(profile__tenant=tenant, profile__role__in=["company_admin", "director"])
        task = None
        for admin_user in admins:
            t = Task.objects.create(
                tenant=tenant, title=title, description=description, category="internal",
                priority="normal", owner=admin_user, due_date=leave_request.start_date,
                created_by=leave_request.user,
            )
            task = task or t  # link the request to the first one created

    leave_request.notification_task = task
    leave_request.save(update_fields=["notification_task"])


@login_required
def calendar_view(request):
    tenant = get_user_tenant(request)
    if tenant is None:
        return render(request, "leave/calendar.html", {"no_tenant": True})

    today = datetime.date.today()
    year = int(request.GET.get("year", today.year))
    month = int(request.GET.get("month", today.month))
    first_of_month = datetime.date(year, month, 1)
    days_in_month = calendar_module.monthrange(year, month)[1]
    last_of_month = datetime.date(year, month, days_in_month)

    prev_month = (first_of_month - datetime.timedelta(days=1)).replace(day=1)
    next_month = (last_of_month + datetime.timedelta(days=1))

    visible_users = _visible_users(request.user, tenant)
    is_approver = can_view_confidential(request.user) or User.objects.filter(
        profile__tenant=tenant, profile__manager=request.user
    ).exists()

    all_shown_users = list(visible_users) + [request.user]
    display_names = get_display_names(all_shown_users, tenant)

    leave_qs = LeaveRequest.objects.filter(
        tenant=tenant, status__in=ACTIVE_STATUSES,
        start_date__lte=last_of_month, end_date__gte=first_of_month,
    ).filter(Q(user=request.user) | Q(user__in=visible_users)).distinct().select_related("user")
    # 'Leave' proper - annual/sick/other. WFH swaps/standing changes are
    # handled separately below so they render as WFH, not as leave.
    leave_only_qs = [lr for lr in leave_qs if lr.leave_type in ("annual", "sick", "other")]

    approved_swaps = [
        lr for lr in leave_qs if lr.leave_type == "wfh_swap" and lr.status == "approved"
    ]
    swapped_away = {(lr.user_id, lr.swap_original_date) for lr in approved_swaps if lr.swap_original_date}

    wfh_qs = WFHDay.objects.filter(
        tenant=tenant
    ).filter(Q(user=request.user) | Q(user__in=visible_users)).distinct().select_related("user")

    my_teams = request.user.teams.filter(tenant=tenant)
    my_team_modality_ids = list(my_teams.values_list("modalities__id", flat=True).distinct())
    deadlines_qs = Milestone.objects.none()
    if my_team_modality_ids:
        deadlines_qs = Milestone.objects.filter(
            tenant=tenant, deadline__gte=first_of_month, deadline__lte=last_of_month,
            project__modalities__id__in=my_team_modality_ids,
        ).distinct().select_related("project").order_by("deadline")

    # Build the month grid: a list of weeks, each a list of 7 days
    # (None for padding outside the month), each day carrying the
    # leave/WFH/deadline entries that fall on it.
    cal = calendar_module.Calendar(firstweekday=0)
    weeks = []
    for week in cal.monthdayscalendar(year, month):
        week_days = []
        for day_num in week:
            if day_num == 0:
                week_days.append(None)
                continue
            d = datetime.date(year, month, day_num)
            day_leave = [lr for lr in leave_only_qs if lr.start_date <= d <= lr.end_date]
            day_wfh = [
                w for w in wfh_qs if w.weekday == d.weekday() and (w.user_id, d) not in swapped_away
            ] + [lr for lr in approved_swaps if lr.start_date == d]
            for entry in day_leave + day_wfh:
                entry.display_name = display_names.get(entry.user_id, entry.user.first_name or entry.user.username)
            week_days.append({
                "date": d,
                "is_today": d == today,
                "leave": day_leave,
                "wfh": day_wfh,
                "deadlines": [m for m in deadlines_qs if m.deadline == d],
            })
        weeks.append(week_days)

    pending_approvals_count = 0
    if is_approver:
        approvable_users = visible_users if can_view_confidential(request.user) else User.objects.filter(
            profile__tenant=tenant, profile__manager=request.user
        )
        pending_approvals_count = LeaveRequest.objects.filter(
            tenant=tenant, status="pending", user__in=approvable_users
        ).count()

    return render(request, "leave/calendar.html", {
        "no_tenant": False,
        "active_nav": "calendar",
        "user_tenant": tenant,
        "weeks": weeks,
        "month_name": first_of_month.strftime("%B %Y"),
        "prev_year": prev_month.year, "prev_month": prev_month.month,
        "next_year": next_month.year, "next_month": next_month.month,
        "today": today,
        "leave_type_choices": LeaveRequest.LEAVE_TYPE_CHOICES,
        "weekday_choices": WEEKDAY_CHOICES,
        "is_approver": is_approver,
        "is_admin_scope": can_view_confidential(request.user),
        "pending_approvals_count": pending_approvals_count,
        "my_wfh_days": WFHDay.objects.filter(tenant=tenant, user=request.user).order_by("weekday"),
    })


@login_required
def leave_request_create(request):
    if request.method != "POST":
        return redirect("calendar")

    tenant = get_user_tenant(request)
    leave_type = request.POST.get("leave_type", "")
    start_date = request.POST.get("start_date", "")
    end_date = request.POST.get("end_date", "") or start_date
    reason = request.POST.get("reason", "").strip()

    valid_types = {v for v, _ in LeaveRequest.LEAVE_TYPE_CHOICES}
    if leave_type not in valid_types or not start_date:
        messages.error(request, "Please choose a leave type and at least a start date.")
        return redirect("calendar")

    if leave_type == "other" and not reason:
        messages.error(request, "Please give a reason for 'Other' requests.")
        return redirect("calendar")

    leave_request = LeaveRequest(
        tenant=tenant, user=request.user, leave_type=leave_type,
        start_date=start_date, end_date=end_date, reason=reason,
    )

    if leave_type == "wfh_swap":
        # The user picks which standing WFH day they're moving, and
        # what date they want to WFH instead - we work out the actual
        # date of that standing day ourselves (server-side, never
        # trusting a client-supplied date for it) and require the new
        # date to fall in the same Mon-Sun week and be a weekday.
        weekday_raw = request.POST.get("swap_weekday")
        try:
            target_date = datetime.date.fromisoformat(start_date)
            weekday = int(weekday_raw)
        except (ValueError, TypeError):
            messages.error(request, "Please choose which WFH day you're swapping and a new date.")
            return redirect("calendar")

        has_standing_day = WFHDay.objects.filter(tenant=tenant, user=request.user, weekday=weekday).exists()
        if not has_standing_day:
            messages.error(request, "That's not currently one of your standing WFH days.")
            return redirect("calendar")

        monday, sunday = _week_bounds(target_date)
        original_date = monday + datetime.timedelta(days=weekday)

        if target_date == original_date:
            messages.error(request, "Please pick a different day to swap to.")
            return redirect("calendar")
        if target_date.weekday() >= 5:
            messages.error(request, "The new WFH day has to be a weekday (Monday to Friday).")
            return redirect("calendar")

        leave_request.standing_weekday = weekday
        leave_request.swap_original_date = original_date
        leave_request.start_date = target_date
        leave_request.end_date = target_date

    if leave_type == "wfh_standing":
        weekday = request.POST.get("standing_weekday")
        action = request.POST.get("standing_action")
        if weekday is None or action not in {"add", "remove"}:
            messages.error(request, "Please choose a weekday and whether to add or remove it.")
            return redirect("calendar")
        leave_request.standing_weekday = int(weekday)
        leave_request.standing_action = action
        leave_request.end_date = leave_request.start_date

    leave_request.save()
    _create_notification_task(leave_request, tenant)
    messages.success(request, "Your request has been sent for approval.")
    return redirect("calendar")


@login_required
def my_leave_requests(request):
    tenant = get_user_tenant(request)
    requests_qs = LeaveRequest.objects.filter(tenant=tenant, user=request.user).order_by("-start_date")
    return render(request, "leave/my_requests.html", {
        "active_nav": "calendar",
        "user_tenant": tenant,
        "requests": requests_qs,
    })


@login_required
def leave_approvals(request):
    tenant = get_user_tenant(request)

    if can_view_confidential(request.user):
        approvable_users = User.objects.filter(profile__tenant=tenant)
    else:
        approvable_users = User.objects.filter(profile__tenant=tenant, profile__manager=request.user)

    pending = LeaveRequest.objects.filter(
        tenant=tenant, status="pending", user__in=approvable_users
    ).select_related("user").order_by("start_date")

    decided = LeaveRequest.objects.filter(
        tenant=tenant, status__in=["approved", "declined"], decided_by=request.user
    ).select_related("user").order_by("-decided_at")[:20]

    return render(request, "leave/approvals.html", {
        "active_nav": "calendar",
        "user_tenant": tenant,
        "pending": pending,
        "decided": decided,
    })


@login_required
def leave_decide(request, pk):
    if request.method != "POST":
        return redirect("leave_approvals")

    tenant = get_user_tenant(request)
    leave_request = get_object_or_404(LeaveRequest, pk=pk, tenant=tenant)

    if not can_approve_leave(request.user, leave_request.user):
        messages.error(request, "You don't have permission to decide this request.")
        return redirect("leave_approvals")

    decision = request.POST.get("decision")
    if decision not in {"approved", "declined"}:
        messages.error(request, "Invalid decision.")
        return redirect("leave_approvals")

    if decision == "declined" and not request.POST.get("decline_reason", "").strip():
        messages.error(request, "Please give a reason for declining.")
        return redirect("leave_approvals")

    leave_request.status = decision
    leave_request.decided_by = request.user
    leave_request.decided_at = timezone.now()
    if decision == "declined":
        leave_request.decline_reason = request.POST.get("decline_reason", "").strip()
    leave_request.save()

    if decision == "approved" and leave_request.leave_type == "wfh_standing":
        if leave_request.standing_action == "add":
            WFHDay.objects.get_or_create(
                tenant=tenant, user=leave_request.user, weekday=leave_request.standing_weekday
            )
        else:
            WFHDay.objects.filter(
                tenant=tenant, user=leave_request.user, weekday=leave_request.standing_weekday
            ).delete()

    if leave_request.notification_task and leave_request.notification_task.status not in ("completed", "cancelled"):
        leave_request.notification_task.status = "completed"
        leave_request.notification_task.save(update_fields=["status"])

    messages.success(request, f"Request {decision}.")
    return redirect("leave_approvals")


@login_required
def calendar_scope_edit(request):
    tenant = get_user_tenant(request)
    if not can_view_confidential(request.user):
        messages.error(request, "You don't have permission to change this.")
        return redirect("calendar")

    scope, _ = CalendarScope.objects.get_or_create(user=request.user)

    if request.method == "POST":
        team_ids = [int(x) for x in request.POST.getlist("teams")]
        scope.included_teams.set(Team.objects.filter(tenant=tenant, id__in=team_ids))
        messages.success(request, "Calendar scope updated.")
        return redirect("calendar")

    return render(request, "leave/calendar_scope.html", {
        "active_nav": "calendar",
        "user_tenant": tenant,
        "teams": Team.objects.filter(tenant=tenant).order_by("name"),
        "selected_team_ids": list(scope.included_teams.values_list("id", flat=True)),
    })
