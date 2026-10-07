"""View mixins: authentication, role permissions and per-business isolation."""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _

from apps.users import permissions


class ActionRequiredMixin(LoginRequiredMixin):
    """Require the user to be allowed to run ``action`` (permission matrix)."""

    action: str | None = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if self.action and not permissions.can(request.user, self.action):
            raise PermissionDenied(_("You are not allowed to perform this operation."))
        return super().dispatch(request, *args, **kwargs)


class BusinessScopedMixin:
    """Restrict the queryset to the businesses the user is allowed to see.

    ``business_field`` is the ORM path to the business from the view's model
    (for example ``"loan__business"``).
    """

    business_field: str = "business"
    collector_field: str | None = None

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = permissions.filter_by_business(
            queryset, self.request.user, self.business_field)
        if self.collector_field:
            queryset = permissions.filter_collector_portfolio(
                queryset, self.request.user, self.collector_field)
        return queryset


class SearchMixin:
    """Simple ``?q=`` search over ``search_fields``."""

    search_fields: list[str] = []

    def get_queryset(self):
        queryset = super().get_queryset()
        term = (self.request.GET.get("q") or "").strip()
        if term and self.search_fields:
            from django.db.models import Q

            lookup = Q()
            for field in self.search_fields:
                lookup |= Q(**{f"{field}__icontains": term})
            queryset = queryset.filter(lookup)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "")
        context["querystring"] = self.querystring_without_page()
        return context

    def querystring_without_page(self) -> str:
        parameters = self.request.GET.copy()
        parameters.pop("page", None)
        return parameters.urlencode()


class AuditableMixin:
    """Store who created and who last updated the record."""

    def form_valid(self, form):
        if not form.instance.pk:
            form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        return super().form_valid(form)


def require_business_access(user, business) -> None:
    if business is None:
        raise PermissionDenied(_("Operation without an associated business."))
    permissions.require_business(user, business)
