import datetime as dt
import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.views.generic import DetailView, ListView, UpdateView, View

from apps.businesses.models import Business
from apps.core.choices import InterestMode
from apps.core.dates import today_local
from apps.core.errors import BusinessRuleError
from apps.core.mixins import ActionRequiredMixin, SearchMixin
from apps.core.money import to_decimal
from apps.customers.models import Customer
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
        queryset = Loan.objects.select_related("customer", "collector")
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
        if permissions.can(self.request.user, permissions.CREATE_LOAN):
            context["loan_form"] = LoanForm.for_new_loan(user=self.request.user)
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


def is_ajax(request) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


class LoanCreateView(ActionRequiredMixin, View):
    """Register a loan in one step.

    The interest is the business rate (Settings) x principal and the
    collector is the customer's. The customer and loan pages open this form
    in a modal and submit it with ``fetch``: the answer is JSON (the redirect,
    or the form re-rendered with its errors). Without JavaScript it works as
    a normal page.
    """

    action = permissions.CREATE_LOAN
    template_name = "loans/form.html"

    def get(self, request):
        customer = None
        customer_id = request.GET.get("customer")
        if customer_id:
            customer = get_object_or_404(
                permissions.filter_by_business(Customer.objects.all(), request.user),
                pk=customer_id,
            )
        form = LoanForm.for_new_loan(customer, user=request.user)
        return render(request, self.template_name, {"form": form, "title": _("New loan")})

    def post(self, request):
        form = LoanForm(request.POST, user=request.user)
        if form.is_valid():
            data = form.cleaned_data
            customer = data["customer"]
            try:
                loan = services.create_loan(
                    customer=customer,
                    business=customer.business,
                    principal=data["principal"],
                    installment_count=data["installment_count"],
                    frequency=data["payment_frequency"],
                    first_payment_date=data["first_payment_date"],
                    user=request.user,
                    interest_mode=InterestMode.FLAT_ON_PRINCIPAL,
                    application_date=data["application_date"],
                    notes=data.get("notes", ""),
                )
            except BusinessRuleError as error:
                form.add_error(None, str(error))
            else:
                messages.success(
                    request, _("Loan %(ref)s created.") % {"ref": loan.reference})
                if is_ajax(request):
                    return JsonResponse({"ok": True, "redirect": loan.get_absolute_url()})
                return redirect(loan.get_absolute_url())
        if is_ajax(request):
            html = render_to_string("loans/_loan_form.html", {"form": form},
                                    request=request)
            return JsonResponse({"ok": False, "html": html}, status=400)
        return render(request, self.template_name, {"form": form, "title": _("New loan")})


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
        context["cancel_url"] = self.object.get_absolute_url()
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
    saving. The interest rule always comes from the business configuration;
    numbers sent from the browser are never trusted.

    Answers ``{"simulation": {...} | null, "warnings": [...]}``: the
    customer's warnings are returned even while the terms are incomplete.
    """
    if not permissions.can(request.user, permissions.CREATE_LOAN):
        raise PermissionDenied
    try:
        payload = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "Invalid payload."}, status=400)

    warnings = []
    customer_id = str(payload.get("customer") or "")
    if customer_id.isdigit():
        customer = (permissions.filter_by_business(Customer.objects.all(), request.user)
                    .filter(pk=customer_id).first())
        if customer is not None:
            warnings = [str(text) for text in
                        services.pre_approval_summary(customer)["warnings"]]

    business = Business.objects.current()
    simulation = None
    try:
        installment_count = int(payload.get("installment_count") or 0)
        if not 1 <= installment_count <= 1000:
            raise ValueError("Invalid number of installments.")
        first_payment = payload.get("first_payment_date")
        result = simulate(
            principal=to_decimal(payload.get("principal") or 0),
            mode=InterestMode.FLAT_ON_PRINCIPAL,
            rate=business.interest_rate,
            installment_count=installment_count,
            first_payment_date=(dt.date.fromisoformat(first_payment) if first_payment
                                else today_local()),
            frequency=payload.get("payment_frequency") or business.payment_frequency,
        )
        simulation = {
            "principal": str(result["principal"]),
            "total_interest": str(result["total_interest"]),
            "total_payable": str(result["total_payable"]),
            "installment_amount": str(result["installment_amount"]),
            "last_installment_amount": str(result["last_installment_amount"]),
            "installment_count": result["installment_count"],
            "final_due_date": result["final_due_date"].strftime("%d/%m/%Y"),
        }
    except (ValueError, TypeError, KeyError, ArithmeticError):
        simulation = None
    return JsonResponse({"simulation": simulation, "warnings": warnings})
