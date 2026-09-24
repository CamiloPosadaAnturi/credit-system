"""Tests for the permission matrix and the per-business isolation."""
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from apps.core.factories import (
    create_business,
    create_customer,
    create_loan,
    create_user,
)
from apps.customers.models import Customer
from apps.loans.models import Loan
from apps.users import permissions
from apps.users.models import Role


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


class BusinessIsolationTests(TestCase):
    def setUp(self):
        self.business_a = create_business("Business A")
        self.business_b = create_business("Business B")
        self.admin_a = create_user("admin_a", Role.ADMIN, [self.business_a])
        self.admin_b = create_user("admin_b", Role.ADMIN, [self.business_b])
        self.superadmin = create_user("boss", Role.SUPERADMIN)
        self.customer_a = create_customer(self.business_a, "Ana")
        self.customer_b = create_customer(self.business_b, "Beto")
        self.loan_a = create_loan(self.customer_a, self.admin_a, Decimal("1000"))
        self.loan_b = create_loan(self.customer_b, self.admin_b, Decimal("2000"))

    def test_the_orm_filters_by_business(self):
        visible = permissions.filter_by_business(Customer.objects.all(), self.admin_a)
        self.assertEqual(list(visible), [self.customer_a])

        loans = permissions.filter_by_business(Loan.objects.all(), self.admin_b)
        self.assertEqual(list(loans), [self.loan_b])

    def test_the_superadmin_sees_everything(self):
        self.assertEqual(
            permissions.filter_by_business(
                Customer.objects.all(), self.superadmin).count(), 2)

    def test_require_business(self):
        permissions.require_business(self.admin_a, self.business_a)
        with self.assertRaises(PermissionDenied):
            permissions.require_business(self.admin_a, self.business_b)

    def test_detail_view_returns_404_for_another_business(self):
        self.client.force_login(self.admin_a)
        own = self.client.get(reverse("loans:detail", args=[self.loan_a.pk]))
        self.assertEqual(own.status_code, 200)
        foreign = self.client.get(reverse("loans:detail", args=[self.loan_b.pk]))
        self.assertEqual(foreign.status_code, 404)

    def test_customer_list_shows_only_its_own(self):
        self.client.force_login(self.admin_a)
        response = self.client.get(reverse("customers:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ana")
        self.assertNotContains(response, "Beto")


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
