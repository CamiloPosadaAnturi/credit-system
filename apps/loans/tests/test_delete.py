"""Delete a loan (with its payments); only restructurings are kept."""
import datetime as dt
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.audit.models import AuditAction, AuditLog
from apps.core.dates import today_local
from apps.core.factories import create_business, create_customer, create_loan, create_user
from apps.loans import services
from apps.loans.models import Installment, Loan
from apps.payments.models import Payment, PaymentAllocation
from apps.payments.services import register_payment, reverse_payment
from apps.users.models import Role


class LoanDeleteTests(TestCase):
    def setUp(self):
        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [self.business])
        self.customer = create_customer(self.business, "Lucia", "Cabrera")
        self.loan = create_loan(self.customer, self.admin, Decimal("1000"), 4)
        self.url = reverse("loans:delete", args=[self.loan.pk])
        self.client.force_login(self.admin)

    def assertLoanExists(self, exists=True):
        self.assertEqual(Loan.objects.filter(pk=self.loan.pk).exists(), exists)

    def test_loan_without_payments_is_deleted_with_its_schedule(self):
        response = self.client.post(self.url)
        self.assertRedirects(response, self.customer.get_absolute_url())
        self.assertLoanExists(False)
        self.assertFalse(Installment.objects.filter(loan_id=self.loan.pk).exists())

    def test_deletion_is_audited(self):
        self.client.post(self.url)
        entry = AuditLog.objects.get(action=AuditAction.DELETE, model_name="Loan")
        self.assertEqual(entry.object_id, str(self.loan.pk))
        self.assertEqual(entry.data["reference"], self.loan.reference)
        self.assertEqual(entry.data["customer"], "Lucia Cabrera")

    def test_loan_with_payments_is_deleted_with_its_payments(self):
        payment = register_payment(loan=self.loan, amount=Decimal("300"), user=self.admin)
        response = self.client.post(self.url)
        self.assertRedirects(response, self.customer.get_absolute_url())
        self.assertLoanExists(False)
        self.assertFalse(Payment.objects.filter(pk=payment.pk).exists())
        self.assertFalse(PaymentAllocation.objects.filter(payment_id=payment.pk).exists())
        entry = AuditLog.objects.get(action=AuditAction.DELETE, model_name="Loan")
        self.assertEqual(entry.data["payments"][0]["reference"], payment.reference)
        self.assertEqual(entry.data["payments"][0]["amount"], "300.00")

    def test_loan_with_reversed_payments_is_deleted(self):
        payment = register_payment(loan=self.loan, amount=Decimal("300"), user=self.admin)
        reverse_payment(payment, self.admin, "Error de captura")
        self.assertIsNone(services.loan_deletion_blocker(self.loan))
        self.client.post(self.url)
        self.assertLoanExists(False)

    def test_restructured_loans_are_not_deleted(self):
        register_payment(loan=self.loan, amount=Decimal("300"), user=self.admin)
        self.loan.refresh_from_db()
        new_loan = services.restructure_loan(
            self.loan, self.admin, installment_count=4, frequency="weekly",
            first_payment_date=today_local() + dt.timedelta(days=7))
        self.client.post(reverse("loans:delete", args=[new_loan.pk]))
        self.assertTrue(Loan.objects.filter(pk=new_loan.pk).exists())
        self.assertIn("restructuring", services.loan_deletion_blocker(new_loan))

    def test_only_admins_can_delete(self):
        for role in (Role.MANAGER, Role.COLLECTOR, Role.VIEWER):
            self.client.force_login(create_user(f"user_{role}", role, [self.business]))
            self.assertEqual(self.client.post(self.url).status_code, 403)
        self.assertLoanExists()

    def test_get_only_shows_the_confirmation(self):
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, "loans/confirm_delete.html")
        self.assertLoanExists()

    def test_after_deleting_its_only_loan_the_customer_can_be_deleted(self):
        self.client.post(self.url)
        self.client.post(reverse("customers:delete", args=[self.customer.pk]))
        self.assertFalse(type(self.customer).objects.filter(pk=self.customer.pk).exists())

    def test_list_confirms_and_warns_about_the_payments(self):
        paid = create_loan(self.customer, self.admin, Decimal("500"), 4)
        register_payment(loan=paid, amount=Decimal("100"), user=self.admin)
        response = self.client.get(reverse("loans:list"))
        self.assertContains(response, 'id="deleteLoanModal"')
        self.assertContains(response, f'data-url="{self.url}"')
        self.assertContains(response, f'data-url="{reverse("loans:delete", args=[paid.pk])}"')
        self.assertContains(response, 'data-detail="Its 1 payment will also be deleted."')
        self.assertContains(response, 'data-detail=""')

    def test_customer_with_paid_loans_can_be_deleted_after_its_loans(self):
        register_payment(loan=self.loan, amount=Decimal("300"), user=self.admin)
        self.client.post(self.url)
        self.client.post(reverse("customers:delete", args=[self.customer.pk]))
        self.assertFalse(type(self.customer).objects.filter(pk=self.customer.pk).exists())

    def test_detail_shows_the_delete_button_only_to_admins(self):
        response = self.client.get(self.loan.get_absolute_url())
        self.assertContains(response, 'id="deleteLoanModal"')
        self.client.force_login(create_user("manager", Role.MANAGER, [self.business]))
        response = self.client.get(self.loan.get_absolute_url())
        self.assertNotContains(response, "deleteLoanModal")


class LoanListQueryCountTests(TestCase):
    """The loans list must not run one query per row (days past due, payments)."""

    def test_query_count_does_not_grow_with_the_loans(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        business = create_business()
        admin = create_user("admin", Role.ADMIN, [business])
        customer = create_customer(business, "Lucia", "Cabrera")
        past = today_local() - dt.timedelta(days=30)
        create_loan(customer, admin, Decimal("1000"), 4, first_payment_date=past)
        self.client.force_login(admin)
        with CaptureQueriesContext(connection) as one:
            self.client.get(reverse("loans:list"))
        for _ in range(5):
            create_loan(customer, admin, Decimal("1000"), 4, first_payment_date=past)
        with CaptureQueriesContext(connection) as six:
            response = self.client.get(reverse("loans:list"))
        self.assertEqual(len(one), len(six))
        self.assertContains(response, "30 d")
