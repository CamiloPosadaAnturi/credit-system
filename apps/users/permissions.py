"""Permission matrix and data visibility helpers.

Every permission check runs on the server: in the views (which action is
allowed) and in the ORM (which rows may be seen). Hiding buttons in the
frontend is NOT a security control.
"""
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from apps.users.models import Role

# --- System actions -------------------------------------------------------
VIEW_DASHBOARD = "view_dashboard"
MANAGE_BUSINESSES = "manage_businesses"
MANAGE_USERS = "manage_users"
VIEW_CUSTOMERS = "view_customers"
MANAGE_CUSTOMERS = "manage_customers"
VIEW_SENSITIVE_DATA = "view_sensitive_data"
VIEW_LOANS = "view_loans"
CREATE_LOAN = "create_loan"
APPROVE_LOAN = "approve_loan"
DISBURSE_LOAN = "disburse_loan"
CANCEL_LOAN = "cancel_loan"
RESTRUCTURE_LOAN = "restructure_loan"
VIEW_PAYMENTS = "view_payments"
REGISTER_PAYMENT = "register_payment"
REVERSE_PAYMENT = "reverse_payment"
VIEW_COLLECTIONS = "view_collections"
LOG_COLLECTION_ACTION = "log_collection_action"
VIEW_REPORTS = "view_reports"
VIEW_AUDIT = "view_audit"

EVERYONE = {Role.SUPERADMIN, Role.ADMIN, Role.MANAGER, Role.COLLECTOR, Role.VIEWER}

MATRIX: dict[str, set[str]] = {
    VIEW_DASHBOARD: EVERYONE,
    MANAGE_BUSINESSES: {Role.SUPERADMIN, Role.ADMIN},
    MANAGE_USERS: {Role.SUPERADMIN, Role.ADMIN},
    VIEW_CUSTOMERS: EVERYONE,
    MANAGE_CUSTOMERS: {Role.SUPERADMIN, Role.ADMIN, Role.MANAGER},
    VIEW_SENSITIVE_DATA: {Role.SUPERADMIN, Role.ADMIN},
    VIEW_LOANS: EVERYONE,
    CREATE_LOAN: {Role.SUPERADMIN, Role.ADMIN, Role.MANAGER},
    APPROVE_LOAN: {Role.SUPERADMIN, Role.ADMIN},
    DISBURSE_LOAN: {Role.SUPERADMIN, Role.ADMIN},
    CANCEL_LOAN: {Role.SUPERADMIN, Role.ADMIN},
    RESTRUCTURE_LOAN: {Role.SUPERADMIN, Role.ADMIN},
    VIEW_PAYMENTS: EVERYONE,
    REGISTER_PAYMENT: {Role.SUPERADMIN, Role.ADMIN, Role.MANAGER, Role.COLLECTOR},
    REVERSE_PAYMENT: {Role.SUPERADMIN, Role.ADMIN},
    VIEW_COLLECTIONS: {Role.SUPERADMIN, Role.ADMIN, Role.MANAGER, Role.COLLECTOR},
    LOG_COLLECTION_ACTION: {Role.SUPERADMIN, Role.ADMIN, Role.MANAGER, Role.COLLECTOR},
    VIEW_REPORTS: {Role.SUPERADMIN, Role.ADMIN, Role.MANAGER},
    VIEW_AUDIT: {Role.SUPERADMIN, Role.ADMIN},
}


def can(user, action: str) -> bool:
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if getattr(user, "is_superadmin", False):
        return True
    roles = MATRIX.get(action)
    if roles is None:
        raise ValueError(f"Unknown action in the permission matrix: {action}")
    return user.role in roles


def require(user, action: str) -> None:
    if not can(user, action):
        raise PermissionDenied(_("You are not authorized to: %(action)s") % {"action": action})


def allowed_businesses(user) -> QuerySet:
    """Businesses the user may operate on.

    Single-business mode: every authenticated user works on the one business.
    """
    from apps.businesses.models import Business

    if not user or not user.is_authenticated:
        return Business.objects.none()
    return Business.objects.all()


def allowed_business_ids(user) -> list[int]:
    return list(allowed_businesses(user).values_list("id", flat=True))


def filter_by_business(queryset: QuerySet, user, field: str = "business") -> QuerySet:
    """Restrict a queryset to what the user may see.

    Single-business mode: authenticated users see every record (the
    collector portfolio filter still applies separately).
    """
    if not user or not user.is_authenticated:
        return queryset.none()
    return queryset


def filter_collector_portfolio(queryset: QuerySet, user,
                               field: str = "collector") -> QuerySet:
    """A collector only sees the portfolio assigned to them."""
    if user and getattr(user, "is_collector", False):
        return queryset.filter(**{field: user})
    return queryset


def user_has_business(user, business) -> bool:
    return bool(user and user.is_authenticated and business is not None)


def require_business(user, business) -> None:
    if not user_has_business(user, business):
        raise PermissionDenied(_("You do not have access to this business."))
