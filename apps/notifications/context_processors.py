from apps.notifications.services import notifications_for

BELL_SIZE = 10


def pending_notifications(request):
    """Unread notifications for the bell, in ONE query in the usual case.

    The count only needs a second query when the bell is full.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    latest = list(notifications_for(user)[:BELL_SIZE])
    count = len(latest) if len(latest) < BELL_SIZE else notifications_for(user).count()
    return {
        "pending_notifications": latest,
        "pending_notifications_count": count,
    }
