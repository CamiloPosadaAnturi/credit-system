from apps.users import permissions


def user_businesses(request):
    """Expose the user's businesses and permissions to every template.

    ``user_permissions`` is a {action: bool} dict so templates can hide menu
    entries. Hiding is NOT a replacement for server-side checks: every view
    verifies the permission again.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    return {
        "user_businesses": permissions.allowed_businesses(user).active(),
        "user_permissions": {
            action: permissions.can(user, action) for action in permissions.MATRIX
        },
    }
