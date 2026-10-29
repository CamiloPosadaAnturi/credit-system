"""Collector performance: grouped queries give the same figures as the per-row rules."""
import datetime as dt
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.collections.models import CollectionAction
from apps.core.dates import today_local
from apps.core.factories import create_business, create_customer, create_loan, create_user
from apps.dashboard.services import collector_performance
from apps.payments.services import register_payment
from apps.users.models import Role


class CollectorPerformanceTests(TestCase):
    def setUp(self):
        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [self.business])
        self.ana = create_user("ana", Role.COLLECTOR, [self.business])
        self.beto = create_user("beto", Role.COLLECTOR, [self.business])
        self.loan = create_loan(create_customer(self.business), self.admin, Decimal("1000"), 4,
                                collector=self.ana,
                                first_payment_date=today_local() - dt.timedelta(days=14))
        before = timezone.now() - dt.timedelta(hours=2)

        def promise(amount):
            return CollectionAction.objects.create(
                loan=self.loan, customer=self.loan.customer, business=self.business,
                user=self.ana, performed_at=before, action_type="promise",
                promised_amount=Decimal(amount), promise_date=today_local())

        self.kept = promise("300")    # 350 paid after it -> kept
        self.broken = promise("500")  # 350 < 500 -> not kept
        CollectionAction.objects.create(  # plain call: an action, not a promise
            loan=self.loan, customer=self.loan.customer, business=self.business,
            user=self.ana, performed_at=before, action_type="call")
        register_payment(loan=self.loan, amount=Decimal("350"), user=self.ana)
        self.loan.refresh_from_db()

    def row(self, rows, collector):
        return next(row for row in rows if row["collector"] == collector)

    def test_figures_match_the_per_row_rules(self):
        rows = collector_performance(self.admin)
        ana = self.row(rows, self.ana)
        self.assertEqual(ana["actions"], 3)
        self.assertEqual(ana["promises"], 2)
        self.assertEqual(ana["promises_kept"],
                         sum(a.promise_kept for a in (self.kept, self.broken)))
        self.assertEqual(ana["promises_kept"], 1)
        self.assertEqual(ana["payments_received"], Decimal("350.00"))
        self.assertEqual(ana["payment_count"], 1)
        self.assertEqual(ana["assigned_loans"], 1)
        self.assertEqual(ana["assigned_portfolio"], self.loan.outstanding_balance)
        self.assertEqual(ana["overdue_balance"], self.loan.overdue_balance)
        beto = self.row(rows, self.beto)
        self.assertEqual((beto["actions"], beto["payments_received"], beto["assigned_loans"]),
                         (0, Decimal("0.00"), 0))

    def test_query_count_does_not_grow_with_collectors(self):
        with CaptureQueriesContext(connection) as two:
            collector_performance(self.admin)
        for index in range(5):
            create_user(f"extra{index}", Role.COLLECTOR, [self.business])
        with CaptureQueriesContext(connection) as seven:
            collector_performance(self.admin)
        self.assertEqual(len(two), len(seven))
