from .utils import get_open_todo_count, can_view_financials, can_view_confidential, can_view_proposals, can_view_fee_amounts, get_user_tenant, get_dashboard_visibility, get_user_role


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
            "can_manage_org": can_view_confidential(request.user),
            "can_view_proposals": proposals_ok,
            "can_view_fee_amounts": can_view_fee_amounts(request.user),
            # Nav link stays visible in 'responsible_for' mode too, since
            # those users can still reach a filtered proposal list.
            "show_proposals_nav": proposals_ok or get_dashboard_visibility(tenant) == "responsible_for",
            "can_access_management": get_user_role(request.user) in {"company_admin", "director", "project_manager"} or request.user.is_superuser,
        }
    return {
        "my_open_todos_count": 0,
        "can_view_financials": False,
        "can_manage_org": False,
        "can_view_proposals": False,
        "can_view_fee_amounts": False,
        "show_proposals_nav": False,
        "can_access_management": False,
    }
