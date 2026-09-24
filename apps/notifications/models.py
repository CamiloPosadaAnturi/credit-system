"""Internal notices (the system never sends SMS or email to customers)."""
from django.db import models
from django.utils.translation import gettext_lazy as _


class NotificationKind(models.TextChoices):
    INFO = "info", _("Informational")
    ALERT = "alert", _("Alert")
    PAST_DUE = "past_due", _("Past due")


class Notification(models.Model):
    business = models.ForeignKey(
        "businesses.Business", verbose_name=_("business"), on_delete=models.CASCADE,
        related_name="notifications")
    user = models.ForeignKey(
        "users.User", verbose_name=_("addressed to"), on_delete=models.CASCADE,
        null=True, blank=True, related_name="notifications",
        help_text=_("When empty, every user of the business sees it."))
    kind = models.CharField(
        _("kind"), max_length=10, choices=NotificationKind.choices,
        default=NotificationKind.INFO)
    title = models.CharField(_("title"), max_length=150)
    message = models.TextField(_("message"), blank=True)
    url = models.CharField(_("link"), max_length=255, blank=True)
    is_read = models.BooleanField(_("read"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title
