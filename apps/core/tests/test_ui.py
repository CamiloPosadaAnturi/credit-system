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

    def simulate(self, payload: str):
        return self.client.post(reverse("loans:simulate"), data=payload,
                                content_type="application/json")

    def test_the_preview_matches_the_backend(self):
        response = self.simulate(
            '{"principal": "10000", "installment_count": 10,'
            ' "payment_frequency": "weekly", "first_payment_date": "2026-01-05"}')
        self.assertEqual(response.status_code, 200)
        data = response.json()["simulation"]
        self.assertEqual(Decimal(data["total_interest"]), Decimal("4000.00"))
        self.assertEqual(Decimal(data["total_payable"]), Decimal("14000.00"))
        self.assertEqual(Decimal(data["installment_amount"]), Decimal("1400.00"))
        self.assertEqual(data["final_due_date"], "09/03/2026")

    def test_the_rate_always_comes_from_the_settings(self):
        """The browser cannot change the rate or the interest mode."""
        response = self.simulate(
            '{"principal": "1000", "interest_rate": "0.90", "interest_mode":'
            ' "simple_per_period", "installment_count": 4, "payment_frequency": "weekly"}')
        self.assertEqual(Decimal(response.json()["simulation"]["total_interest"]),
                         Decimal("400.00"))

    def test_incomplete_terms_return_no_simulation(self):
        response = self.simulate('{"principal": "0"}')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["simulation"])

    def test_invalid_json_returns_400(self):
        self.assertEqual(self.simulate("not json").status_code, 400)

    def test_customer_warnings_are_included(self):
        from apps.core.factories import create_customer, create_loan

        customer = create_customer(self.business, "Ana")
        create_loan(customer, self.admin)
        response = self.simulate(f'{{"customer": "{customer.pk}"}}')
        data = response.json()
        self.assertIsNone(data["simulation"])
        self.assertTrue(data["warnings"])

    def test_requires_the_create_loan_permission(self):
        self.client.force_login(create_user("coll", Role.COLLECTOR))
        self.assertEqual(self.simulate('{"principal": "1000"}').status_code, 403)
