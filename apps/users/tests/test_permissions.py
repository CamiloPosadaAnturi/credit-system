"""Tests for the permission matrix and the single-business mode."""
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from apps.businesses.models import Business
from apps.core.factories import (
    create_business,
    create_customer,
    create_loan,
    create_user,
)
from apps.customers.models import Customer
from apps.loans.models import Loan
from apps.users import permissions
from apps.users.models import Role, User


class PermissionMatrixTests(TestCase):
    def setUp(self):
        self.business = create_business()
        self.by_role = {
            role: create_user(f"u_{role}", role, [self.business])
            for role in [Role.SUPERADMIN, Role.ADMIN, Role.MANAGER,
                         Role.COLLECTOR, Role.VIEWER]
        }

    def test_only_admins_approve_loans(self):
        self.assertTrue(permissions.can(self.by_role[Role.SUPERADMIN],
                                        permissions.APPROVE_LOAN))
        self.assertTrue(permissions.can(self.by_role[Role.ADMIN],
                                        permissions.APPROVE_LOAN))
        for role in [Role.MANAGER, Role.COLLECTOR, Role.VIEWER]:
            self.assertFalse(permissions.can(self.by_role[role],
                                             permissions.APPROVE_LOAN))

    def test_collector_registers_payments_but_cannot_reverse_them(self):
        collector = self.by_role[Role.COLLECTOR]
        self.assertTrue(permissions.can(collector, permissions.REGISTER_PAYMENT))
        self.assertFalse(permissions.can(collector, permissions.REVERSE_PAYMENT))

    def test_viewer_is_read_only(self):
        viewer = self.by_role[Role.VIEWER]
        self.assertTrue(permissions.can(viewer, permissions.VIEW_LOANS))
        for action in [permissions.REGISTER_PAYMENT, permissions.CREATE_LOAN,
                       permissions.MANAGE_CUSTOMERS, permissions.MANAGE_USERS]:
            self.assertFalse(permissions.can(viewer, action))

    def test_sensitive_data_is_restricted(self):
        self.assertTrue(permissions.can(self.by_role[Role.ADMIN],
                                        permissions.VIEW_SENSITIVE_DATA))
        self.assertFalse(permissions.can(self.by_role[Role.MANAGER],
                                         permissions.VIEW_SENSITIVE_DATA))
        self.assertFalse(permissions.can(self.by_role[Role.COLLECTOR],
                                         permissions.VIEW_SENSITIVE_DATA))

    def test_inactive_user_can_do_nothing(self):
        user = self.by_role[Role.ADMIN]
        user.is_active = False
        self.assertFalse(permissions.can(user, permissions.VIEW_DASHBOARD))

    def test_require_raises_permission_denied(self):
        with self.assertRaises(PermissionDenied):
            permissions.require(self.by_role[Role.VIEWER], permissions.CREATE_LOAN)

    def test_unknown_action(self):
        with self.assertRaises(ValueError):
            permissions.can(self.by_role[Role.ADMIN], "made_up_action")


