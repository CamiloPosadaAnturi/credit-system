from django.contrib import admin

from apps.payments.models import Payment, PaymentAllocation


class AllocationInline(admin.TabularInline):
    model = PaymentAllocation
    extra = 0
    readonly_fields = ("installment", "amount", "principal", "interest")
    can_delete = False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "paid_at", "customer", "loan", "amount", "method",
                    "kind", "status")
    list_filter = ("status", "kind", "method", "business")
    search_fields = ("reference", "external_reference", "loan__reference")
    readonly_fields = ("reference", "allocated_amount", "overpayment", "created_at")
    inlines = [AllocationInline]
    date_hierarchy = "paid_at"

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
