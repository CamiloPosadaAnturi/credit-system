"""Audit log of the critical operations.

Audit records are immutable: they are appended, never edited or deleted
from the application.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


class AuditAction(models.TextChoices):
    CREATE = "create", _("Creation")
    UPDATE = "update", _("Update")
    DEACTIVATE = "deactivate", _("Deactivation")
    APPROVE = "approve", _("Approval")
    DISBURSE = "disburse", _("Disbursement")
    CANCEL = "cancel", _("Cancellation")
    RESTRUCTURE = "restructure", _("Restructuring")
    PAYMENT = "payment", _("Payment registered")
    REVERSAL = "reversal", _("Payment reversal")
    COLLECTION = "collection", _("Collection action")
    SIGN_IN = "sign_in", _("System access")
    EXPORT = "export", _("Data export")


class AuditLog(models.Model):
    created_at = models.DateTimeField(_("date"), auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        "users.User", verbose_name=_("user"), on_delete=models.SET_NULL,
        null=True, blank=True, related_name="audit_logs",
    )
    business = models.ForeignKey(
        "businesses.Business", verbose_name=_("business"), on_delete=models.SET_NULL,
        null=True, blank=True, related_name="audit_logs",
    )
    action = models.CharField(_("action"), max_length=20, choices=AuditAction.choices)
    model_name = models.CharField(_("model"), max_length=60, blank=True)
    object_id = models.CharField(_("object id"), max_length=40, blank=True)
    description = models.CharField(_("description"), max_length=255)
    data = models.JSONField(_("data"), default=dict, blank=True)
    ip_address = models.GenericIPAddressField(_("IP"), null=True, blank=True)

    class Meta:
        verbose_name = _("audit log entry")
        verbose_name_plural = _("audit log")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["model_name", "object_id"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self) -> str:
        return (f"{self.created_at:%Y-%m-%d %H:%M} {self.get_action_display()} - "
                f"{self.description}")
