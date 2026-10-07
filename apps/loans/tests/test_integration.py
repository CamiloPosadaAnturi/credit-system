"""Integration tests: from loan creation to settlement."""
import datetime as dt
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.core.dates import today_local
from apps.core.factories import create_business, create_customer, create_user
from apps.loans import services as loan_services
from apps.loans.models import InstallmentStatus, Loan, LoanStatus
from apps.payments import services as payment_services
from apps.payments.models import PaymentAllocation, PaymentStatus
from apps.users.models import Role


class FullFlowTests(TestCase):
    """1,000 MXN at 40%, 4 weekly installments of 350, paid one by one."""

    def setUp(self):
        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [self.business])
        self.collector = create_user("collector", Role.COLLECTOR, [self.business])
        self.customer = create_customer(self.business, collector=self.collector)

    def test_from_creation_to_settlement(self):
        start = today_local() - dt.timedelta(days=21)
        loan = loan_services.create_loan(
            customer=self.customer, business=self.business, principal=Decimal("1000"),
            installment_count=4, frequency="weekly", first_payment_date=start,
            user=self.admin, collector=self.collector)

        self.assertEqual(loan.status, LoanStatus.PENDING)
        self.assertEqual(loan.total_payable, Decimal("1400.00"))

        loan_services.approve_loan(loan, self.admin)
        loan.refresh_from_db()
        loan_services.disburse_loan(loan, self.admin)
        loan.refresh_from_db()
        self.assertEqual(loan.status, LoanStatus.PAST_DUE)  # 3 installments already due

        expected_balances = ["1050.00", "700.00", "350.00", "0.00"]
        for index, expected in enumerate(expected_balances):
            payment_services.register_payment(
                loan=loan, amount=Decimal("350"), user=self.collector,
                collector=self.collector, force_duplicate=True)
            loan.refresh_from_db()
            self.assertEqual(loan.outstanding_balance, Decimal(expected),
                             f"wrong balance after payment {index + 1}")

        self.assertEqual(loan.status, LoanStatus.SETTLED)
        self.assertEqual(loan.principal_paid, Decimal("1000.00"))
        self.assertEqual(loan.interest_paid, Decimal("400.00"))
        self.assertEqual(
            loan.installments.filter(status=InstallmentStatus.PAID).count(), 4)

        # The balance can be rebuilt from the payment allocations.
        allocated = sum(
            allocation.amount for allocation in PaymentAllocation.objects.filter(
                installment__loan=loan, payment__status=PaymentStatus.CONFIRMED))
        self.assertEqual(allocated, loan.total_payable)

    def test_irregular_payments_and_a_reversal(self):
        loan = loan_services.create_loan(
            customer=self.customer, business=self.business, principal=Decimal("3000"),
            installment_count=6, frequency="biweekly",
            first_payment_date=today_local(), user=self.admin)
        loan_services.approve_loan(loan, self.admin)
        loan.refresh_from_db()
        loan_services.disburse_loan(loan, self.admin)
        loan.refresh_from_db()
        self.assertEqual(loan.total_payable, Decimal("4200.00"))
        self.assertEqual(loan.installment_amount, Decimal("700.00"))

        payment_services.register_payment(loan=loan, amount=Decimal("250"),
                                          user=self.admin)
        payment_services.register_payment(loan=loan, amount=Decimal("1000"),
                                          user=self.admin)
        bad_payment = payment_services.register_payment(
            loan=loan, amount=Decimal("500"), user=self.admin)
        loan.refresh_from_db()
        self.assertEqual(loan.outstanding_balance, Decimal("2450.00"))

        payment_services.reverse_payment(bad_payment, self.admin, "Bounced cheque")
        loan.refresh_from_db()
        self.assertEqual(loan.outstanding_balance, Decimal("2950.00"))
        self.assertEqual(loan.total_paid, Decimal("1250.00"))

        payment_services.settle_early(loan, self.admin)
        loan.refresh_from_db()
        self.assertEqual(loan.status, LoanStatus.SETTLED)
        self.assertEqual(loan.outstanding_balance, Decimal("0.00"))


