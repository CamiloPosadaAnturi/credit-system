import uuid

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.generic import DetailView, ListView, View

from apps.core.errors import BusinessRuleError
from apps.core.mixins import ActionRequiredMixin, SearchMixin
from apps.loans.models import Loan
from apps.payments import services
from apps.payments.forms import (
    PaymentFilterForm,
    PaymentForm,
    PayoffForm,
    ReversalForm,
)
from apps.payments.models import Payment
from apps.users import permissions


class PaymentBaseMixin(LoginRequiredMixin):
    model = Payment

    def get_queryset(self):
        queryset = Payment.objects.select_related(
            "loan", "customer", "business", "received_by", "collector")
        queryset = permissions.filter_by_business(queryset, self.request.user)
        return permissions.filter_collector_portfolio(queryset, self.request.user)


class PaymentListView(PaymentBaseMixin, SearchMixin, ListView):
    template_name = "payments/list.html"
    context_object_name = "payments"
    paginate_by = 30
    search_fields = ["reference", "external_reference", "customer__first_name",
                     "customer__last_name", "loan__reference"]

    def get_queryset(self):
        queryset = super().get_queryset()
        self.filter_form = PaymentFilterForm(
            self.request.GET or None, user=self.request.user)
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data.get("business"):
                queryset = queryset.filter(business=data["business"])
            if data.get("method"):
                queryset = queryset.filter(method=data["method"])
            if data.get("status"):
                queryset = queryset.filter(status=data["status"])
            if data.get("collector"):
                queryset = queryset.filter(collector=data["collector"])
            if data.get("start"):
                queryset = queryset.filter(paid_at__date__gte=data["start"])
            if data.get("end"):
                queryset = queryset.filter(paid_at__date__lte=data["end"])
        return queryset

    def get_context_data(self, **kwargs):
        from django.db.models import Sum

        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        context["filtered_total"] = (
            self.get_queryset().confirmed().aggregate(total=Sum("amount"))["total"] or 0
        )
        context["title"] = _("Payments")
        return context


class PaymentDetailView(PaymentBaseMixin, DetailView):
    template_name = "payments/detail.html"
    context_object_name = "payment"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["allocations"] = self.object.allocations.select_related("installment")
        context["can_reverse"] = (
            permissions.can(self.request.user, permissions.REVERSE_PAYMENT)
            and self.object.is_confirmed
        )
        return context


def _authorized_loan(request, loan_id) -> Loan:
    queryset = permissions.filter_by_business(Loan.objects.all(), request.user)
    queryset = permissions.filter_collector_portfolio(queryset, request.user)
    return get_object_or_404(queryset.select_related("customer", "business"), pk=loan_id)


class RegisterPaymentView(ActionRequiredMixin, View):
    action = permissions.REGISTER_PAYMENT
    template_name = "payments/register.html"

    def build_context(self, loan, form):
        return {
            "loan": loan,
            "form": form,
            "installments": loan.installments.all(),
            "outstanding_balance": services.outstanding_balance(loan),
            "overdue_balance": services.overdue_balance(loan),
            "next_installment": loan.next_installment,
            "title": _("Register payment - %(ref)s") % {"ref": loan.reference},
        }

    def get(self, request, loan_id):
        loan = _authorized_loan(request, loan_id)
        initial = {"idempotency_key": uuid.uuid4().hex}
        next_installment = loan.next_installment
        if next_installment:
            initial["amount"] = next_installment.balance
        form = PaymentForm(initial=initial, loan=loan)
        return render(request, self.template_name, self.build_context(loan, form))

    def post(self, request, loan_id):
        loan = _authorized_loan(request, loan_id)
        form = PaymentForm(request.POST, loan=loan)
        if form.is_valid():
            data = form.cleaned_data
            try:
                payment = services.register_payment(
                    loan=loan,
                    amount=data["amount"],
                    user=request.user,
                    method=data["method"],
                    paid_at=data.get("paid_at") or None,
                    external_reference=data.get("external_reference", ""),
                    notes=data.get("notes", ""),
                    idempotency_key=data.get("idempotency_key", ""),
                    allow_overpayment=data.get("allow_overpayment", False),
                    force_duplicate=data.get("confirm_duplicate", False),
                )
            except BusinessRuleError as error:
                messages.error(request, str(error))
                return render(request, self.template_name,
                              self.build_context(loan, form))
            text = _("Payment %(ref)s registered for %(amount)s MXN.") % {
                "ref": payment.reference, "amount": payment.amount}
            if payment.overpayment:
                text += " " + _("Unallocated overpayment: %(amount)s MXN.") % {
                    "amount": payment.overpayment}
            messages.success(request, text)
            return redirect("payments:detail", pk=payment.pk)
        return render(request, self.template_name, self.build_context(loan, form))


class ReversePaymentView(ActionRequiredMixin, View):
    action = permissions.REVERSE_PAYMENT
    template_name = "payments/reverse.html"

    def get_payment(self, request, pk) -> Payment:
        queryset = permissions.filter_by_business(Payment.objects.all(), request.user)
        return get_object_or_404(queryset, pk=pk)

    def get(self, request, pk):
        payment = self.get_payment(request, pk)
        return render(request, self.template_name,
                      {"payment": payment, "form": ReversalForm()})

    def post(self, request, pk):
        payment = self.get_payment(request, pk)
        form = ReversalForm(request.POST)
        if form.is_valid():
            try:
                services.reverse_payment(payment, request.user,
                                         form.cleaned_data["reason"])
                messages.success(
                    request,
                    _("Payment %(ref)s reversed.") % {"ref": payment.reference})
                return redirect("payments:detail", pk=payment.pk)
            except BusinessRuleError as error:
                messages.error(request, str(error))
        return render(request, self.template_name,
                      {"payment": payment, "form": form})


class EarlyPayoffView(ActionRequiredMixin, View):
    action = permissions.REGISTER_PAYMENT
    template_name = "payments/payoff.html"

    def get(self, request, loan_id):
        loan = _authorized_loan(request, loan_id)
        return render(request, self.template_name, {
            "loan": loan,
            "quote": services.early_payoff_quote(loan),
            "form": PayoffForm(initial={"idempotency_key": uuid.uuid4().hex}),
        })

    def post(self, request, loan_id):
        loan = _authorized_loan(request, loan_id)
        form = PayoffForm(request.POST)
        quote = services.early_payoff_quote(loan)
        if form.is_valid():
            data = form.cleaned_data
            try:
                payment = services.settle_early(
                    loan, request.user,
                    method=data["method"],
                    external_reference=data.get("external_reference", ""),
                    notes=data.get("notes", ""),
                    idempotency_key=data.get("idempotency_key", ""),
                )
                messages.success(
                    request,
                    _("Loan settled with payment %(ref)s.") % {
                        "ref": payment.reference})
                return redirect("loans:detail", pk=loan.pk)
            except BusinessRuleError as error:
                messages.error(request, str(error))
        return render(request, self.template_name,
                      {"loan": loan, "quote": quote, "form": form})
