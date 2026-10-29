"""Notification bell: notifications for everyone are shown, in one query."""
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.core.factories import create_business, create_user
from apps.notifications.context_processors import pending_notifications
from apps.notifications.services import create_notification, notifications_for
from apps.users.models import Role


class NotificationBellTests(TestCase):
    def setUp(self):
        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [self.business])
        self.other = create_user("other", Role.MANAGER, [self.business])

    def test_notifications_for_everyone_are_visible(self):
        create_notification(business=self.business, title="Loan settled")  # user=None
        create_notification(business=self.business, title="Only for other", user=self.other)
        titles = [n.title for n in notifications_for(self.admin)]
        self.assertEqual(titles, ["Loan settled"])

    def test_bell_uses_one_query_when_not_full(self):
        create_notification(business=self.business, title="Loan settled")
        request = type("Request", (), {"user": self.admin})()
        with CaptureQueriesContext(connection) as ctx:
            context = pending_notifications(request)
        self.assertEqual(len(ctx), 1)
        self.assertEqual(context["pending_notifications_count"], 1)

    def test_full_bell_still_counts_everything(self):
        for index in range(12):
            create_notification(business=self.business, title=f"N{index}")
        request = type("Request", (), {"user": self.admin})()
        context = pending_notifications(request)
        self.assertEqual(len(context["pending_notifications"]), 10)
        self.assertEqual(context["pending_notifications_count"], 12)

    def test_page_shows_the_badge(self):
        create_notification(business=self.business, title="Loan settled")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("customers:list"))
        self.assertContains(response, "Loan settled")
