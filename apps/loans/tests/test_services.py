"""Tests for the loan life cycle."""
import datetime as dt
from decimal import Decimal

from django.test import TestCase

from apps.core.dates import today_local
from apps.core.errors import LoanError
from apps.core.factories import (
    create_business,
    create_customer,
    create_loan,
    create_user,
)
from apps.loans import services
from apps.loans.models import Loan, LoanStatus
from apps.users.models import Role


class LifeCycleTests(TestCase):
    def setUp(self):
        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [self.business])
        self.customer = create_customer(self.business)

    def test_creation_computes_interest_and_schedule(self):
        loan = create_loan(self.customer, self.admin, Decimal("1000"), 4, disburse=False)
        self.assertEqual(loan.total_interest, Decimal("400.00"))
        self.assertEqual(loan.total_payable, Decimal("1400.00"))
        self.assertEqual(loan.installments.count(), 4)
        self.assertEqual(loan.installment_amount, Decimal("350.00"))
        self.assertEqual(loan.status, LoanStatus.PENDING)
        self.assertTrue(loan.reference.startswith("LN-"))

    def test_references_are_unique_and_sequential(self):
        first = create_loan(self.customer, self.admin, disburse=False)
        second = create_loan(self.customer, self.admin, disburse=False)
        self.assertNotEqual(first.reference, second.reference)
        self.assertEqual(int(second.reference.split("-")[-1]),
                         int(first.reference.split("-")[-1]) + 1)

    def test_approval_and_disbursement_flow(self):
        loan = create_loan(self.customer, self.admin, disburse=False)
        services.approve_loan(loan, self.admin)
        loan.refresh_from_db()
        self.assertEqual(loan.status, LoanStatus.APPROVED)
        self.assertEqual(loan.approval_date, today_local())

        services.disburse_loan(loan, self.admin)
        loan.refresh_from_db()
        self.assertEqual(loan.status, LoanStatus.ACTIVE)
        self.assertEqual(loan.outstanding_balance, Decimal("1400.00"))

    def test_cannot_disburse_without_approval(self):
        loan = create_loan(self.customer, self.admin, disburse=False)
        with self.assertRaises(LoanError):
            services.disburse_loan(loan, self.admin)

    def test_disbursed_loan_is_not_editable(self):
        loan = create_loan(self.customer, self.admin)
        self.assertFalse(loan.is_editable)
        with self.assertRaises(LoanError):
            services.recalculate_terms(loan, self.admin)

    def test_loan_rate_survives_a_business_rate_change(self):
        loan = create_loan(self.customer, self.admin)
        self.business.interest_rate = Decimal("0.6000")
        self.business.save()
        loan.refresh_from_db()
        self.assertEqual(loan.interest_rate, Decimal("0.4000"))
        self.assertEqual(loan.total_interest, Decimal("400.00"))

    def test_cancellation_requires_a_reason_and_no_payments(self):
        loan = create_loan(self.customer, self.admin)
        with self.assertRaises(LoanError):
            services.cancel_loan(loan, self.admin, "")
        services.cancel_loan(loan, self.admin, "Customer withdrew")
        loan.refresh_from_db()
        self.assertEqual(loan.status, LoanStatus.CANCELLED)
        self.assertEqual(loan.outstanding_balance, Decimal("0.00"))

    def test_restricted_customer_cannot_be_approved(self):
        self.customer.status = "restricted"
        self.customer.save()
        loan = create_loan(self.customer, self.admin, disburse=False)
        with self.assertRaises(LoanError):
            services.approve_loan(loan, self.admin)

    def test_customer_from_another_business(self):
        other = create_business("Other business")
        with self.assertRaises(LoanError):
            services.create_loan(
                customer=self.customer, business=other, principal=Decimal("1000"),
                installment_count=4, frequency="weekly",
                first_payment_date=today_local(), user=self.admin)

    def test_restructuring_keeps_the_history(self):
        from apps.payments.services import register_payment

        loan = create_loan(self.customer, self.admin, Decimal("1000"), 4)
        register_payment(loan=loan, amount=Decimal("350"), user=self.admin)
        loan.refresh_from_db()

        new_loan = services.restructure_loan(
            loan, self.admin, installment_count=6, frequency="weekly",
            first_payment_date=today_local() + dt.timedelta(days=7))

        loan.refresh_from_db()
        self.assertEqual(loan.status, LoanStatus.RESTRUCTURED)
        self.assertEqual(loan.outstanding_balance, Decimal("0.00"))
        self.assertEqual(loan.payments.count(), 1)  # the original payment is still there
        self.assertEqual(new_loan.principal, Decimal("1050.00"))
        self.assertEqual(new_loan.original_loan_id, loan.pk)
        self.assertEqual(new_loan.installment_count, 6)
        self.assertEqual(new_loan.status, LoanStatus.ACTIVE)

    def test_schedule_cannot_be_rebuilt_with_payments_applied(self):
        from apps.payments.services import register_payment

        loan = create_loan(self.customer, self.admin)
        register_payment(loan=loan, amount=Decimal("100"), user=self.admin)
        loan.refresh_from_db()
        with self.assertRaises(LoanError):
            services.generate_schedule(loan)


class DerivedStatusTests(TestCase):
    def setUp(self):
        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [self.business])
        self.customer = create_customer(self.business)

    def test_loan_with_an_overdue_installment_is_past_due(self):
        loan = create_loan(
            self.customer, self.admin, Decimal("1000"), 4,
            first_payment_date=today_local() - dt.timedelta(days=10))
        services.refresh_status(loan)
        loan.refresh_from_db()
        self.assertEqual(loan.status, LoanStatus.PAST_DUE)
        self.assertGreaterEqual(loan.days_past_due, 10)

    def test_grace_days_prevent_past_due(self):
        self.business.grace_days = 15
        self.business.save()
        loan = create_loan(
            self.customer, self.admin, Decimal("1000"), 4,
            first_payment_date=today_local() - dt.timedelta(days=10))
        services.refresh_status(loan)
        loan.refresh_from_db()
        self.assertEqual(loan.status, LoanStatus.ACTIVE)

    def test_bulk_status_refresh(self):
        loan = create_loan(self.customer, self.admin, Decimal("1000"), 4,
                           first_payment_date=today_local() - dt.timedelta(days=30))
        # Force a stale status to check the sweep fixes it.
        Loan.objects.filter(pk=loan.pk).update(status=LoanStatus.ACTIVE)
        self.assertEqual(services.refresh_statuses(Loan.objects.live()), 1)
        loan.refresh_from_db()
        self.assertEqual(loan.status, LoanStatus.PAST_DUE)
        # A second sweep changes nothing.
        self.assertEqual(services.refresh_statuses(Loan.objects.live()), 0)
