"""Delete a customer: permissions, business rule (no loans), audit and UI."""
from django.test import TestCase
from django.urls import reverse

from apps.audit.models import AuditAction, AuditLog
from apps.core.factories import create_business, create_customer, create_loan, create_user
from apps.customers.models import Customer
from apps.users.models import Role


class CustomerDeleteTests(TestCase):
    def setUp(self):
        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [self.business])
        self.customer = create_customer(self.business, "Lucia", "Cabrera")
        self.url = reverse("customers:delete", args=[self.customer.pk])
        self.client.force_login(self.admin)

    def test_admin_deletes_a_customer_without_loans(self):
        response = self.client.post(self.url)
        self.assertRedirects(response, reverse("customers:list"))
        self.assertFalse(Customer.objects.filter(pk=self.customer.pk).exists())

    def test_deletion_is_audited_with_a_snapshot(self):
        self.client.post(self.url)
        entry = AuditLog.objects.get(action=AuditAction.DELETE)
        self.assertEqual(entry.model_name, "Customer")
        self.assertEqual(entry.object_id, str(self.customer.pk))
        self.assertEqual(entry.user, self.admin)
        self.assertEqual(entry.data["full_name"], "Lucia Cabrera")
        self.assertNotIn("code", entry.data)
        self.assertEqual(entry.data["phone"], self.customer.phone)

    def test_customer_with_loans_is_not_deleted(self):
        create_loan(self.customer, user=self.admin)
        response = self.client.post(self.url, follow=True)
        self.assertRedirects(response, self.customer.get_absolute_url())
        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())
        self.assertContains(response, "alert-danger")
        self.assertFalse(AuditLog.objects.filter(action=AuditAction.DELETE).exists())

    def test_get_shows_a_confirmation_page_and_deletes_nothing(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "customers/confirm_delete.html")
        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())

    def test_manager_and_collector_cannot_delete(self):
        for role in (Role.MANAGER, Role.COLLECTOR, Role.VIEWER):
            user = create_user(f"user_{role}", role, [self.business])
            self.client.force_login(user)
            self.assertEqual(self.client.post(self.url).status_code, 403)
        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())

    def test_next_keeps_the_list_filters_but_ignores_external_urls(self):
        next_url = reverse("customers:list") + "?q=Lu"
        response = self.client.post(self.url, {"next": next_url})
        self.assertRedirects(response, next_url)
        other = create_customer(self.business, "Ana", "Ruiz")
        response = self.client.post(reverse("customers:delete", args=[other.pk]),
                                    {"next": "https://evil.example/"})
        self.assertRedirects(response, reverse("customers:list"))

    def test_list_shows_delete_next_to_edit(self):
        with_loan = create_customer(self.business, "Mario", "Diaz")
        create_loan(with_loan, user=self.admin)
        response = self.client.get(reverse("customers:list"))
        self.assertContains(response, 'id="deleteCustomerModal"')
        self.assertContains(response, f'data-url="{self.url}"')
        # A customer with loans gets a notice (not the confirmation) saying why.
        self.assertNotContains(
            response, f'data-url="{reverse("customers:delete", args=[with_loan.pk])}"')
        self.assertContains(response, 'id="blockedActionModal"')
        self.assertContains(response, "Mario Diaz has 1 registered loan. Delete it first")

    def test_list_hides_delete_from_managers(self):
        self.client.force_login(create_user("manager", Role.MANAGER, [self.business]))
        response = self.client.get(reverse("customers:list"))
        self.assertNotContains(response, "deleteCustomerModal")

    def test_out_of_range_page_shows_the_last_page(self):
        response = self.client.get(reverse("customers:list"), {"page": 99})
        self.assertEqual(response.status_code, 200)
