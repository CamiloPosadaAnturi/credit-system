"""Tests for registering and allocating payments."""
import datetime as dt
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.core.dates import today_local
from apps.core.errors import PaymentError
from apps.core.factories import (
    create_business,
    create_customer,
    create_loan,
    create_user,
)
from apps.loans.models import InstallmentStatus, LoanStatus
from apps.payments import services
from apps.payments.models import Payment, PaymentKind, PaymentMethod, PaymentStatus
from apps.users.models import Role


class PaymentTestCase(TestCase):
    def setUp(self):
        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [self.business])
        self.customer = create_customer(self.business)
        # 1,000 principal + 400 interest = 1,400 in 4 installments of 350.
        self.loan = create_loan(self.customer, self.admin, Decimal("1000"), 4)


class AllocationTests(PaymentTestCase):
    def test_partial_payment_updates_installment_and_balance(self):
        services.register_payment(loan=self.loan, amount=Decimal("200"), user=self.admin)
        self.loan.refresh_from_db()
        installment = self.loan.installments.first()
        self.assertEqual(installment.amount_paid, Decimal("200.00"))
        self.assertEqual(installment.status, InstallmentStatus.PARTIAL)
        self.assertEqual(self.loan.outstanding_balance, Decimal("1200.00"))

    def test_exact_installment_payment_marks_it_paid(self):
        services.register_payment(loan=self.loan, amount=Decimal("350"), user=self.admin)
        installment = self.loan.installments.first()
        installment.refresh_from_db()
        self.assertEqual(installment.status, InstallmentStatus.PAID)
        self.assertIsNotNone(installment.settled_on)

    def test_payment_covers_several_installments_in_order(self):
        services.register_payment(loan=self.loan, amount=Decimal("800"), user=self.admin)
        installments = list(self.loan.installments.order_by("number"))
        self.assertEqual(installments[0].status, InstallmentStatus.PAID)
        self.assertEqual(installments[1].status, InstallmentStatus.PAID)
        self.assertEqual(installments[2].amount_paid, Decimal("100.00"))
        self.assertEqual(installments[3].amount_paid, Decimal("0.00"))

    def test_principal_and_interest_split(self):
        """Within an installment the interest is covered first, then principal."""
        payment = services.register_payment(
            loan=self.loan, amount=Decimal("350"), user=self.admin)
        allocation = payment.allocations.get()
        self.assertEqual(allocation.interest, Decimal("100.00"))
        self.assertEqual(allocation.principal, Decimal("250.00"))
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.interest_paid, Decimal("100.00"))
        self.assertEqual(self.loan.principal_paid, Decimal("250.00"))

    def test_payment_smaller_than_the_interest_only_covers_interest(self):
        payment = services.register_payment(
            loan=self.loan, amount=Decimal("60"), user=self.admin)
        allocation = payment.allocations.get()
        self.assertEqual(allocation.interest, Decimal("60.00"))
        self.assertEqual(allocation.principal, Decimal("0.00"))

    def test_full_payment_settles_the_loan(self):
        services.register_payment(loan=self.loan, amount=Decimal("1400"), user=self.admin)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.outstanding_balance, Decimal("0.00"))
        self.assertEqual(self.loan.status, LoanStatus.SETTLED)
        self.assertEqual(self.loan.principal_paid, Decimal("1000.00"))
        self.assertEqual(self.loan.interest_paid, Decimal("400.00"))
        self.assertFalse(
            self.loan.installments.exclude(status=InstallmentStatus.PAID).exists())

    def test_interest_is_not_recomputed_on_payment(self):
        for _ in range(4):
            services.register_payment(loan=self.loan, amount=Decimal("350"),
                                      user=self.admin, force_duplicate=True)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.total_interest, Decimal("400.00"))
        self.assertEqual(self.loan.total_payable, Decimal("1400.00"))
        self.assertEqual(self.loan.outstanding_balance, Decimal("0.00"))

    def test_zero_or_negative_amount(self):
        for amount in [Decimal("0"), Decimal("-100")]:
            with self.subTest(amount=amount):
                with self.assertRaises(PaymentError):
                    services.register_payment(loan=self.loan, amount=amount,
                                              user=self.admin)

    def test_payment_above_the_balance_needs_authorization(self):
        with self.assertRaises(PaymentError):
            services.register_payment(loan=self.loan, amount=Decimal("2000"),
                                      user=self.admin)
        payment = services.register_payment(loan=self.loan, amount=Decimal("2000"),
                                            user=self.admin, allow_overpayment=True)
        self.assertEqual(payment.allocated_amount, Decimal("1400.00"))
        self.assertEqual(payment.overpayment, Decimal("600.00"))

    def test_cannot_pay_a_loan_that_is_not_live(self):
        services.register_payment(loan=self.loan, amount=Decimal("1400"), user=self.admin)
        self.loan.refresh_from_db()
        with self.assertRaises(PaymentError):
            services.register_payment(loan=self.loan, amount=Decimal("50"),
                                      user=self.admin)


class DuplicateTests(PaymentTestCase):
    def test_idempotency_key_prevents_double_registration(self):
        first = services.register_payment(
            loan=self.loan, amount=Decimal("350"), user=self.admin,
            idempotency_key="abc123")
        second = services.register_payment(
            loan=self.loan, amount=Decimal("350"), user=self.admin,
            idempotency_key="abc123")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Payment.objects.count(), 1)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.outstanding_balance, Decimal("1050.00"))

    def test_identical_immediate_payment_is_blocked(self):
        services.register_payment(loan=self.loan, amount=Decimal("350"), user=self.admin)
        with self.assertRaises(PaymentError):
            services.register_payment(loan=self.loan, amount=Decimal("350"),
                                      user=self.admin)

    def test_identical_payment_can_be_confirmed_explicitly(self):
        services.register_payment(loan=self.loan, amount=Decimal("350"), user=self.admin)
        services.register_payment(loan=self.loan, amount=Decimal("350"),
                                  user=self.admin, force_duplicate=True)
        self.assertEqual(Payment.objects.confirmed().count(), 2)