class MainScreenTests(TestCase):
    """Check the main screens answer 200 with real data."""

    def setUp(self):
        from apps.core.factories import create_loan

        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [self.business])
        self.customer = create_customer(self.business)
        self.loan = create_loan(self.customer, self.admin, Decimal("2000"), 4)
        payment_services.register_payment(loan=self.loan, amount=Decimal("700"),
                                          user=self.admin)
        self.client.force_login(self.admin)

    def test_screens(self):
        routes = [
            reverse("dashboard:home"),
            reverse("businesses:settings"),
            reverse("businesses:settings_edit"),
            reverse("customers:list"),
            reverse("customers:detail", args=[self.customer.pk]),
            reverse("loans:list"),
            reverse("loans:detail", args=[self.loan.pk]),
            reverse("loans:schedule", args=[self.loan.pk]),
            reverse("payments:list"),
            reverse("payments:register", args=[self.loan.pk]),
            reverse("payments:payoff", args=[self.loan.pk]),
            reverse("collections:board"),
            reverse("collections:my_portfolio"),
            reverse("collections:actions"),
            reverse("collections:log_action", args=[self.loan.pk]),
            reverse("reports:catalog"),
            reverse("audit:list"),
            reverse("notifications:list"),
            reverse("users:list"),
            reverse("users:profile"),
        ]
        for route in routes:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 200)

    def test_every_report_answers(self):
        from apps.reports.definitions import REPORTS

        for key in REPORTS:
            with self.subTest(report=key):
                response = self.client.get(reverse("reports:detail", args=[key]))
                self.assertEqual(response.status_code, 200)

    def test_csv_and_excel_export(self):
        csv_response = self.client.get(
            reverse("reports:detail", args=["loans_granted"]), {"format": "csv"})
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("text/csv", csv_response["Content-Type"])

        excel_response = self.client.get(
            reverse("reports:detail", args=["portfolio"]), {"format": "excel"})
        self.assertEqual(excel_response.status_code, 200)
        self.assertIn("spreadsheetml", excel_response["Content-Type"])

    def test_registering_a_payment_through_the_view(self):
        response = self.client.post(
            reverse("payments:register", args=[self.loan.pk]),
            {"amount": "500", "method": "cash", "idempotency_key": "form-1"},
            follow=True)
        self.assertEqual(response.status_code, 200)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.outstanding_balance, Decimal("1600.00"))

        # Re-submitting the same form (same key) does not duplicate the payment.
        self.client.post(
            reverse("payments:register", args=[self.loan.pk]),
            {"amount": "500", "method": "cash", "idempotency_key": "form-1"},
            follow=True)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.outstanding_balance, Decimal("1600.00"))
        self.assertEqual(self.loan.payments.confirmed().count(), 2)

    def test_creating_a_loan_through_the_view(self):
        data = {
            "customer": self.customer.pk,
            "application_date": today_local().isoformat(),
            "principal": "5000", "interest_mode": "flat_on_principal",
            "interest_rate": "0.40", "rate_period": "contract",
            "payment_frequency": "weekly", "installment_count": 10,
            "first_payment_date": today_local().isoformat(),
        }
        # First submit: confirmation screen, nothing created yet.
        preview = self.client.post(reverse("loans:create"), data)
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "Confirm")
        self.assertEqual(Loan.objects.filter(principal=Decimal("5000")).count(), 0)

        data["confirm"] = "1"
        final = self.client.post(reverse("loans:create"), data, follow=True)
        self.assertEqual(final.status_code, 200)
        loan = Loan.objects.get(principal=Decimal("5000"))
        self.assertEqual(loan.business, self.business)
        self.assertEqual(loan.total_interest, Decimal("2000.00"))
        self.assertEqual(loan.total_payable, Decimal("7000.00"))
        self.assertEqual(loan.installments.count(), 10)
