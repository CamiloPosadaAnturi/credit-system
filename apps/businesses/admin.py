from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.businesses.models import Business


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("trade_name", "tax_id", "city", "state", "manager",
                    "rate_percentage")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (_("General information"), {"fields": ("trade_name", "legal_name", "tax_id",
                                               "phone", "email", "manager")}),
        (_("Location"), {"fields": ("address", "city", "state")}),
        (_("Interest"), {"fields": ("interest_mode", "interest_rate", "rate_period",
                                    "payment_frequency", "installment_count")}),
        (_("Late fees and payoff"), {"fields": ("grace_days", "charges_late_fee",
                                                "late_fee_rate", "allows_early_payoff",
                                                "early_payoff_discount")}),
        (_("Other"), {"fields": ("notes", "created_at", "updated_at")}),
    )

    # Single-business mode: the one record can be edited but never duplicated
    # or deleted (customers, loans and payments reference it).
    def has_add_permission(self, request):
        return not Business.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
