from django.db import models

# Every role's starting point for the four permission domains. A person's
# individual profile can override any one of these on the Manage > Users
# screen; blank ("") on the profile means "use whatever's here".
ROLE_DEFAULTS = {
    "company_admin": {"fees": "edit", "financials": "edit", "confidential": "edit", "company_admin": "edit"},
    "director": {"fees": "edit", "financials": "edit", "confidential": "edit", "company_admin": "edit"},
    "accounts": {"fees": "view", "financials": "edit", "confidential": "none", "company_admin": "none"},
    "project_manager": {"fees": "none", "financials": "none", "confidential": "none", "company_admin": "none"},
    "engineer": {"fees": "none", "financials": "none", "confidential": "none", "company_admin": "none"},
    "administration": {"fees": "none", "financials": "none", "confidential": "none", "company_admin": "none"},
    "external_consultant": {"fees": "none", "financials": "none", "confidential": "none", "company_admin": "none"},
    "client_user": {"fees": "none", "financials": "none", "confidential": "none", "company_admin": "none"},
    "read_only": {"fees": "none", "financials": "none", "confidential": "none", "company_admin": "none"},
}
NO_ACCESS = {"fees": "none", "financials": "none", "confidential": "none", "company_admin": "none"}


def get_user_role(user):
    if user.is_superuser:
        return "company_admin"
    profile = getattr(user, "profile", None)
    return profile.role if profile else ""


def get_access_level(user, domain):
    """The effective None/View/Edit level for `user` in one of the four
    permission domains ('fees', 'financials', 'confidential', 'company_admin'):
    superusers always get 'edit'; otherwise an explicit override on the
    person's profile wins, falling back to their role's default."""
    if user.is_superuser:
        return "edit"
    profile = getattr(user, "profile", None)
    if not profile:
        return "none"
    override = getattr(profile, f"{domain}_access", "")
    if override:
        return override
    return ROLE_DEFAULTS.get(profile.role, NO_ACCESS).get(domain, "none")


def can_view_financials(user):
    """Invoices, payments, fee amounts, WIP - View or Edit level on the
    Financials domain."""
    return get_access_level(user, "financials") in ("view", "edit")


def can_edit_financials(user):
    """Creating invoices, marking them issued, recording payments -
    requires Edit level specifically, not just View."""
    return get_access_level(user, "financials") == "edit"


def can_view_confidential(user):
    """Confidential-marked documents and (in future) the HR section -
    Edit is the only 'has access' level for this domain."""
    return get_access_level(user, "confidential") == "edit"


def can_view_proposals(user):
    """Fee Proposals - View or Edit level on the Fees domain."""
    return get_access_level(user, "fees") in ("view", "edit")


def can_edit_proposals(user):
    """Creating/modifying Fee Proposals - requires Edit level."""
    return get_access_level(user, "fees") == "edit"


def can_manage_company(user):
    """Creating/editing users, teams, and tenant settings; approving
    anyone's leave company-wide - Edit level on the Company Admin domain."""
    return get_access_level(user, "company_admin") == "edit"


def has_company_wide_scope(user):
    """Directors and anyone with Company Admin access see everything
    company-wide (all leave, all milestone reminders, the whole Manage
    hub); everyone else is scoped to their own team/direct reports.
    Deliberately separate from can_view_confidential - seeing the whole
    company's calendar isn't the same permission as seeing a
    confidential-marked document."""
    return get_user_role(user) == "director" or can_manage_company(user)


def can_view_fee_amounts(user):
    """Any dollar figure that originates from a fee proposal (a
    proposal's fee_amount, or a project's original_fee) - visible to
    anyone who can see financials OR proposals, since Accounts
    legitimately needs original_fee for reconciliation even without
    full proposal access."""
    return can_view_financials(user) or can_view_proposals(user)


def can_view_document(user, document):
    """Whether `user` may see this Document, based on its confidentiality
    level: 'confidential' documents (e.g. HR/company-confidential files)
    are Director/Admin only, 'fee_proposal' documents follow the same
    rule as Fee Proposals generally, and everything else (blank/standard)
    is visible to anyone who already has access to the project."""
    level = document.confidentiality
    if level == "confidential":
        return can_view_confidential(user)
    if level == "fee_proposal":
        return can_view_proposals(user)
    return True


def visible_document_filter(user):
    """A Q object for filtering a Document queryset down to only the
    documents `user` is allowed to see - the queryset-level equivalent
    of can_view_document, for list views."""
    q = models.Q(confidentiality="")
    if can_view_confidential(user):
        q |= models.Q(confidentiality="confidential")
    if can_view_proposals(user):
        q |= models.Q(confidentiality="fee_proposal")
    return q


def can_approve_leave(actor, target_user):
    """Who's allowed to approve/decline a leave or WFH request for
    `target_user`: Company Admin access, any Director, or their direct
    line manager specifically."""
    if get_user_role(actor) == "director" or can_manage_company(actor):
        return True
    profile = getattr(target_user, "profile", None)
    return bool(profile and profile.manager_id == actor.id)


def require_delete_reason(request):
    """Pulls a 'delete_reason' field out of a POST, stripped. Returns
    None (and leaves it to the caller to bail out with an error
    message) if nothing meaningful was given - this is the shared
    gate every in-app delete action should call before actually
    deleting anything."""
    reason = request.POST.get("delete_reason", "").strip()
    return reason or None


def diff_and_log_update(user, tenant, instance, before, reason):
    """Compares `before` (a dict of field_name -> old value, captured
    BEFORE the new values were applied) against `instance`'s current
    values for those same fields, and logs one audit entry naming
    which fields actually changed - skips logging entirely if nothing
    actually differs, so a resubmitted form with no real edit doesn't
    clutter the Activity Log. Returns the list of changed field names."""
    from .models import log_audit
    changed = [f for f, old in before.items() if getattr(instance, f) != old]
    if changed:
        log_audit(user, tenant, "update", instance, reason=reason, details=f"Changed: {', '.join(changed)}")
    return changed


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
