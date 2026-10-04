import datetime as dt

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic import ListView, TemplateView, View

from apps.audit.models import AuditAction
from apps.audit.services import log
from apps.collections import services
from apps.collections.forms import (
    CollectionActionFilterForm,
    CollectionActionForm,
    CollectionsFilterForm,
)
from apps.collections.models import CollectionAction
from apps.core.dates import today_local
from apps.core.mixins import ActionRequiredMixin
from apps.loans.models import Loan
from apps.users import permissions


def authorized_loans(request):
    queryset = permissions.filter_by_business(Loan.objects.all(), request.user)
    return permissions.filter_collector_portfolio(queryset, request.user)


class CollectionsBoardView(ActionRequiredMixin, TemplateView):
    action = permissions.VIEW_COLLECTIONS
    template_name = "collections/board.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request = self.request
        form = CollectionsFilterForm(request.GET or None, user=request.user)
        loans = authorized_loans(request)
        min_days = 0
        if form.is_valid():
            data = form.cleaned_data
            if data.get("business"):
                loans = loans.filter(business=data["business"])
            if data.get("collector"):
                loans = loans.filter(collector=data["collector"])
            min_days = data.get("min_days_past_due") or 0

        today = today_local()
        live = loans.live()
        context.update({
            "filter_form": form,
            "today": today,
            "breakdown": services.portfolio_breakdown(loans, today),
            "due_today": services.installments_due_on(live, today),
            "upcoming": services.upcoming_installments(live, 7, today)[:50],
            "overdue": services.overdue_installments(live, today, min_days)[:100],
            "past_due": services.past_due_summary(live, today)[:100],
            "title": _("Collections and past-due portfolio"),
        })
        return context


class CollectionActionListView(ActionRequiredMixin, ListView):
    action = permissions.VIEW_COLLECTIONS
    model = CollectionAction
    template_name = "collections/actions.html"
    context_object_name = "actions"
    paginate_by = 30

    def get_queryset(self):
        queryset = CollectionAction.objects.select_related(
            "customer", "loan", "user", "business")
        queryset = permissions.filter_by_business(queryset, self.request.user)
        if self.request.user.is_collector:
            queryset = queryset.filter(user=self.request.user)
        self.filter_form = CollectionActionFilterForm(
            self.request.GET or None, user=self.request.user)
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data.get("business"):
                queryset = queryset.filter(business=data["business"])
            if data.get("collector"):
                queryset = queryset.filter(user=data["collector"])
            if data.get("action_type"):
                queryset = queryset.filter(action_type=data["action_type"])
            if data.get("outcome"):
                queryset = queryset.filter(outcome=data["outcome"])
            if data.get("start"):
                queryset = queryset.filter(performed_at__date__gte=data["start"])
            if data.get("end"):
                queryset = queryset.filter(performed_at__date__lte=data["end"])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        context["title"] = _("Collection actions")
        return context


class LogCollectionActionView(ActionRequiredMixin, View):
    action = permissions.LOG_COLLECTION_ACTION
    template_name = "collections/log_action.html"

    def get_loan(self, request, loan_id) -> Loan:
        return get_object_or_404(
            authorized_loans(request).select_related("customer", "business"),
            pk=loan_id)

    def get(self, request, loan_id):
        loan = self.get_loan(request, loan_id)
        return render(request, self.template_name, {
            "loan": loan,
            "form": CollectionActionForm(initial={
                "next_contact_date": today_local() + dt.timedelta(days=1)}),
            "actions": loan.collection_actions.select_related("user")[:10],
        })

    def post(self, request, loan_id):
        loan = self.get_loan(request, loan_id)
        form = CollectionActionForm(request.POST)
        if form.is_valid():
            action = form.save(commit=False)
            action.loan = loan
            action.customer = loan.customer
            action.business = loan.business
            action.user = request.user
            action.performed_at = timezone.now()
            action.save()
            log(
                AuditAction.COLLECTION,
                _("Collection action (%(type)s) on %(reference)s") % {
                    "type": action.get_action_type_display(),
                    "reference": loan.reference,
                },
                target=action, user=request.user, business=loan.business,
                data={"outcome": action.outcome,
                      "promised_amount": str(action.promised_amount)},
            )
            messages.success(request, _("Collection action saved."))
            return redirect("loans:detail", pk=loan.pk)
        return render(request, self.template_name, {
            "loan": loan, "form": form,
            "actions": loan.collection_actions.select_related("user")[:10],
        })


class MyPortfolioView(ActionRequiredMixin, TemplateView):
    """The collector's daily view: who has to pay today."""

    action = permissions.VIEW_COLLECTIONS
    template_name = "collections/my_portfolio.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = today_local()
        loans = authorized_loans(self.request).live()
        if not self.request.user.is_collector:
            collector_id = self.request.GET.get("collector")
            if collector_id:
                loans = loans.filter(collector_id=collector_id)
        context.update({
            "today": today,
            "due_today": services.installments_due_on(loans, today),
            "overdue": services.overdue_installments(loans, today),
            "upcoming": services.upcoming_installments(loans, 3, today),
            "title": _("My portfolio for today"),
        })
        return context


class RefreshPastDueView(ActionRequiredMixin, View):
    """Recompute the past-due status of the live loans."""

    action = permissions.VIEW_COLLECTIONS

    def post(self, request):
        from apps.loans.services import refresh_statuses

        changed = refresh_statuses(authorized_loans(request).live())
        messages.success(
            request, _("%(count)s loan(s) changed status.") % {"count": changed})
        return redirect("collections:board")
