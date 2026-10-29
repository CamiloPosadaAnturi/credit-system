from django.contrib import admin

from apps.customers.models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "business", "phone")
    list_filter = ("business",)
    search_fields = ("first_name", "last_name", "second_last_name", "phone")
    readonly_fields = ("created_at", "updated_at")
