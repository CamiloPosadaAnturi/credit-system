import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.generic import DetailView, ListView, UpdateView, View

from apps.core.dates import today_local
from apps.core.errors import BusinessRuleError
from apps.core.mixins import ActionRequiredMixin, SearchMixin
from apps.core.money import to_decimal
from apps.loans import services
from apps.loans.calculations import simulate
from apps.loans.forms import (
    CancellationForm,
    LoanFilterForm,
    LoanForm,
    RestructuringForm,
)
from apps.loans.models import EDITABLE_STATUSES, Loan, LoanStatus
from apps.users import permissions


class LoanBaseMixin(LoginRequiredMixin):
    model = Loan

    def get_queryset(self):
        queryset = Loan.objects.select_related("customer", "business", "collector")
        queryset = permissions.filter_by_business(queryset, self.request.user)
        return permissions.filter_collector_portfolio(queryset, self.request.user)


class LoanListView(LoanBaseMixin, SearchMixin, ListView):
    template_name = "loans/list.html"
    context_object_name = "loans"
    paginate_by = 25
    search_fields = ["reference", "customer__first_name", "customer__last_name",
                     "customer__second_last_name"]

    def get_queryset(self):
        queryset = super().get_queryset()
        self.filter_form = LoanFilterForm(self.request.GET or None, user=self.request.user)
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data.get("business"):
                queryset = queryset.filter(business=data["business"])
            if data.get("status"):
                queryset = queryset.filter(status=data["status"])
            if data.get("collector"):
                queryset = queryset.filter(collector=data["collector"])
            if data.get("start"):
                queryset = queryset.filter(disbursement_date__gte=data["start"])
            if data.get("end"):
                queryset = queryset.filter(disbursement_date__lte=data["end"])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        context["title"] = _("Loans")
        return context


class LoanDetailView(LoanBaseMixin, DetailView):
    template_name = "loans/detail.html"
    context_object_name = "loan"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        loan = self.object
        context["installments"] = loan.installments.all()
        context["payments"] = loan.payments.select_related("received_by").order_by(
            "-paid_at")
        context["can_approve"] = (
            permissions.can(self.request.user, permissions.APPROVE_LOAN)
            and loan.status in EDITABLE_STATUSES
        )
        context["can_disburse"] = (
            permissions.can(self.request.user, permissions.DISBURSE_LOAN)
            and loan.status == LoanStatus.APPROVED
        )
        context["can_register_payment"] = (
            permissions.can(self.request.user, permissions.REGISTER_PAYMENT)
            and loan.is_live
        )
        context["can_cancel"] = (
            permissions.can(self.request.user, permissions.CANCEL_LOAN)
            and loan.status not in (LoanStatus.SETTLED, LoanStatus.CANCELLED)
        )
        context["can_restructure"] = (
            permissions.can(self.request.user, permissions.RESTRUCTURE_LOAN)
            and loan.is_live
        )
        return context


class LoanCreateView(ActionRequiredMixin, View):
    """Two-step loan creation: capture the terms, then confirm them."""

    action = permissions.CREATE_LOAN
    template_name = "loans/form.html"

    def get(self, request):
        initial = {"application_date": today_local(), "first_payment_date": today_local()}
        customer_id = request.GET.get("customer")
        if customer_id:
            from apps.customers.models import Customer

            customer = get_object_or_404(
                permissions.filter_by_business(Customer.objects.all(), request.user),
                pk=customer_id,
            )
            initial.update({"customer": customer.pk, "business": customer.business_id,
                            "collector": customer.collector_id,
                            "interest_mode": customer.business.interest_mode,
                            "interest_rate": customer.business.interest_rate,
                            "rate_period": customer.business.rate_period,
                            "payment_frequency": customer.business.payment_frequency,
                            "installment_count": customer.business.installment_count})
        form = LoanForm(initial=initial, user=request.user)
        return render(request, self.template_name,
                      {"form": form, "title": _("New loan")})

    def post(self, request):
        form = LoanForm(request.POST, request.FILES, user=request.user)
        if not form.is_valid():
            return render(request, self.template_name,
                          {"form": form, "title": _("New loan")})

        data = form.cleaned_data
        permissions.require_business(request.user, data["business"])
        simulation = simulate(
            principal=data["principal"],
            mode=data["interest_mode"],
            rate=data["interest_rate"] or 0,
            installment_count=data["installment_count"],
            first_payment_date=data["first_payment_date"],
            frequency=data["payment_frequency"],
            custom_days=data.get("custom_days"),
        )

        if request.POST.get("confirm") != "1":
            return render(request, "loans/confirm.html", {
                "form": form,
                "simulation": simulation,
                "customer": data["customer"],
                "customer_summary": services.pre_approval_summary(data["customer"]),
                "title": _("Confirm the loan terms"),
            })

        try:
            loan = services.create_loan(
                customer=data["customer"],
                business=data["business"],
                principal=data["principal"],
                installment_count=data["installment_count"],
                frequency=data["payment_frequency"],
                first_payment_date=data["first_payment_date"],
                user=request.user,
                collector=data.get("collector"),
                interest_mode=data["interest_mode"],
                interest_rate=data["interest_rate"] or 0,
                rate_period=data["rate_period"],
                custom_days=data.get("custom_days"),
                application_date=data["application_date"],
                notes=data.get("notes", ""),
            )
        except BusinessRuleError as error:
            messages.error(request, str(error))
            return render(request, self.template_name,
                          {"form": form, "title": _("New loan")})

        if form.cleaned_data.get("contract"):
            loan.contract = form.cleaned_data["contract"]
            loan.save(update_fields=["contract"])
        messages.success(request,
                         _("Loan %(ref)s created.") % {"ref": loan.reference})
        return redirect(loan.get_absolute_url())


