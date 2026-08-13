import datetime

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from django.shortcuts import render
from django.utils import timezone

from tenants.models import Tenant, DeadlineCategory
from tenants.utils import get_open_todo_count, can_view_proposals, get_dashboard_visibility, get_display_names
from crm.models import Proposal, Enquiry
from delivery.models import Milestone, Task, Project
from finance.models import Invoice
from leave.models import LeaveRequest, WFHDay


@login_required
def command_centre(request):
    """
    Blueprint section 8 - the Command Centre: KPI cards plus a
    'Today's Focus' list of what actually needs attention.

    NOTE: with only one tenant today, this shows that tenant's data
    directly. Once a second tenant exists, this needs to filter by
    the logged-in user's tenant instead of Tenant.objects.first().
    """

    if request.user.is_superuser:
        tenant = Tenant.objects.first()
    else:
        profile = getattr(request.user, "profile", None)
        tenant = profile.tenant if profile else None

    today = timezone.localtime(timezone.now()).date()
    soon = today + datetime.timedelta(days=7)

    if tenant is None:
        return render(request, "dashboard/command_centre.html", {"no_tenant": True})

    milestones = Milestone.objects.filter(tenant=tenant)
    proposals = Proposal.objects.filter(tenant=tenant)
    invoices = Invoice.objects.filter(tenant=tenant)
    tasks = Task.objects.filter(tenant=tenant)

    from crm.models import ProposalFollowUp
    from finance.models import InvoiceFollowUp
    proposal_followups_due = ProposalFollowUp.objects.filter(
        tenant=tenant, status="scheduled", due_date__lte=today
    ).select_related("proposal", "proposal__organisation")
    invoice_followups_due = InvoiceFollowUp.objects.filter(
        tenant=tenant, status="scheduled", due_date__lte=today
    ).select_related("invoice", "invoice__organisation")

    # This person's team(s) and the disciplines those teams cover -
    # used to show "projects relevant to my team" below.
    my_teams = request.user.teams.filter(tenant=tenant)
    my_team_modality_ids = list(
        my_teams.values_list("modalities__id", flat=True).distinct()
    )
    my_team_projects = None
    if my_team_modality_ids:
        cutoff = timezone.now() - datetime.timedelta(days=7)
        my_team_projects = Project.objects.filter(
            tenant=tenant, status="active", modalities__id__in=my_team_modality_ids
        ).distinct().select_related("client_organisation").order_by("-activated_at")
        my_team_projects = [
            {"project": p, "is_new": p.activated_at is not None and p.activated_at >= cutoff}
            for p in my_team_projects
        ]

    open_proposal_statuses = ["draft", "internal_review", "director_review", "approved", "issued", "follow_up_due", "revised"]
    unpaid_invoice_statuses = ["awaiting_approval", "approved", "issued", "part_paid", "overdue", "disputed"]

    # Who's out or working from home today, across the whole tenant -
    # this is deliberately not team-scoped, since knowing who's around
    # today is useful company-wide and doesn't expose anything private
    # (the free-text reason and decline reason are never shown here).
    out_today = LeaveRequest.objects.filter(
        tenant=tenant, status="approved", start_date__lte=today, end_date__gte=today,
        leave_type__in=["annual", "sick", "other"],
    ).select_related("user")
    wfh_today = WFHDay.objects.filter(tenant=tenant, weekday=today.weekday()).select_related("user")
    # Approved one-off WFH day swaps landing today don't suppress the
    # tenant-wide "who's out" picture the way they do on the personal
    # Calendar (that suppression is per-viewer there); here we just
    # add the swapped-in person too, since a duplicate WFH tag for
    # someone whose standing day also happens to be today is harmless.
    wfh_swap_today = LeaveRequest.objects.filter(
        tenant=tenant, status="approved", leave_type="wfh_swap", start_date=today,
    ).select_related("user")
    site_visit_today = Task.objects.filter(
        tenant=tenant, category="site_visit", due_date=today,
    ).exclude(status__in=["completed", "cancelled"]).exclude(owner__isnull=True).select_related("owner")

    _names_users = (
        [o.user for o in out_today] + [w.user for w in wfh_today]
        + [s.user for s in wfh_swap_today] + [t.owner for t in site_visit_today]
    )
    _display_names = get_display_names(_names_users, tenant)
    for _entry in list(out_today) + list(wfh_today) + list(wfh_swap_today):
        _entry.display_name = _display_names.get(_entry.user_id, _entry.user.first_name or _entry.user.username)
    for _t in site_visit_today:
        _t.owner_display_name = _display_names.get(_t.owner_id, _t.owner.first_name or _t.owner.username)

    # Colour-code the "not in the office" tags: WFH matches the light
    # blue used on the Calendar, leave types get their own colour, and
    # Site Visit borrows whatever colour is set on a "Site Visit"
    # deadline category if one exists, so it stays consistent with
    # how the Calendar colour-codes categories.
    LEAVE_TYPE_COLORS = {
        "annual": "#ca8a04",   # gold
        "sick": "#e11d48",     # rose
        "other": "#6b7280",    # grey
    }
    WFH_COLOR = "#2563eb"
    site_visit_category = DeadlineCategory.objects.filter(tenant=tenant, name__iexact="Site Visit").first()
    SITE_VISIT_COLOR = site_visit_category.color if site_visit_category else "#d97706"

    for _lr in out_today:
        _lr.badge_color = LEAVE_TYPE_COLORS.get(_lr.leave_type, "#6b7280")
    for _w in wfh_today:
        _w.badge_color = WFH_COLOR
    for _s in wfh_swap_today:
        _s.badge_color = WFH_COLOR
    for _t in site_visit_today:
        _t.badge_color = SITE_VISIT_COLOR

    # Fee Proposals are opt-in visible (see tenants.utils.can_view_proposals).
    # People without access see nothing proposal-related by default, or -
    # if this tenant has turned on 'responsible_for' mode - a filtered view
    # of just what they're personally tied to, with fee amounts always
    # excluded regardless of mode.
    full_proposal_access = can_view_proposals(request.user)
    visibility_mode = get_dashboard_visibility(tenant)
    proposals_visibility = "full" if full_proposal_access else (
        "responsible" if visibility_mode == "responsible_for" else "hidden"
    )

    my_responsible_enquiries = None
    my_responsible_proposals = None
    my_archived_projects = None
    if proposals_visibility == "responsible":
        my_responsible_enquiries = Enquiry.objects.filter(
            tenant=tenant, responsible_director=request.user
        ).exclude(status__in=["closed", "declined"]).select_related("organisation").order_by("-date_received")
        my_responsible_proposals = Proposal.objects.filter(tenant=tenant).filter(
            Q(enquiry__responsible_director=request.user)
            | Q(organisation__relationship_owner=request.user)
            | Q(director_approved_by=request.user)
        ).distinct().select_related("organisation").order_by("-issue_date")
        my_archived_projects = Project.objects.filter(
            tenant=tenant, status__in=["archived", "closed", "completed"]
        ).filter(
            Q(project_manager=request.user) | Q(director=request.user)
        ).distinct().select_related("client_organisation").order_by("-archive_date", "-completion_date")

    context = {
        "no_tenant": False,
        "active_nav": "home",
        "tenant": tenant,
        "user_tenant": tenant,
        "active_projects_count": milestones.values("project").distinct().filter(
            project__status="active"
        ).count(),
        "open_proposals_count": proposals.filter(status__in=open_proposal_statuses).count() if full_proposal_access else None,
        "milestones_at_risk_count": milestones.filter(status__in=["at_risk", "overdue"]).count(),
        "outstanding_debt": sum(
            (inv.outstanding_amount for inv in invoices.filter(status__in=unpaid_invoice_statuses)),
            start=0,
        ),
        "ready_to_invoice_count": milestones.filter(status="approved_to_invoice").count(),
        "invoiced_this_month": invoices.filter(
            invoice_date__year=today.year, invoice_date__month=today.month
        ).aggregate(total=Sum("total"))["total"] or 0,
        "follow_ups_due_count": proposals.filter(follow_up_date__lte=today).filter(
            status__in=open_proposal_statuses
        ).count() if full_proposal_access else None,
        "my_open_todos_count": get_open_todo_count(request.user),
        # Today's Focus
        "deadlines_today": milestones.filter(deadline=today).exclude(status__in=["issued", "closed", "paid"]),
        "deadlines_soon": milestones.filter(deadline__gt=today, deadline__lte=soon).exclude(
            status__in=["issued", "closed", "paid"]
        ),
        "overdue_milestones": milestones.filter(deadline__lt=today).exclude(
            status__in=["issued", "closed", "paid"]
        ),
        "proposal_follow_ups": proposals.filter(follow_up_date__lte=today).filter(
            status__in=open_proposal_statuses
        ) if full_proposal_access else None,
        "ready_to_invoice": milestones.filter(status="approved_to_invoice"),
        "overdue_invoices": invoices.filter(due_date__lt=today).filter(status__in=unpaid_invoice_statuses),
        "high_priority_tasks": tasks.filter(priority__in=["high", "critical"]).exclude(
            status__in=["completed", "cancelled"]
        ),
        "proposal_followups_due": proposal_followups_due if full_proposal_access else None,
        "invoice_followups_due": invoice_followups_due,
        "my_team_projects": my_team_projects,
        # Who's around today
        "out_today": out_today,
        "wfh_today": wfh_today,
        "wfh_swap_today": wfh_swap_today,
        "site_visit_today": site_visit_today,
        "today_count": out_today.count() + wfh_today.count() + wfh_swap_today.count() + site_visit_today.count(),
        # Fee Proposal visibility - "full", "responsible", or "hidden"
        "proposals_visibility": proposals_visibility,
        "my_responsible_enquiries": my_responsible_enquiries,
        "my_responsible_proposals": my_responsible_proposals,
        "my_archived_projects": my_archived_projects,
    }
    return render(request, "dashboard/command_centre.html", context)
