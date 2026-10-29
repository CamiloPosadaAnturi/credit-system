from django.db.models import Q

from apps.notifications.models import Notification, NotificationKind


def create_notification(*, business, title: str, message: str = "", url: str = "",
                        user=None, kind: str = NotificationKind.INFO):
    return Notification.objects.create(
        business=business, user=user, title=title[:150],
        message=message, url=url, kind=kind,
    )


def notifications_for(user, unread_only: bool = True):
    from apps.users import permissions

    queryset = Notification.objects.filter(
        business__in=permissions.allowed_businesses(user))
    # Addressed to this user or to everyone (user empty). Note: ``user__in``
    # with ``None`` would silently drop the "everyone" ones.
    queryset = queryset.filter(Q(user=user) | Q(user__isnull=True))
    if unread_only:
        queryset = queryset.filter(is_read=False)
    return queryset
