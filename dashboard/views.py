import datetime

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render

from tenants.models import Tenant
from crm.models import Proposal
from delivery.models import Milestone, Task
from finance.models import Invoice


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

    today = datetime.date.today()
    soon = today + datetime.timedelta(days=7)

    if tenant is None:
        return render(request, "dashboard/command_centre.html", {"no_tenant": True})

    milestones = Milestone.objects.filter(tenant=tenant)
    proposals = Proposal.objects.filter(tenant=tenant)
    invoices = Invoice.objects.filter(tenant=tenant)
    tasks = Task.objects.filter(tenant=tenant)

    open_proposal_statuses = ["draft", "internal_review", "director_review", "approved", "issued", "follow_up_due", "revised"]
    unpaid_invoice_statuses = ["awaiting_approval", "approved", "issued", "part_paid", "overdue", "disputed"]

    context = {
        "no_tenant": False,
        "tenant": tenant,
        # KPI cards
        "active_projects_count": milestones.values("project").distinct().filter(
            project__status="active"
        ).count(),
        "open_proposals_count": proposals.filter(status__in=open_proposal_statuses).count(),
        "milestones_at_risk_count": milestones.filter(status__in=["at_risk", "overdue"]).count(),
        "outstanding_debt": sum(
            (inv.outstanding_amount for inv in invoices.filter(status__in=unpaid_invoice_statuses)),
            start=0,
        ),
        "ready_to_invoice_count": milestones.filter(status="approved_to_invoice").count(),
        "follow_ups_due_count": proposals.filter(follow_up_date__lte=today).filter(
            status__in=open_proposal_statuses
        ).count(),
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
        ),
        "ready_to_invoice": milestones.filter(status="approved_to_invoice"),
        "overdue_invoices": invoices.filter(due_date__lt=today).filter(status__in=unpaid_invoice_statuses),
        "high_priority_tasks": tasks.filter(priority__in=["high", "critical"]).exclude(
            status__in=["completed", "cancelled"]
        ),
    }
    return render(request, "dashboard/command_centre.html", context)
