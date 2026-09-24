"""Collection actions: the record of the collector's daily work."""
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.money import ZERO


class ActionType(models.TextChoices):
    CALL = "call", _("Call made")
    MESSAGE = "message", _("Message sent")
    VISIT = "visit", _("Visit made")
    PROMISE = "promise", _("Promise to pay")
    NOT_FOUND = "not_found", _("Customer not reached")
    AGREEMENT = "agreement", _("Payment agreement")


class ActionOutcome(models.TextChoices):
    PAID = "paid", _("Payment made")
    PROMISED = "promised", _("Promises to pay")
    NO_ANSWER = "no_answer", _("No answer")
    REFUSED = "refused", _("Refuses to pay")
    RESCHEDULED = "rescheduled", _("Reschedule contact")
    OTHER = "other", _("Other")


class CollectionAction(models.Model):
    loan = models.ForeignKey(
        "loans.Loan", verbose_name=_("loan"), on_delete=models.CASCADE,
        related_name="collection_actions")
    customer = models.ForeignKey(
        "customers.Customer", verbose_name=_("customer"), on_delete=models.CASCADE,
        related_name="collection_actions")
    business = models.ForeignKey(
        "businesses.Business", verbose_name=_("business"), on_delete=models.CASCADE,
        related_name="collection_actions")
    user = models.ForeignKey(
        "users.User", verbose_name=_("handled by"), on_delete=models.PROTECT,
        related_name="collection_actions")

    performed_at = models.DateTimeField(_("action date"), db_index=True)
    action_type = models.CharField(_("action type"), max_length=20,
                                   choices=ActionType.choices)
    outcome = models.CharField(
        _("outcome"), max_length=20, choices=ActionOutcome.choices,
        default=ActionOutcome.OTHER)

    promised_amount = models.DecimalField(
        _("promised amount"), max_digits=12, decimal_places=2, default=ZERO)
    promise_date = models.DateField(_("promise date"), null=True, blank=True)
    next_contact_date = models.DateField(
        _("next contact date"), null=True, blank=True, db_index=True)
    notes = models.TextField(_("notes"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("collection action")
        verbose_name_plural = _("collection actions")
        ordering = ["-performed_at"]
        indexes = [
            models.Index(fields=["business", "-performed_at"]),
            models.Index(fields=["user", "-performed_at"]),
        ]

    def __str__(self) -> str:
        return (f"{self.get_action_type_display()} - {self.customer} "
                f"({self.performed_at:%d/%m/%Y})")

    @property
    def promise_kept(self) -> bool:
        """A promise counts as kept when payments came in after the action."""
        if not self.promise_date or self.promised_amount <= ZERO:
            return False
        from django.db.models import Sum

        from apps.payments.models import Payment, PaymentStatus

        paid = Payment.objects.filter(
            loan=self.loan, status=PaymentStatus.CONFIRMED,
            paid_at__gte=self.performed_at,
        ).aggregate(total=Sum("amount"))["total"] or ZERO
        return paid >= self.promised_amount
