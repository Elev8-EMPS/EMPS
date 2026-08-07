from .utils import get_open_todo_count, can_view_financials, can_view_confidential


def todo_badge(request):
    """Makes the open to-do count and permission flags available in
    every template, since the sidebar and several pages need them
    regardless of which view is being rendered."""
    if hasattr(request, "user") and request.user.is_authenticated:
        return {
            "my_open_todos_count": get_open_todo_count(request.user),
            "can_view_financials": can_view_financials(request.user),
            "can_manage_org": can_view_confidential(request.user),
        }
    return {"my_open_todos_count": 0, "can_view_financials": False, "can_manage_org": False}
