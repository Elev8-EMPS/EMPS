import calendar as pycalendar
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from delivery.models import Milestone, Task
from tenants.models import Team
from tenants.utils import get_user_role, get_user_tenant, can_view_proposals

from .forms import CalendarEventTypeForm, CalendarPreferenceForm, CalendarSettingsForm, LeaveRequestForm, LeaveTypeConfigForm, WFHChangeRequestForm, WFHScheduleForm
from .models import CalendarEventType, CalendarPreference, CalendarSettings, LeaveApproval, LeaveRequest, LeaveType, WFHChangeRequest, WFHSchedule
from .services import (
    ensure_calendar_defaults,
    find_approver,
    get_or_create_preference,
    get_calendar_settings as get_or_create_calendar_settings,
    grouped_deadlines,
    user_can_access_management,
    user_can_approve,
    visible_leave_requests,
    visible_projects,
    visible_users,
    visible_wfh_requests,
    validate_wfh_change,
    process_approval_escalations,
    wfh_users_on_date,
)


def _tenant_or_404(request):
    tenant = get_user_tenant(request)
    if not tenant:
        raise Http404("Your user is not assigned to a tenant.")
    ensure_calendar_defaults(tenant)
    return tenant


def _month(value):
    today = timezone.localdate()
    if not value:
        return today.year, today.month
    try:
        parsed = datetime.strptime(value, "%Y-%m").date()
        return parsed.year, parsed.month
    except ValueError:
        return today.year, today.month


def _month_days(year, month):
    first = date(year, month, 1)
    last = date(year, month, pycalendar.monthrange(year, month)[1])
    grid_start = first - timedelta(days=first.weekday())
    grid_end = last + timedelta(days=(6 - last.weekday()))
    days = []
    current = grid_start
    while current <= grid_end:
        days.append(current)
        current += timedelta(days=1)
    return first, last, days


def _event(event_type, title, event_date, *, colour=None, requires_action=False, detail="", obj=None):
    return {
        "type": event_type,
        "title": title,
        "date": event_date,
        "colour": colour or "#2563eb",
        "requires_action": requires_action,
        "detail": detail,
        "object": obj,
    }


