"""Tests for the management commands."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.businesses.models import Business
from apps.customers.models import Customer
from apps.loans.models import Loan, LoanStatus
from apps.payments.models import Payment
from apps.users.models import User


class LoadDemoDataTests(TestCase):
    def test_loads_a_coherent_dataset(self):
        output = StringIO()
        call_command("load_demo_data", stdout=output)

        self.assertEqual(Business.objects.count(), 1)
        self.assertEqual(Customer.objects.count(), 20)
        self.assertEqual(User.objects.count(), 4)
        self.assertGreater(Loan.objects.count(), 15)
        self.assertGreater(Payment.objects.count(), 5)

        self.assertTrue(Loan.objects.filter(status=LoanStatus.SETTLED).exists())
        self.assertTrue(Loan.objects.filter(status=LoanStatus.PAST_DUE).exists())
        self.assertTrue(Loan.objects.filter(status=LoanStatus.PENDING).exists())
        self.assertIn("Demo data loaded", output.getvalue())

    def test_balances_match_the_allocations(self):
        """Every loan must be rebuildable from its payment allocations."""
        from apps.payments.models import PaymentAllocation, PaymentStatus

        call_command("load_demo_data", stdout=StringIO())
        for loan in Loan.objects.disbursed():
            allocated = sum(
                allocation.amount
                for allocation in PaymentAllocation.objects.filter(
                    installment__loan=loan, payment__status=PaymentStatus.CONFIRMED)
            )
            self.assertEqual(
                loan.outstanding_balance, max(loan.total_payable - allocated, 0),
                f"The balance of {loan.reference} does not match its allocations.")
            self.assertEqual(
                sum(item.scheduled_amount for item in loan.installments.all()),
                loan.total_payable)
