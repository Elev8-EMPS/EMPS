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


def can_approve_leave(actor, target_user):
    """Who's allowed to approve/decline a leave or WFH request for
    `target_user`: their Line Manager specifically, or anyone with
    the Director/Company Admin role - matching the rule that only
    managers, directors, and company admins can act on leave."""
    if get_user_role(actor) in CONFIDENTIAL_ROLES:  # company_admin, director
        return True
    profile = getattr(target_user, "profile", None)
    return bool(profile and profile.manager_id == actor.id)


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
    return Task.objects.filter(status__in=open_statuses).filter(
        models.Q(owner=user) | models.Q(assigned_team__members=user)
    ).distinct().count()


def get_display_names(users, tenant):
    """
    Builds a {user_id: display_name} dict for a group of people shown
    together on the Calendar or a dashboard 'who's out today' widget,
    following the tenant's calendar_name_display setting:
      - 'first_name': always just the first name.
      - 'first_last_initial': always first name + last initial.
      - 'auto' (default): first name only, but if two people in this
        SAME group share a first name, add their last initial to both
        so they're told apart - only for the ones that actually clash.
    Falls back to username for anyone with no first name set.
    """
    mode = getattr(tenant, "calendar_name_display", "auto") if tenant else "auto"
    users = list(users)

    def base_name(u):
        return u.first_name.strip() or u.username

    def with_initial(u):
        name = base_name(u)
        if u.first_name.strip() and u.last_name.strip():
            return f"{name} {u.last_name.strip()[0].upper()}"
        return name

    if mode == "first_name":
        return {u.id: base_name(u) for u in users}
    if mode == "first_last_initial":
        return {u.id: with_initial(u) for u in users}

    # auto: only disambiguate first names that actually clash in this group
    from collections import Counter
    first_name_counts = Counter(base_name(u).lower() for u in users)
    result = {}
    for u in users:
        if first_name_counts[base_name(u).lower()] > 1:
            result[u.id] = with_initial(u)
        else:
            result[u.id] = base_name(u)
    return result