def _calendar_events(request, tenant, start_date, end_date):
    preference = get_or_create_preference(request.user, tenant)
    events = []
    event_colours = {x.code: x.colour for x in CalendarEventType.objects.filter(tenant=tenant, is_active=True)}

    if preference.show_leave:
        for leave in visible_leave_requests(request.user, tenant, start_date, end_date).filter(status="approved"):
            current = max(leave.start_date, start_date)
            finish = min(leave.end_date, end_date)
            while current <= finish:
                if current.weekday() < 5:
                    part_label = ""
                    if leave.start_date == leave.end_date and leave.start_part in {"am", "pm"}:
                        part_label = " — ½ day (morning)" if leave.start_part == "am" else " — ½ day (afternoon)"
                    elif current == leave.start_date and leave.start_part in {"am", "pm"}:
                        part_label = " — ½ day start"
                    elif current == leave.end_date and leave.end_part in {"am", "pm"}:
                        part_label = " — ½ day end"
                    events.append(_event(
                        "leave", f"{leave.requester.get_full_name() or leave.requester.username} — {leave.leave_type.name}{part_label}", current,
                        colour=leave.leave_type.colour, detail=f"{leave.working_days:g} day(s)", obj=leave,
                    ))
                current += timedelta(days=1)

    if preference.show_wfh:
        users = visible_users(request.user, tenant)
        schedules = WFHSchedule.objects.filter(tenant=tenant, user__in=users).select_related("user")
        changes = visible_wfh_requests(request.user, tenant, start_date, end_date).filter(status="approved")
        changed_dates = {(c.requester_id, c.original_date): c for c in changes if c.original_date and c.change_type == "swap"}
        removed_dates = {(c.requester_id, c.requested_date) for c in changes if c.change_type == "remove"}
        approved_leave_dates = set()
        for leave in visible_leave_requests(request.user, tenant, start_date, end_date).filter(status="approved"):
            current_leave = max(leave.start_date, start_date)
            while current_leave <= min(leave.end_date, end_date):
                if current_leave.weekday() < 5:
                    approved_leave_dates.add((leave.requester_id, current_leave))
                current_leave += timedelta(days=1)
        added_dates = {(c.requester_id, c.requested_date): c for c in changes if c.change_type in {"add", "swap"}}
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                for schedule in schedules:
                    active_from = schedule.effective_from or date.min
                    active_to = schedule.effective_to or date.max
                    if not (active_from <= current <= active_to):
                        continue
                    enabled = schedule.weekday_enabled(current.weekday())
                    if (schedule.user_id, current) in removed_dates:
                        enabled = False
                    if (schedule.user_id, current) in changed_dates:
                        enabled = False
                    if (schedule.user_id, current) in added_dates:
                        enabled = True
                    if enabled and (schedule.user_id, current) not in approved_leave_dates:
                        name = schedule.user.get_full_name() or schedule.user.username
                        events.append(_event("wfh", f"{name} — WFH", current, colour=event_colours.get("wfh", "#059669"), obj=schedule))
            current += timedelta(days=1)

    if preference.show_deadlines:
        for item in grouped_deadlines(request.user, tenant, start_date, end_date):
            detail = item["scope"] or "Project deadline"
            title = item["title"] + (f" — {item['scope']}" if item["scope"] else "")
            events.append(_event("deadline", title, item["date"], colour=event_colours.get("deadline", "#2563eb"), requires_action=item["requires_action"], detail=detail, obj=item["project"]))

    if preference.show_tasks:
        task_q = Q(owner=request.user) | Q(assigned_team__members=request.user)
        tasks = Task.objects.filter(tenant=tenant, due_date__gte=start_date, due_date__lte=end_date).filter(task_q).exclude(status__in=["completed", "cancelled"]).select_related("related_project")
        for task in tasks:
            events.append(_event("task", f"Task — {task.title}", task.due_date, colour=event_colours.get("task", "#d97706"), requires_action=True, detail=task.get_priority_display(), obj=task))

    if preference.show_followups:
        from crm.models import ProposalFollowUp
        from finance.models import InvoiceFollowUp
        if preference.show_fee_proposals:
            for followup in ProposalFollowUp.objects.filter(tenant=tenant, due_date__gte=start_date, due_date__lte=end_date, status="scheduled").select_related("proposal"):
                events.append(_event("followup", f"Proposal follow-up — {followup.proposal.proposal_number}", followup.due_date, colour=event_colours.get("followup", "#0891b2"), requires_action=True, obj=followup))
        for followup in InvoiceFollowUp.objects.filter(tenant=tenant, due_date__gte=start_date, due_date__lte=end_date, status="scheduled").select_related("invoice"):
            events.append(_event("followup", f"Invoice follow-up — {followup.invoice.invoice_number}", followup.due_date, colour=event_colours.get("followup", "#0891b2"), requires_action=True, obj=followup))

    return events


@login_required
def calendar_home(request):
    tenant = _tenant_or_404(request)
    year, month = _month(request.GET.get("month"))
    first, last, days = _month_days(year, month)
    events = _calendar_events(request, tenant, first, last)
    events_by_date = {}
    for event in events:
        events_by_date.setdefault(event["date"], []).append(event)
    prev_month = (first - timedelta(days=1)).strftime("%Y-%m")
    next_month = (last + timedelta(days=1)).strftime("%Y-%m")
    pending_leave = LeaveRequest.objects.filter(tenant=tenant, requester=request.user, status="pending").count()
    pending_wfh = WFHChangeRequest.objects.filter(tenant=tenant, requester=request.user, status="pending").count()
    return render(request, "calendar_app/calendar.html", {
        "active_nav": "calendar", "user_tenant": tenant, "tenant": tenant,
        "first": first, "last": last, "days": days, "events_by_date": events_by_date,
        "weekday_names": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "month_label": first.strftime("%B %Y"), "prev_month": prev_month, "next_month": next_month,
        "pending_leave": pending_leave, "pending_wfh": pending_wfh,
        "preference": get_or_create_preference(request.user, tenant),
    })


