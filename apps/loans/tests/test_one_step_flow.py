"""One-step loan flow: creating a loan leaves it approved and disbursed."""
from decimal import Decimal

from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from apps.core.dates import today_local
from apps.core.errors import LoanError
from apps.core.factories import create_business, create_customer, create_user
from apps.loans import services
from apps.loans.models import LIVE_STATUSES, Loan, LoanStatus
from apps.users.models import Role


class OneStepLoanFlowTests(TestCase):
    def setUp(self):
        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [self.business])
        self.customer = create_customer(self.business)
        self.client.force_login(self.admin)

    def form_data(self, **extra):
        data = {
            "customer": self.customer.pk,
            "application_date": today_local().isoformat(),
            "principal": "1000",
            "payment_frequency": "weekly",
            "installment_count": 4,
            "first_payment_date": today_local().isoformat(),
        }
        data.update(extra)
        return data

    def test_creating_a_loan_approves_and_disburses_it(self):
        response = self.client.post(reverse("loans:create"), self.form_data())
        loan = Loan.objects.get()
        self.assertRedirects(response, loan.get_absolute_url())
        self.assertIn(loan.status, LIVE_STATUSES)
        self.assertEqual(loan.disbursed_by, self.admin)
        self.assertEqual(loan.disbursement_date, today_local())
        self.assertEqual(loan.total_payable, Decimal("1400.00"))
        # Ready to receive payments right away.
        detail = self.client.get(loan.get_absolute_url())
        self.assertContains(detail, reverse("payments:register", args=[loan.pk]))

    def test_creating_from_the_modal_answers_json(self):
        response = self.client.post(reverse("loans:create"), self.form_data(),
                                    HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        loan = Loan.objects.get()
        self.assertEqual(response.json(), {"ok": True, "redirect": loan.get_absolute_url()})
        self.assertIn(loan.status, LIVE_STATUSES)

    def test_a_failing_rule_saves_nothing(self):
        with self.assertRaises(LoanError):
            services.create_loan(
                customer=self.customer, business=self.business, principal=Decimal("0"),
                installment_count=4, frequency="weekly",
                first_payment_date=today_local(), user=self.admin)
        self.assertFalse(Loan.objects.exists())

    def test_approval_disbursement_and_edit_steps_are_gone(self):
        for name in ["loans:disburse", "loans:approve", "loans:update"]:
            with self.assertRaises(NoReverseMatch):
                reverse(name, args=[1])

    def test_there_are_no_approval_statuses(self):
        for value in ["draft", "pending_approval", "approved"]:
            self.assertNotIn(value, LoanStatus.values)
        response = self.client.get(reverse("loans:list"))
        self.assertNotContains(response, 'value="pending_approval"')

    def test_new_loan_modal_has_the_confirmation_step(self):
        response = self.client.get(reverse("loans:list"))
        self.assertContains(response, "data-confirm-step")
        self.assertContains(response, 'data-step="confirm"')

    def test_new_loan_page_asks_for_confirmation(self):
        response = self.client.get(reverse("loans:create"))
        self.assertContains(response, "data-confirm=")


class SidebarTests(TestCase):
    def test_sidebar_hides_admin_sections(self):
        business = create_business()
        admin = create_user("admin", Role.ADMIN, [business])
        self.client.force_login(admin)
        html = self.client.get(reverse("loans:list")).content.decode()
        nav = html[html.index('<nav class="sidebar-nav">'):html.index("</nav>")]
        self.assertIn(reverse("payments:list"), nav)
        for name in ["reports:catalog", "users:list", "audit:list", "businesses:settings",
                     "admin:index"]:
            self.assertNotIn(f'href="{reverse(name)}"', nav, name)
