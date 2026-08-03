from .utils import get_open_todo_count


def todo_badge(request):
    """Makes the open to-do count available in every template, so the
    sidebar badge shows up no matter which page you're on."""
    if hasattr(request, "user") and request.user.is_authenticated:
        return {"my_open_todos_count": get_open_todo_count(request.user)}
    return {"my_open_todos_count": 0}