@login_required
def leave_request_create(request):
    tenant = _tenant_or_404(request)
    if request.method == "POST":
        form = LeaveRequestForm(request.POST, tenant=tenant)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.tenant = tenant
            leave.requester = request.user
            leave.current_approver = find_approver(request.user, leave.start_date, leave.end_date)
            if not leave.current_approver:
                form.add_error(None, "No manager, director or company administrator is available to approve this request.")
            else:
                from .services import leave_conflicts
                if leave_conflicts(leave):
                    form.add_error(None, "You already have a pending or approved leave request overlapping these dates.")
                else:
                    leave.full_clean()
                    leave.save()
                    Task.objects.create(
                        tenant=tenant,
                        title=f"Leave approval required — {request.user.get_full_name() or request.user.username}",
                        description=(f"Leave request #{leave.pk}: {request.user.get_full_name() or request.user.username} requested {leave.leave_type.name} "
                                    f"from {leave.start_date:%d %b %Y} to {leave.end_date:%d %b %Y} ({leave.working_days:g} day(s)).\n\n"
                                    f"Reason: {leave.reason or 'No reason provided.'}\n\n"
                                    f"Open Calendar → Leave approvals to approve or decline."),
                        category="internal", priority="high", owner=leave.current_approver,
                        due_date=timezone.localdate(),
                    )
                    messages.success(request, "Leave request submitted for approval.")
                    return redirect("calendar_home")
    else:
        initial = {}
        selected_date = request.GET.get("date")
        if selected_date:
            try:
                parsed = datetime.strptime(selected_date, "%Y-%m-%d").date()
                initial = {"start_date": parsed, "end_date": parsed}
            except ValueError:
                pass
        form = LeaveRequestForm(tenant=tenant, initial=initial)
    return render(request, "calendar_app/leave_form.html", {"form": form, "user_tenant": tenant, "active_nav": "calendar", "title": "Request leave"})


@login_required
def wfh_request_create(request):
    tenant = _tenant_or_404(request)
    if request.method == "POST":
        form = WFHChangeRequestForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = tenant
            obj.requester = request.user
            obj.current_approver = find_approver(request.user, obj.requested_date, obj.requested_date)
            if not obj.current_approver:
                form.add_error(None, "No manager, director or company administrator is available to approve this request.")
            else:
                try:
                    obj.full_clean()
                    validate_wfh_change(obj)
                except ValueError as exc:
                    form.add_error(None, str(exc))
                else:
                    obj.save()
                    description = f"WFH request #{obj.pk}: {obj.get_change_type_display()} requested for {obj.requested_date:%d %b %Y}. "
                    if obj.original_date:
                        description += f"Original date: {obj.original_date:%d %b %Y}. "
                    description += f"Reason: {obj.reason or 'No reason provided.'}"
                    Task.objects.create(
                        tenant=tenant,
                        title=f"WFH approval required — {request.user.get_full_name() or request.user.username}",
                        description=description,
                        category="internal", priority="normal", owner=obj.current_approver,
                        due_date=timezone.localdate(),
                    )
                    messages.success(request, "WFH change request submitted for approval.")
                    return redirect("calendar_home")
    else:
        selected_date = request.GET.get("date")
        initial = {}
        if selected_date:
            try:
                initial["requested_date"] = datetime.strptime(selected_date, "%Y-%m-%d").date()
            except ValueError:
                pass
        form = WFHChangeRequestForm(initial=initial)
    return render(request, "calendar_app/wfh_form.html", {"form": form, "user_tenant": tenant, "active_nav": "calendar", "title": "Request WFH change"})


@login_required
def wfh_schedule(request, user_id=None):
    tenant = _tenant_or_404(request)
    target = request.user if user_id is None else get_object_or_404(User, pk=user_id, profile__tenant=tenant)
    if target != request.user:
        if not user_can_access_management(request.user):
            raise Http404()
        if target.pk not in set(visible_users(request.user, tenant).values_list("id", flat=True)):
            raise Http404()
    schedule, _ = WFHSchedule.objects.get_or_create(user=target, tenant=tenant)
    if request.method == "POST":
        form = WFHScheduleForm(request.POST, instance=schedule)
        if form.is_valid():
            form.save()
            messages.success(request, "WFH schedule saved.")
            return redirect("calendar_home" if target == request.user else "management_hub")
    else:
        form = WFHScheduleForm(instance=schedule)
    return render(request, "calendar_app/wfh_schedule.html", {"form": form, "target": target, "user_tenant": tenant, "active_nav": "calendar"})