class LoanUpdateView(ActionRequiredMixin, LoanBaseMixin, UpdateView):
    action = permissions.CREATE_LOAN
    form_class = LoanForm
    template_name = "loans/form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_object(self, queryset=None):
        loan = super().get_object(queryset)
        if not loan.is_editable:
            raise PermissionDenied(
                _("A disbursed loan cannot be edited. Use an authorized restructuring "
                  "or a payment reversal.")
            )
        return loan

    def form_valid(self, form):
        loan = form.save(commit=False)
        loan.updated_by = self.request.user
        loan.save()
        services.recalculate_terms(loan, user=self.request.user)
        messages.success(self.request, _("Terms updated and schedule rebuilt."))
        return redirect(loan.get_absolute_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Edit %(ref)s") % {"ref": self.object.reference}
        return context


class LoanActionView(LoginRequiredMixin, View):
    """Base for the status transitions (POST plus confirmation)."""

    required_action: str = ""

    def get_loan(self, request, pk) -> Loan:
        queryset = permissions.filter_by_business(Loan.objects.all(), request.user)
        loan = get_object_or_404(queryset, pk=pk)
        permissions.require(request.user, self.required_action)
        return loan


class ApproveLoanView(LoanActionView):
    required_action = permissions.APPROVE_LOAN

    def post(self, request, pk):
        loan = self.get_loan(request, pk)
        try:
            services.approve_loan(loan, request.user)
            messages.success(request,
                             _("Loan %(ref)s approved.") % {"ref": loan.reference})
        except BusinessRuleError as error:
            messages.error(request, str(error))
        return redirect(loan.get_absolute_url())


class DisburseLoanView(LoanActionView):
    required_action = permissions.DISBURSE_LOAN

    def post(self, request, pk):
        loan = self.get_loan(request, pk)
        try:
            services.disburse_loan(loan, request.user)
            messages.success(
                request,
                _("Loan %(ref)s disbursed. The schedule is now active.") % {
                    "ref": loan.reference})
        except BusinessRuleError as error:
            messages.error(request, str(error))
        return redirect(loan.get_absolute_url())


class CancelLoanView(LoanActionView):
    required_action = permissions.CANCEL_LOAN

    def get(self, request, pk):
        loan = self.get_loan(request, pk)
        return render(request, "loans/cancel.html",
                      {"loan": loan, "form": CancellationForm()})

    def post(self, request, pk):
        loan = self.get_loan(request, pk)
        form = CancellationForm(request.POST)
        if form.is_valid():
            try:
                services.cancel_loan(loan, request.user, form.cleaned_data["reason"])
                messages.success(request,
                                 _("Loan %(ref)s cancelled.") % {"ref": loan.reference})
                return redirect(loan.get_absolute_url())
            except BusinessRuleError as error:
                messages.error(request, str(error))
        return render(request, "loans/cancel.html", {"loan": loan, "form": form})


class RestructureLoanView(LoanActionView):
    required_action = permissions.RESTRUCTURE_LOAN

    def get(self, request, pk):
        loan = self.get_loan(request, pk)
        initial = {"installment_count": loan.installment_count,
                   "payment_frequency": loan.payment_frequency,
                   "first_payment_date": today_local()}
        return render(request, "loans/restructure.html",
                      {"loan": loan, "form": RestructuringForm(initial=initial)})

    def post(self, request, pk):
        loan = self.get_loan(request, pk)
        form = RestructuringForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            try:
                new_loan = services.restructure_loan(
                    loan, request.user,
                    installment_count=data["installment_count"],
                    frequency=data["payment_frequency"],
                    first_payment_date=data["first_payment_date"],
                    interest_mode=data.get("interest_mode") or None,
                    interest_rate=data.get("interest_rate"),
                    notes=data.get("notes", ""),
                )
                messages.success(
                    request,
                    _("Loan restructured. New reference: %(ref)s") % {
                        "ref": new_loan.reference})
                return redirect(new_loan.get_absolute_url())
            except BusinessRuleError as error:
                messages.error(request, str(error))
        return render(request, "loans/restructure.html", {"loan": loan, "form": form})


class ScheduleView(LoanBaseMixin, DetailView):
    template_name = "loans/schedule.html"
    context_object_name = "loan"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["installments"] = self.object.installments.all()
        return context


def simulate_loan(request):
    """Live preview of the loan terms (JSON).

    The result is informational: the backend recomputes everything when
    saving. Numbers sent from the browser are never trusted.
    """
    if not request.user.is_authenticated:
        raise PermissionDenied
    try:
        payload = json.loads(request.body or "{}")
        result = simulate(
            principal=to_decimal(payload.get("principal")),
            mode=payload.get("interest_mode"),
            rate=to_decimal(payload.get("interest_rate")),
            installment_count=int(payload.get("installment_count") or 1),
            first_payment_date=today_local(),
            frequency=payload.get("payment_frequency"),
            custom_days=int(payload.get("custom_days") or 0) or None,
        )
    except (ValueError, TypeError, KeyError) as error:
        return JsonResponse({"error": str(error)}, status=400)
    return JsonResponse({
        "principal": str(result["principal"]),
        "total_interest": str(result["total_interest"]),
        "total_payable": str(result["total_payable"]),
        "installment_amount": str(result["installment_amount"]),
        "last_installment_amount": str(result["last_installment_amount"]),
        "installment_count": result["installment_count"],
    })
