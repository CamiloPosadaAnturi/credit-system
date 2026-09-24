from django.contrib import admin

from apps.loans.models import Installment, Loan


class InstallmentInline(admin.TabularInline):
    model = Installment
    extra = 0
    readonly_fields = ("number", "due_date", "scheduled_amount",
                       "scheduled_principal", "scheduled_interest",
                       "amount_paid", "status")
    can_delete = False


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ("reference", "customer", "business", "principal", "total_interest",
                    "total_payable", "outstanding_balance", "status")
    list_filter = ("status", "business", "payment_frequency", "interest_mode")
    search_fields = ("reference", "customer__first_name", "customer__last_name")
    readonly_fields = ("reference", "total_interest", "total_payable",
                       "installment_amount", "principal_paid", "interest_paid",
                       "outstanding_balance", "final_due_date",
                       "created_at", "updated_at")
    inlines = [InstallmentInline]

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Installment)
class InstallmentAdmin(admin.ModelAdmin):
    list_display = ("loan", "number", "due_date", "scheduled_amount",
                    "amount_paid", "status")
    list_filter = ("status",)
    search_fields = ("loan__reference",)

    def has_delete_permission(self, request, obj=None):
        return False