@login_required
def leave_approval_list(request):
    tenant = _tenant_or_404(request)
    if get_user_role(request.user) not in {"company_admin", "director", "project_manager"} and not request.user.is_superuser:
        raise Http404()
    qs = visible_leave_requests(request.user, tenant).filter(status="pending")
    return render(request, "calendar_app/approval_list.html", {"leave_requests": qs, "wfh_requests": visible_wfh_requests(request.user, tenant).filter(status="pending"), "user_tenant": tenant, "active_nav": "calendar"})


def _decline_requires_reason(request):
    reason = (request.POST.get("decline_reason") or "").strip()
    return reason


@login_required
def leave_approve(request, pk):
    tenant = _tenant_or_404(request)
    leave = get_object_or_404(LeaveRequest.objects.select_related("requester", "leave_type", "current_approver"), pk=pk, tenant=tenant)
    if not user_can_approve(request.user, leave) or leave.status != "pending":
        raise Http404()
    if request.method != "POST":
        return redirect("leave_approval_list")
    action = request.POST.get("action")
    with transaction.atomic():
        leave = LeaveRequest.objects.select_for_update().get(pk=leave.pk)
        if leave.status != "pending" or not user_can_approve(request.user, leave):
            messages.error(request, "This request has already been processed or is no longer assigned to you.")
            return redirect("leave_approval_list")
        if action == "decline":
            reason = _decline_requires_reason(request)
            if not reason:
                messages.error(request, "A reason is required when declining leave.")
                return redirect("leave_approval_list")
            leave.status = "declined"
            leave.decline_reason = reason
        elif action == "approve":
            leave.status = "approved"
            leave.decline_reason = ""
        else:
            messages.error(request, "Invalid approval action.")
            return redirect("leave_approval_list")
        leave.decided_at = timezone.now()
        leave.save(update_fields=["status", "decline_reason", "decided_at", "updated_at"])
        LeaveApproval.objects.create(tenant=tenant, request=leave, approver=request.user, action=leave.status, reason=leave.decline_reason)
        Task.objects.filter(tenant=tenant, owner=request.user, title__startswith="Leave approval required", description__icontains=f"Leave request #{leave.pk}:").update(status="completed", completed_at=timezone.now())
    messages.success(request, f"Leave request {leave.status}.")
    return redirect("leave_approval_list")


@login_required
def wfh_approve(request, pk):
    tenant = _tenant_or_404(request)
    obj = get_object_or_404(WFHChangeRequest.objects.select_related("requester", "current_approver"), pk=pk, tenant=tenant)
    if not user_can_approve(request.user, obj) or obj.status != "pending":
        raise Http404()
    if request.method != "POST":
        return redirect("leave_approval_list")
    action = request.POST.get("action")
    with transaction.atomic():
        obj = WFHChangeRequest.objects.select_for_update().get(pk=obj.pk)
        if obj.status != "pending" or not user_can_approve(request.user, obj):
            messages.error(request, "This request has already been processed or is no longer assigned to you.")
            return redirect("leave_approval_list")
        if action == "decline":
            reason = _decline_requires_reason(request)
            if not reason:
                messages.error(request, "A reason is required when declining a WFH change.")
                return redirect("leave_approval_list")
            obj.status = "declined"
            obj.decline_reason = reason
        elif action == "approve":
            obj.status = "approved"
            obj.decline_reason = ""
        else:
            messages.error(request, "Invalid approval action.")
            return redirect("leave_approval_list")
        obj.decided_at = timezone.now()
        obj.save(update_fields=["status", "decline_reason", "decided_at", "updated_at"])
        Task.objects.filter(tenant=tenant, owner=request.user, title__startswith="WFH approval required", description__icontains=f"WFH request #{obj.pk}:").update(status="completed", completed_at=timezone.now())
    messages.success(request, f"WFH request {obj.status}.")
    return redirect("leave_approval_list")


@login_required
def my_requests(request):
    tenant = _tenant_or_404(request)
    leave = LeaveRequest.objects.filter(tenant=tenant, requester=request.user).select_related("leave_type", "current_approver")
    wfh = WFHChangeRequest.objects.filter(tenant=tenant, requester=request.user).select_related("current_approver")
    return render(request, "calendar_app/my_requests.html", {"leave_requests": leave, "wfh_requests": wfh, "user_tenant": tenant, "active_nav": "calendar"})


