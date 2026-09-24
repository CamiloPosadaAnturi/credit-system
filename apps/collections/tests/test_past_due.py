"""Tests for portfolio classification and past-due calculations."""
import datetime as dt
from decimal import Decimal

from django.test import TestCase

from apps.collections import services
from apps.core.dates import today_local
from apps.core.factories import (
    create_business,
    create_customer,
    create_loan,
    create_user,
)
from apps.loans.models import Loan
from apps.payments.services import register_payment
from apps.users.models import Role


class PastDueTests(TestCase):
    def setUp(self):
        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [self.business])
        self.customer = create_customer(self.business)
        self.today = today_local()

    def build(self, days_ago=0, principal=Decimal("1000"), installments=4):
        return create_loan(
            self.customer, self.admin, principal, installments,
            first_payment_date=self.today - dt.timedelta(days=days_ago))

    def test_installments_due_today(self):
        self.build(days_ago=0)
        self.assertEqual(
            services.installments_due_on(Loan.objects.all(), self.today).count(), 1)

    def test_overdue_installments_and_balance(self):
        self.build(days_ago=14)  # installments 1 and 2 are overdue (day 0 and day 7)
        overdue = services.overdue_installments(Loan.objects.all(), self.today)
        self.assertEqual(overdue.count(), 2)
        self.assertEqual(
            services.overdue_balance_for(Loan.objects.all(), self.today),
            Decimal("700.00"))

    def test_days_past_due_of_installment_and_loan(self):
        loan = self.build(days_ago=20)
        oldest = loan.installments.order_by("number").first()
        self.assertEqual(oldest.days_past_due, 20)
        self.assertEqual(loan.days_past_due, 20)  # the loan takes its oldest installment

    def test_a_paid_installment_is_not_counted_as_overdue(self):
        loan = self.build(days_ago=14)
        register_payment(loan=loan, amount=Decimal("350"), user=self.admin)
        loan.refresh_from_db()
        self.assertEqual(
            services.overdue_installments(Loan.objects.all(), self.today).count(), 1)
        self.assertEqual(loan.days_past_due, 7)

    def test_overdue_balance_versus_total_balance(self):
        loan = self.build(days_ago=14)
        self.assertEqual(loan.overdue_balance, Decimal("700.00"))
        self.assertEqual(loan.outstanding_balance, Decimal("1400.00"))

    def test_minimum_days_filter(self):
        self.build(days_ago=14)
        self.assertEqual(
            services.overdue_installments(
                Loan.objects.all(), self.today, min_days=10).count(), 1)
        self.assertEqual(
            services.overdue_installments(
                Loan.objects.all(), self.today, min_days=30).count(), 0)

    def test_portfolio_breakdown(self):
        self.build(days_ago=14)
        self.build(days_ago=0)
        breakdown = services.portfolio_breakdown(Loan.objects.all(), self.today)
        self.assertEqual(breakdown["live_loans"], 2)
        self.assertEqual(breakdown["due_today"], 2)
        self.assertEqual(breakdown["overdue"], 2)
        self.assertEqual(breakdown["total_balance"], Decimal("2800.00"))
        self.assertEqual(breakdown["customers_with_several_loans"], 1)

    def test_no_late_fee_without_a_policy(self):
        loan = self.build(days_ago=30)
        self.assertEqual(services.late_fee_estimate(loan, self.today), Decimal("0.00"))

    def test_late_fee_only_when_configured(self):
        self.business.charges_late_fee = True
        self.business.late_fee_rate = Decimal("0.0100")  # 1% per day on the overdue balance
        self.business.save()
        loan = self.build(days_ago=7)
        loan.refresh_from_db()
        # Installment 1 (350) with 7 days past due: 350 * 0.01 * 7 = 24.50
        self.assertEqual(services.late_fee_estimate(loan, self.today), Decimal("24.50"))

    def test_past_due_summary(self):
        loan = self.build(days_ago=21)
        rows = services.past_due_summary(Loan.objects.all(), self.today)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["loan"], loan)
        self.assertEqual(row["overdue_count"], 3)
        self.assertEqual(row["overdue_balance"], Decimal("1050.00"))
        self.assertEqual(row["days_past_due"], 21)
