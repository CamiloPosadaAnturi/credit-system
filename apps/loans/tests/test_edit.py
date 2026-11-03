"""Edit a loan in place: same reference, schedule rebuilt, payments re-applied."""
import datetime as dt
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.core.dates import today_local
from apps.core.errors import LoanError
from apps.core.factories import create_business, create_customer, create_loan, create_user
from apps.loans import services
from apps.loans.models import Loan, LoanStatus
from apps.payments import services as payment_services
from apps.users.models import Role


class EditLoanTests(TestCase):
    def setUp(self):
        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [self.business])
        self.customer = create_customer(self.business)

    def edit(self, loan, **changes):
        data = {"principal": loan.principal, "installment_count": loan.installment_count,
                "frequency": loan.payment_frequency,
                "first_payment_date": loan.first_payment_date}
        data.update(changes)
        return services.update_loan(loan, self.admin, **data)

    def test_edit_recomputes_terms_and_keeps_the_reference(self):
        loan = create_loan(self.customer, self.admin, Decimal("1000"), 4)
        reference = loan.reference
        self.edit(loan, principal=Decimal("2000"), installment_count=5)
        loan.refresh_from_db()
        self.assertEqual(loan.reference, reference)
        self.assertEqual(Loan.objects.count(), 1)
        self.assertEqual(loan.total_interest, Decimal("800.00"))
        self.assertEqual(loan.total_payable, Decimal("2800.00"))
        self.assertEqual(loan.outstanding_balance, Decimal("2800.00"))
        self.assertEqual(loan.installments.count(), 5)

    def test_payments_are_applied_again(self):
        loan = create_loan(self.customer, self.admin, Decimal("1000"), 4)
        payment_services.register_payment(loan=loan, amount=Decimal("350"), user=self.admin)
        self.edit(loan, installment_count=2)
        loan.refresh_from_db()
        self.assertEqual(loan.installments.count(), 2)
        self.assertEqual(loan.total_paid, Decimal("350.00"))
        self.assertEqual(loan.outstanding_balance, Decimal("1050.00"))
        first = loan.installments.order_by("number").first()
        self.assertEqual(first.amount_paid, Decimal("350.00"))

    def test_cannot_reduce_below_what_was_paid(self):
        loan = create_loan(self.customer, self.admin, Decimal("1000"), 4)
        payment_services.register_payment(loan=loan, amount=Decimal("700"), user=self.admin)
        with self.assertRaises(LoanError):
            self.edit(loan, principal=Decimal("100"))

    def test_cancelled_loans_are_not_edited(self):
        loan = create_loan(self.customer, self.admin)
        services.cancel_loan(loan, self.admin, "Mistake")
        with self.assertRaises(LoanError):
            self.edit(loan, principal=Decimal("500"))

    def test_edit_view(self):
        loan = create_loan(self.customer, self.admin, Decimal("1000"), 4)
        self.client.force_login(self.admin)
        url = reverse("loans:edit", args=[loan.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, {
            "principal": "1500", "payment_frequency": "weekly", "installment_count": "3",
            "first_payment_date": (today_local() + dt.timedelta(days=7)).isoformat(),
            "application_date": today_local().isoformat(), "notes": "",
        })
        self.assertRedirects(response, loan.get_absolute_url())
        loan.refresh_from_db()
        self.assertEqual(loan.principal, Decimal("1500.00"))
        self.assertEqual(loan.installment_count, 3)
        self.assertEqual(loan.status, LoanStatus.ACTIVE)
        detail = self.client.get(loan.get_absolute_url()).content.decode()
        self.assertIn(url, detail)
        self.assertNotIn("restructure", detail)
