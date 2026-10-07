"""Quick customer registration from the modal of the customer list."""
from django.test import TestCase
from django.urls import reverse

from apps.core.factories import create_business, create_user
from apps.customers.models import Customer, CustomerStatus
from apps.users.models import Role

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class QuickCustomerCreateTests(TestCase):
    def setUp(self):
        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN)
        self.client.force_login(self.admin)
        self.url = reverse("customers:create")

    def test_list_includes_the_modal_with_three_fields(self):
        response = self.client.get(reverse("customers:list"))
        self.assertContains(response, 'id="newCustomerModal"')
        self.assertContains(response, 'data-bs-target="#newCustomerModal"')
        form = response.context["quick_form"]
        self.assertEqual(list(form.fields), ["first_name", "last_name", "phone"])

    def test_ajax_success_creates_the_customer(self):
        response = self.client.post(self.url, {
            "first_name": "Laura", "last_name": "Mendez", "phone": "5512345678",
        }, **AJAX)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(),
                         {"ok": True, "redirect": reverse("customers:list")})
        customer = Customer.objects.get(first_name="Laura")
        self.assertEqual(customer.last_name, "Mendez")
        self.assertEqual(customer.phone, "5512345678")
        self.assertEqual(customer.business, self.business)
        self.assertEqual(customer.status, CustomerStatus.ACTIVE)
        self.assertEqual(customer.created_by, self.admin)
        self.assertTrue(customer.code)

    def test_ajax_errors_come_back_as_html(self):
        response = self.client.post(self.url, {"first_name": "Laura"}, **AJAX)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("is-invalid", data["html"])
        self.assertIn('name="last_name"', data["html"])
        self.assertFalse(Customer.objects.exists())

    def test_without_javascript_it_is_a_normal_page(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        response = self.client.post(self.url, {
            "first_name": "Pedro", "last_name": "Soto", "phone": "5598765432"})
        self.assertRedirects(response, reverse("customers:list"))
        self.assertTrue(Customer.objects.filter(first_name="Pedro").exists())

    def test_requires_the_permission(self):
        self.client.force_login(create_user("coll", Role.COLLECTOR))
        response = self.client.post(self.url, {
            "first_name": "X", "last_name": "Y", "phone": "5512345678"}, **AJAX)
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(self.client.get(reverse("customers:list")),
                               'id="newCustomerModal"')
