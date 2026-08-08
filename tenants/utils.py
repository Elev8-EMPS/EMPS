from django.db import models


FINANCIAL_ROLES = {"company_admin", "director", "accounts"}
CONFIDENTIAL_ROLES = {"company_admin", "director"}
PROPOSAL_ROLES = {"company_admin", "director"}


def get_user_role(user):
    if user.is_superuser:
        return "company_admin"
    profile = getattr(user, "profile", None)
    return profile.role if profile else ""


def can_view_financials(user):
    """Invoices, payments, fee amounts on proposals - restricted to
    admin, director, and accounts roles, per the blueprint's rule
    that financial data isn't visible to everyone by default."""
    return get_user_role(user) in FINANCIAL_ROLES


def can_view_confidential(user):
    """Employee records, confidential company documents - admin and
    director only."""
    return get_user_role(user) in CONFIDENTIAL_ROLES


def can_view_proposals(user):
    """Fee Proposals - including fee amounts and (future) proposal
    letters/templates - are opt-in visible. Company Administrators
    and Directors always qualify; everyone else needs
    `can_manage_proposals` explicitly ticked on their profile via
    Manage. Deliberately separate from `can_view_financials`: an
    Accounts user sees invoices without automatically seeing fee
    proposals, and vice versa."""
    if get_user_role(user) in PROPOSAL_ROLES:
        return True
    profile = getattr(user, "profile", None)
    return bool(profile and profile.can_manage_proposals)


def can_view_fee_amounts(user):
    """Any dollar figure that originates from a fee proposal (a
    proposal's fee_amount, or a project's original_fee) - visible to
    anyone who can see financials OR proposals, since Accounts
    legitimately needs original_fee for reconciliation even without
    full proposal access."""
    return can_view_financials(user) or can_view_proposals(user)


def get_dashboard_visibility(tenant):
    """The tenant-level setting controlling what people WITHOUT
    proposal access see on their Command Centre. Defaults to the
    strict 'restricted' behaviour if there's no tenant yet."""
    return tenant.dashboard_visibility if tenant else "restricted"


def get_user_tenant(request):
    """
    Shared logic for 'which tenant's data should this request see'.
    Superusers see the first tenant (there's only one today).
    Everyone else sees their own tenant, or None if unassigned.
    """
    if request.user.is_superuser:
        from .models import Tenant
        return Tenant.objects.first()
    profile = getattr(request.user, "profile", None)
    return profile.tenant if profile else None


def get_open_todo_count(user):
    """
    How many open (not completed/cancelled) to-dos are assigned to
    this user directly, or to any team they belong to. Used for the
    sidebar badge and Command Centre alert.
    """
    if not user.is_authenticated:
        return 0
    from delivery.models import Task
    open_statuses = ["not_started", "in_progress", "waiting"]
    profile = getattr(user, "profile", None)
    tenant = profile.tenant if profile else None
    qs = Task.objects.filter(status__in=open_statuses)
    if tenant:
        qs = qs.filter(tenant=tenant)
    return qs.filter(
        models.Q(owner=user) | models.Q(assigned_team__members=user)
    ).distinct().count()
