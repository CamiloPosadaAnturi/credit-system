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
    queryset = queryset.filter(user__in=[user, None])
    if unread_only:
        queryset = queryset.filter(is_read=False)
    return queryset
