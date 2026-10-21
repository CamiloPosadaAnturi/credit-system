"""Customer list/detail: slim profile and the edit modal."""
from django.test import TestCase
from django.urls import reverse

from apps.core.factories import create_business, create_customer, create_user
from apps.customers.models import Customer
from apps.users.models import Role


class CustomerEditModalTests(TestCase):
    def setUp(self):
        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [self.business])
        self.customer = create_customer(self.business, "Lucia", "Cabrera")
        self.client.force_login(self.admin)
        self.url = reverse("customers:update", args=[self.customer.pk])

    def test_removed_fields_are_gone_from_the_model(self):
        names = {field.name for field in Customer._meta.get_fields()}
        for removed in ["collector", "national_id", "tax_id", "birth_date", "alt_phone",
                        "email", "address", "city", "state", "postal_code", "occupation"]:
            self.assertNotIn(removed, names)

    def test_list_has_an_edit_button_per_row(self):
        response = self.client.get(reverse("customers:list"))
        self.assertContains(response, 'id="editCustomerModal"')
        self.assertContains(response, f'data-url="{self.url}"')

    def test_detail_edit_opens_the_modal(self):
        response = self.client.get(self.customer.get_absolute_url())
        self.assertContains(response, 'id="editCustomerModal"')
        self.assertContains(response, "js-remote-form")

    def test_modal_fragment_has_no_layout(self):
        response = self.client.get(self.url, {"modal": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "customers/_edit_form.html")
        self.assertTemplateNotUsed(response, "base.html")
        self.assertContains(response, 'name="first_name"')
        self.assertNotContains(response, 'name="email"')

    def management(self, **extra):
        data = {
            "first_name": "Lucia", "last_name": "Cabrera", "second_last_name": "Fuentes",
            "phone": "5575171986", "status": "active", "notes": "",
        }
        data.update(extra)
        return data

    def test_ajax_save_redirects_to_next(self):
        response = self.client.post(
            self.url, self.management(next=reverse("customers:list") + "?q=Lu"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.json(),
                         {"ok": True, "redirect": reverse("customers:list") + "?q=Lu"})
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.second_last_name, "Fuentes")

    def test_ajax_errors_come_back_as_html(self):
        response = self.client.post(self.url, self.management(first_name=""),
                                    HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 400)
        self.assertIn("is-invalid", response.json()["html"])

    def test_external_next_is_ignored(self):
        response = self.client.post(self.url, self.management(next="https://evil.example/"))
        self.assertRedirects(response, self.customer.get_absolute_url())

    def test_personal_references_are_gone(self):
        from django.apps import apps
        with self.assertRaises(LookupError):
            apps.get_model("customers", "PersonalReference")
        response = self.client.get(self.url, {"modal": "1"})
        self.assertNotContains(response, "references-TOTAL_FORMS")
