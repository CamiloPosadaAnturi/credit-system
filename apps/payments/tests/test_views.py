"""Tests for the payments list and the payment detail modal."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.factories import create_business, create_customer, create_loan, create_user
from apps.payments import services
from apps.users.models import Role


class PaymentViewsTests(TestCase):
    def setUp(self):
        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [self.business])
        customer = create_customer(self.business)
        loan = create_loan(customer, self.admin, Decimal("1000"), 4)
        self.payment = services.register_payment(
            loan=loan, amount=Decimal("350"), user=self.admin)
        self.client.force_login(self.admin)

    def test_list_rows_open_the_modal_and_hide_collector(self):
        response = self.client.get(reverse("payments:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="paymentModal"')
        self.assertContains(response, "js-payment-modal")
        self.assertContains(response, f'data-url="{self.payment.get_absolute_url()}"')
        self.assertNotContains(response, "Cobrador")
        self.assertNotContains(response, "Collector")

    def test_today_filter_only_returns_payments_from_today(self):
        self.payment.paid_at = timezone.now() - timedelta(days=1)
        self.payment.save(update_fields=["paid_at"])

        response = self.client.get(reverse("payments:list"), {"today": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.payment.reference)
        self.assertTrue(response.context["today_filter"])

    def test_modal_returns_fragment_without_layout(self):
        response = self.client.get(self.payment.get_absolute_url(), {"modal": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "payments/detail_modal.html")
        self.assertTemplateNotUsed(response, "base.html")
        self.assertContains(response, self.payment.loan.reference)
        self.assertNotContains(response, f'href="{self.payment.get_absolute_url()}"')
        self.assertNotContains(response, "Cobrador")

    def test_full_detail_page_still_works(self):
        response = self.client.get(self.payment.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "payments/detail.html")
        self.assertNotContains(response, "Cobrador")