class ReversalTests(PaymentTestCase):
    def test_reversal_restores_the_balance_and_keeps_the_record(self):
        payment = services.register_payment(
            loan=self.loan, amount=Decimal("700"), user=self.admin)
        services.reverse_payment(payment, self.admin, "Deposit never cleared")
        payment.refresh_from_db()
        self.loan.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.REVERSED)
        self.assertEqual(payment.reversal_reason, "Deposit never cleared")
        self.assertEqual(Payment.objects.count(), 1)  # never deleted
        self.assertEqual(self.loan.outstanding_balance, Decimal("1400.00"))
        self.assertEqual(self.loan.installments.first().amount_paid, Decimal("0.00"))

    def test_reversal_brings_a_settled_loan_back_to_live(self):
        payment = services.register_payment(
            loan=self.loan, amount=Decimal("1400"), user=self.admin)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.status, LoanStatus.SETTLED)
        services.reverse_payment(payment, self.admin, "Data entry error")
        self.loan.refresh_from_db()
        self.assertIn(self.loan.status, [LoanStatus.ACTIVE, LoanStatus.PAST_DUE])
        self.assertEqual(self.loan.outstanding_balance, Decimal("1400.00"))

    def test_reversal_requires_a_reason_and_cannot_repeat(self):
        payment = services.register_payment(
            loan=self.loan, amount=Decimal("350"), user=self.admin)
        with self.assertRaises(PaymentError):
            services.reverse_payment(payment, self.admin, "")
        services.reverse_payment(payment, self.admin, "Valid reason")
        with self.assertRaises(PaymentError):
            services.reverse_payment(payment, self.admin, "Again")


class OverdueAllocationTests(TestCase):
    def setUp(self):
        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [self.business])
        self.customer = create_customer(self.business)
        self.loan = create_loan(
            self.customer, self.admin, Decimal("1000"), 4,
            first_payment_date=today_local() - dt.timedelta(days=14))

    def test_payment_covers_the_oldest_overdue_installment_first(self):
        payment = services.register_payment(
            loan=self.loan, amount=Decimal("350"), user=self.admin)
        allocation = payment.allocations.get()
        self.assertEqual(allocation.installment.number, 1)

    def test_overdue_balance_shrinks_with_the_payment(self):
        initial = services.overdue_balance(self.loan)
        self.assertEqual(initial, Decimal("700.00"))  # installments 1 and 2 are due
        services.register_payment(loan=self.loan, amount=Decimal("350"), user=self.admin)
        self.assertEqual(services.overdue_balance(self.loan), Decimal("350.00"))


class EarlyPayoffTests(PaymentTestCase):
    def test_without_discount_the_full_balance_is_paid(self):
        quote = services.early_payoff_quote(self.loan)
        self.assertEqual(quote["discount"], Decimal("0.00"))
        self.assertEqual(quote["payoff_amount"], Decimal("1400.00"))
        services.settle_early(self.loan, self.admin)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.status, LoanStatus.SETTLED)
        self.assertEqual(self.loan.outstanding_balance, Decimal("0.00"))

    def test_with_discount_a_write_off_is_recorded(self):
        self.business.early_payoff_discount = Decimal("0.5000")
        self.business.save()
        loan = create_loan(
            self.customer, self.admin, Decimal("1000"), 4,
            first_payment_date=today_local() + dt.timedelta(days=7))
        quote = services.early_payoff_quote(loan)
        # All four installments fall in the future: unearned interest = 400.
        self.assertEqual(quote["unearned_interest"], Decimal("400.00"))
        self.assertEqual(quote["discount"], Decimal("200.00"))
        self.assertEqual(quote["payoff_amount"], Decimal("1200.00"))

        services.settle_early(loan, self.admin)
        loan.refresh_from_db()
        self.assertEqual(loan.status, LoanStatus.SETTLED)
        self.assertEqual(loan.outstanding_balance, Decimal("0.00"))
        write_off = loan.payments.get(kind=PaymentKind.WRITE_OFF)
        self.assertEqual(write_off.amount, Decimal("200.00"))
        # The cash actually received is 1,200, not 1,400:
        # a write-off does not count as money collected.
        received = sum(payment.amount for payment in loan.payments.cash_received())
        self.assertEqual(received, Decimal("1200.00"))

    def test_business_that_does_not_allow_payoff(self):
        self.business.allows_early_payoff = False
        self.business.save()
        with self.assertRaises(PaymentError):
            services.settle_early(self.loan, self.admin)


class ReferenceAndMethodTests(PaymentTestCase):
    def test_reference_is_sequential_per_business(self):
        first = services.register_payment(loan=self.loan, amount=Decimal("100"),
                                          user=self.admin)
        second = services.register_payment(loan=self.loan, amount=Decimal("150"),
                                           user=self.admin)
        self.assertTrue(first.reference.startswith("PY-"))
        self.assertEqual(int(second.reference.split("-")[-1]),
                         int(first.reference.split("-")[-1]) + 1)

    def test_payment_methods(self):
        payment = services.register_payment(
            loan=self.loan, amount=Decimal("100"), user=self.admin,
            method=PaymentMethod.TRANSFER, external_reference="REF-001",
            paid_at=timezone.now())
        self.assertEqual(payment.method, PaymentMethod.TRANSFER)
        self.assertEqual(payment.external_reference, "REF-001")
