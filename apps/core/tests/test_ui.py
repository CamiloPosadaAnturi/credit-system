"""Interface tests: templates, pagination and public screens."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.core.factories import create_business, create_customer, create_user
from apps.users.models import Role


class PaginationTests(TestCase):
    """Regression: pagination used to break on the first page of a long list."""

    def setUp(self):
        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [self.business])
        for index in range(60):
            create_customer(self.business, f"Customer{index}", "Lastname")
        self.client.force_login(self.admin)

    def test_first_page(self):
        response = self.client.get(reverse("customers:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Page 1 of 3")
        self.assertContains(response, "page=2")

    def test_last_page(self):
        response = self.client.get(reverse("customers:list"), {"page": 3})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Page 3 of 3")

    def test_pagination_keeps_the_filters(self):
        response = self.client.get(reverse("customers:list"),
                                   {"q": "Customer", "page": 2})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "q=Customer")


class PublicScreenTests(TestCase):
    def test_login_page_renders(self):
        response = self.client.get(reverse("users:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Credit System")

    def test_missing_page(self):
        self.assertEqual(self.client.get("/a-route-that-does-not-exist/").status_code, 404)


class SensitiveDataTests(TestCase):
    def setUp(self):
        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [self.business])
        self.manager = create_user("manager", Role.MANAGER, [self.business])
        self.customer = create_customer(self.business,
                                        national_id="RAMA850101HDFMNN09",
                                        tax_id="RAMA850101AB1")

    def test_admin_sees_the_national_id(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("customers:detail", args=[self.customer.pk]))
        self.assertContains(response, "RAMA850101HDFMNN09")

    def test_manager_does_not_see_the_national_id(self):
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse("customers:detail", args=[self.customer.pk]))
        self.assertNotContains(response, "RAMA850101HDFMNN09")
        self.assertContains(response, "sensitive data")


class SimulatorTests(TestCase):
    def setUp(self):
        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [self.business])
        self.client.force_login(self.admin)

    def test_the_preview_matches_the_backend(self):
        response = self.client.post(
            reverse("loans:simulate"),
            data='{"principal": "10000", "interest_rate": "0.40",'
                 ' "installment_count": 10, "interest_mode": "flat_on_principal",'
                 ' "payment_frequency": "weekly"}',
            content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(Decimal(data["total_interest"]), Decimal("4000.00"))
        self.assertEqual(Decimal(data["total_payable"]), Decimal("14000.00"))
        self.assertEqual(Decimal(data["installment_amount"]), Decimal("1400.00"))

    def test_invalid_data_returns_400(self):
        response = self.client.post(
            reverse("loans:simulate"), data='{"principal": "0"}',
            content_type="application/json")
        self.assertEqual(response.status_code, 400)
