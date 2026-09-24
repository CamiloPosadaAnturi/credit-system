from apps.notifications.services import notifications_for


def pending_notifications(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    return {
        "pending_notifications": notifications_for(user)[:10],
        "pending_notifications_count": notifications_for(user).count(),
    }
