from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.businesses.models import Business


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("trade_name", "tax_id", "city", "state", "manager",
                    "rate_percentage", "is_active")
    list_filter = ("is_active", "state", "interest_mode", "payment_frequency")
    search_fields = ("trade_name", "legal_name", "tax_id")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (_("General information"), {"fields": ("trade_name", "legal_name", "tax_id",
                                               "phone", "email", "manager", "is_active")}),
        (_("Location"), {"fields": ("address", "city", "state")}),
        (_("Interest"), {"fields": ("interest_mode", "interest_rate", "rate_period",
                                    "payment_frequency", "installment_count")}),
        (_("Late fees and payoff"), {"fields": ("grace_days", "charges_late_fee",
                                                "late_fee_rate", "allows_early_payoff",
                                                "early_payoff_discount")}),
        (_("Other"), {"fields": ("notes", "created_at", "updated_at")}),
    )
