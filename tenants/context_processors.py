from .utils import get_open_todo_count, can_view_financials, can_manage_company, has_company_wide_scope, can_view_proposals, can_view_fee_amounts, get_user_tenant, get_dashboard_visibility


def _pending_leave_approvals_count(user, tenant):
    if not tenant:
        return 0
    from django.contrib.auth.models import User as AuthUser
    from leave.models import LeaveRequest
    if has_company_wide_scope(user):
        approvable_users = AuthUser.objects.filter(profile__tenant=tenant)
    else:
        approvable_users = AuthUser.objects.filter(profile__tenant=tenant, profile__manager=user)
    return LeaveRequest.objects.filter(tenant=tenant, status="pending", user__in=approvable_users).count()


def todo_badge(request):
    """Makes the open to-do count and permission flags available in
    every template, since the sidebar and several pages need them
    regardless of which view is being rendered."""
    if hasattr(request, "user") and request.user.is_authenticated:
        tenant = get_user_tenant(request)
        proposals_ok = can_view_proposals(request.user)
        return {
            "my_open_todos_count": get_open_todo_count(request.user),
            "can_view_financials": can_view_financials(request.user),
            "can_manage_org": can_manage_company(request.user),
            "can_view_proposals": proposals_ok,
            "can_view_fee_amounts": can_view_fee_amounts(request.user),
            # Nav link stays visible in 'responsible_for' mode too, since
            # those users can still reach a filtered proposal list.
            "show_proposals_nav": proposals_ok or get_dashboard_visibility(tenant) == "responsible_for",
            "pending_leave_approvals_count": _pending_leave_approvals_count(request.user, tenant),
        }
    return {
        "my_open_todos_count": 0,
        "can_view_financials": False,
        "can_manage_org": False,
        "can_view_proposals": False,
        "can_view_fee_amounts": False,
        "show_proposals_nav": False,
        "pending_leave_approvals_count": 0,
    }
