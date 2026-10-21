"""The ?q= search box filters the customer, loan and payment lists."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.core.factories import create_business, create_customer, create_loan, create_user
from apps.payments import services as payment_services
from apps.users.models import Role


class ListSearchTests(TestCase):
    def setUp(self):
        business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [business])
        self.lucia = create_customer(business, "Lucia", "Cabrera")
        self.hector = create_customer(business, "Hector", "Jimenez")
        self.loan_lucia = create_loan(self.lucia, self.admin)
        self.loan_hector = create_loan(self.hector, self.admin)
        payment_services.register_payment(
            loan=self.loan_lucia, amount=Decimal("100"), user=self.admin)
        payment_services.register_payment(
            loan=self.loan_hector, amount=Decimal("100"), user=self.admin)
        self.client.force_login(self.admin)

    def assert_only_lucia(self, url_name):
        response = self.client.get(reverse(url_name), {"q": "Lucia"})
        rows = list(response.context["object_list"])
        self.assertTrue(rows)
        for row in rows:
            customer = getattr(row, "customer", row)
            self.assertEqual(customer, self.lucia)

    def test_customer_search(self):
        self.assert_only_lucia("customers:list")

    def test_loan_search(self):
        self.assert_only_lucia("loans:list")

    def test_payment_search(self):
        self.assert_only_lucia("payments:list")