@login_required
def calendar_preferences(request):
    tenant = _tenant_or_404(request)
    pref = get_or_create_preference(request.user, tenant)
    if request.method == "POST":
        form = CalendarPreferenceForm(request.POST, instance=pref)
    else:
        form = CalendarPreferenceForm(instance=pref)
    if get_user_role(request.user) not in {"company_admin", "director"} and not request.user.is_superuser:
        form.fields.pop("show_company_wide", None)
    if not can_view_proposals(request.user):
        form.fields.pop("show_fee_proposals", None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Calendar preferences saved.")
        return redirect("calendar_home")
    return render(request, "calendar_app/preferences.html", {"form": form, "user_tenant": tenant, "active_nav": "calendar"})


@login_required
def calendar_configuration(request):
    tenant = _tenant_or_404(request)
    if get_user_role(request.user) not in {"company_admin", "director"} and not request.user.is_superuser:
        raise Http404()
    settings_obj = get_or_create_calendar_settings(tenant)
    event_types = CalendarEventType.objects.filter(tenant=tenant).order_by("order", "name")
    leave_types = LeaveType.objects.filter(tenant=tenant).order_by("order", "name")
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "settings":
            form = CalendarSettingsForm(request.POST, instance=settings_obj)
            if form.is_valid():
                form.save(); messages.success(request, "Calendar approval settings saved.")
        elif action == "event":
            obj = get_object_or_404(CalendarEventType, pk=request.POST.get("pk"), tenant=tenant)
            form = CalendarEventTypeForm(request.POST, instance=obj)
            if form.is_valid():
                form.save(); messages.success(request, "Calendar event styling saved.")
        elif action == "leave":
            obj = get_object_or_404(LeaveType, pk=request.POST.get("pk"), tenant=tenant)
            form = LeaveTypeConfigForm(request.POST, instance=obj)
            if form.is_valid():
                form.save(); messages.success(request, "Leave type settings saved.")
        return redirect("calendar_configuration")
    return render(request, "calendar_app/configuration.html", {
        "active_nav": "management", "user_tenant": tenant, "settings_form": CalendarSettingsForm(instance=settings_obj),
        "event_types": [(obj, CalendarEventTypeForm(instance=obj)) for obj in event_types],
        "leave_types": [(obj, LeaveTypeConfigForm(instance=obj)) for obj in leave_types],
    })


@login_required
def management_hub(request):
    tenant = _tenant_or_404(request)
    if not user_can_access_management(request.user):
        raise Http404()
    process_approval_escalations(tenant)
    role = get_user_role(request.user)
    pending_leave = visible_leave_requests(request.user, tenant).filter(status="pending")
    pending_wfh = visible_wfh_requests(request.user, tenant).filter(status="pending")
    today = timezone.localdate()
    upcoming_deadlines = grouped_deadlines(request.user, tenant, today, today + timedelta(days=30))
    team_users = visible_users(request.user, tenant)
    today_leave = visible_leave_requests(request.user, tenant, today, today).filter(status="approved")
    today_wfh = wfh_users_on_date(request.user, tenant, today)
    projects = visible_projects(request.user, tenant)
    own_tasks = Task.objects.filter(tenant=tenant, owner=request.user).exclude(status__in=["completed", "cancelled"]).order_by("due_date", "priority")
    preference = get_or_create_preference(request.user, tenant)
    proposals = None
    if preference.show_fee_proposals and can_view_proposals(request.user):
        from crm.models import Proposal
        proposals = Proposal.objects.filter(tenant=tenant, status__in=["draft", "internal_review", "director_review", "approved", "issued", "follow_up_due", "revised"]).select_related("organisation").order_by("-issue_date", "proposal_number")[:50]
    context = {
        "active_nav": "management", "user_tenant": tenant, "role": role,
        "pending_leave": pending_leave[:20], "pending_wfh": pending_wfh[:20],
        "pending_leave_count": pending_leave.count(), "pending_wfh_count": pending_wfh.count(),
        "upcoming_deadlines": upcoming_deadlines[:20], "team_users": team_users,
        "today_leave": today_leave, "today_wfh": today_wfh,
        "active_projects": projects.order_by("project_number")[:50] if preference.show_projects else [], "own_tasks": own_tasks[:20],
        "proposals": proposals, "preference": preference,
    }
    return render(request, "calendar_app/management_hub.html", context)