class SingleBusinessTests(TestCase):
    """The system operates one business: nobody has to pick or be assigned one."""

    def setUp(self):
        self.business = create_business("The business")
        # Users are no longer linked to businesses.
        self.admin = create_user("admin", Role.ADMIN)
        self.manager = create_user("manager", Role.MANAGER)
        self.collector = create_user("coll", Role.COLLECTOR)
        self.superadmin = create_user("boss", Role.SUPERADMIN)
        self.customer = create_customer(self.business, "Ana")
        self.loan = create_loan(self.customer, self.admin, Decimal("1000"))

    def test_current_returns_the_existing_business(self):
        self.assertEqual(Business.objects.current(), self.business)
        self.assertEqual(Business.objects.count(), 1)

    def test_current_creates_the_business_on_a_fresh_install(self):
        Loan.objects.all().delete()
        Customer.objects.all().delete()
        Business.objects.all().delete()
        business = Business.objects.current()
        self.assertEqual(Business.objects.count(), 1)
        self.assertEqual(business.interest_rate, Decimal("0.4000"))

    def test_users_without_membership_see_the_data(self):
        visible = permissions.filter_by_business(Customer.objects.all(), self.manager)
        self.assertEqual(list(visible), [self.customer])
        self.client.force_login(self.manager)
        self.assertContains(self.client.get(reverse("customers:list")), "Ana")
        self.assertEqual(
            self.client.get(reverse("loans:detail", args=[self.loan.pk])).status_code, 200)

    def test_anonymous_sees_nothing(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertFalse(
            permissions.filter_by_business(Customer.objects.all(), AnonymousUser()).exists())

    def test_new_customer_gets_the_business_automatically(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("customers:create"), {
            "first_name": "Carla", "last_name": "Lopez", "phone": "5512345678",
            "status": "active",
            "references-TOTAL_FORMS": "0", "references-INITIAL_FORMS": "0",
            "references-MIN_NUM_FORMS": "0", "references-MAX_NUM_FORMS": "1000",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Customer.objects.get(first_name="Carla").business, self.business)

    def test_forms_do_not_ask_for_a_business(self):
        self.client.force_login(self.admin)
        for name in ["customers:create", "loans:create", "users:create",
                     "customers:list", "loans:list", "payments:list"]:
            with self.subTest(view=name):
                response = self.client.get(reverse(name))
                self.assertNotContains(response, 'name="business"')
                self.assertNotContains(response, 'name="businesses"')

    def test_dashboard_has_no_business_selector(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="business"')
        self.assertNotContains(response, "All businesses")

    def test_settings_page_edits_the_business(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("businesses:settings")).status_code, 200)
        response = self.client.post(reverse("businesses:settings_edit"), {
            "trade_name": "Renamed", "interest_mode": "flat_on_principal",
            "interest_rate": "0.3000", "rate_period": "contract",
            "payment_frequency": "weekly", "installment_count": "4",
            "grace_days": "2", "late_fee_rate": "0", "early_payoff_discount": "0",
            "allows_early_payoff": "on",
        })
        self.assertRedirects(response, reverse("businesses:settings"))
        self.business.refresh_from_db()
        self.assertEqual(self.business.trade_name, "Renamed")
        self.assertEqual(self.business.interest_rate, Decimal("0.3000"))
        self.assertEqual(Business.objects.count(), 1)

    def test_settings_require_permission(self):
        for user in [self.manager, self.collector]:
            self.client.force_login(user)
            with self.subTest(role=user.role):
                self.assertEqual(
                    self.client.get(reverse("businesses:settings")).status_code, 403)
                self.assertEqual(
                    self.client.get(reverse("businesses:settings_edit")).status_code, 403)

    def test_admin_cannot_manage_super_administrators(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("users:list"))
        self.assertContains(response, "manager")
        self.assertNotContains(response, ">boss<")
        self.assertEqual(
            self.client.get(reverse("users:update", args=[self.superadmin.pk])).status_code,
            404)
        self.assertEqual(
            self.client.get(
                reverse("users:password", args=[self.superadmin.pk])).status_code, 403)

    def test_admin_creates_users_without_businesses(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("users:create"), {
            "username": "newcoll", "first_name": "New", "last_name": "Collector",
            "role": "collector", "is_active": "on",
            "password1": "Sup3r-Secret-99", "password2": "Sup3r-Secret-99",
        })
        self.assertEqual(response.status_code, 302)
        new_user = User.objects.get(username="newcoll")
        self.client.force_login(self.admin)
        # The new collector can be assigned to customers right away.
        response = self.client.get(reverse("customers:create"))
        self.assertContains(response, f'value="{new_user.pk}"')


class CollectorPortfolioTests(TestCase):
    def setUp(self):
        self.business = create_business()
        self.admin = create_user("admin", Role.ADMIN, [self.business])
        self.collector_one = create_user("coll1", Role.COLLECTOR, [self.business])
        self.collector_two = create_user("coll2", Role.COLLECTOR, [self.business])
        self.customer_one = create_customer(self.business, "Ana",
                                            collector=self.collector_one)
        self.customer_two = create_customer(self.business, "Beto",
                                            collector=self.collector_two)
        self.loan_one = create_loan(self.customer_one, self.admin)
        self.loan_two = create_loan(self.customer_two, self.admin)

    def test_collector_only_sees_their_portfolio(self):
        visible = permissions.filter_collector_portfolio(
            Loan.objects.all(), self.collector_one)
        self.assertEqual(list(visible), [self.loan_one])

    def test_admin_sees_the_whole_portfolio(self):
        visible = permissions.filter_collector_portfolio(
            Loan.objects.all(), self.admin)
        self.assertEqual(visible.count(), 2)

    def test_collector_cannot_open_another_collectors_loan(self):
        self.client.force_login(self.collector_one)
        self.assertEqual(
            self.client.get(
                reverse("loans:detail", args=[self.loan_one.pk])).status_code, 200)
        self.assertEqual(
            self.client.get(
                reverse("loans:detail", args=[self.loan_two.pk])).status_code, 404)

    def test_collector_cannot_open_reports(self):
        self.client.force_login(self.collector_one)
        self.assertEqual(self.client.get(reverse("reports:catalog")).status_code, 403)

    def test_collector_cannot_create_loans(self):
        self.client.force_login(self.collector_one)
        self.assertEqual(self.client.get(reverse("loans:create")).status_code, 403)

    def test_login_is_required(self):
        response = self.client.get(reverse("loans:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/users/sign-in/", response["Location"])
