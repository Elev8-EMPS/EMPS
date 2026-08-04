from .utils import get_open_todo_count, can_view_financials


def todo_badge(request):
    """Makes the open to-do count and financial-visibility permission
    available in every template, since the sidebar and several pages
    need them regardless of which view is being rendered."""
    if hasattr(request, "user") and request.user.is_authenticated:
        return {
            "my_open_todos_count": get_open_todo_count(request.user),
            "can_view_financials": can_view_financials(request.user),
        }
    return {"my_open_todos_count": 0, "can_view_financials": False}
