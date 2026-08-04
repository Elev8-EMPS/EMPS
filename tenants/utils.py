from django.db import models


FINANCIAL_ROLES = {"company_admin", "director", "accounts"}
CONFIDENTIAL_ROLES = {"company_admin", "director"}


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
