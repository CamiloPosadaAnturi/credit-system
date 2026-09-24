"""Aggregated indicators per business.

Centralizes the portfolio queries so that the business dashboard, the main
dashboard and the reports all use the exact same definitions
(see docs/reglas_financieras.md).
"""
from decimal import Decimal

from django.db.models import Count, Q, Sum

from apps.core.money import ZERO, money


def business_summary(business, start=None, end=None) -> dict:
    """Main indicators of a business.

    * disbursed_principal: principal of disbursed loans.
    * contractual_interest: interest agreed on those loans.
    * total_collected: confirmed payments (reversed ones excluded).
    * outstanding_balance: what is left to collect on live loans.
    * overdue_balance: the part of the outstanding balance already past due.
    """
    from apps.loans.models import LIVE_STATUSES, Loan, LoanStatus
    from apps.payments.models import Payment, PaymentStatus

    loans = Loan.objects.filter(business=business).disbursed()
    if start:
        loans = loans.filter(disbursement_date__gte=start)
    if end:
        loans = loans.filter(disbursement_date__lte=end)

    totals = loans.aggregate(
        principal=Sum("principal"),
        interest=Sum("total_interest"),
        payable=Sum("total_payable"),
        balance=Sum("outstanding_balance"),
        live=Count("id", filter=Q(status__in=LIVE_STATUSES)),
        settled=Count("id", filter=Q(status=LoanStatus.SETTLED)),
        past_due=Count("id", filter=Q(status=LoanStatus.PAST_DUE)),
    )

    payments = Payment.objects.filter(business=business, status=PaymentStatus.CONFIRMED)
    if start:
        payments = payments.filter(paid_at__date__gte=start)
    if end:
        payments = payments.filter(paid_at__date__lte=end)
    collected = payments.aggregate(total=Sum("amount"))["total"] or ZERO

    principal = totals["principal"] or ZERO
    interest = totals["interest"] or ZERO
    payable = totals["payable"] or ZERO
    balance = totals["balance"] or ZERO

    from apps.collections.services import overdue_balance_for

    overdue = overdue_balance_for(loans)

    return {
        "business": business,
        "disbursed_principal": money(principal),
        "contractual_interest": money(interest),
        "contractual_total": money(payable),
        "total_collected": money(collected),
        "outstanding_balance": money(balance),
        "overdue_balance": money(overdue),
        "live_loans": totals["live"] or 0,
        "settled_loans": totals["settled"] or 0,
        "past_due_loans": totals["past_due"] or 0,
        "recovery_rate": ratio(collected, payable),
        "overdue_portfolio_rate": ratio(overdue, balance),
    }


def ratio(part, whole) -> Decimal:
    part = part or ZERO
    whole = whole or ZERO
    if whole <= ZERO:
        return ZERO
    return money(Decimal(part) * 100 / Decimal(whole))
