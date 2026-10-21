from django.contrib import admin

from apps.customers.models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("code", "full_name", "business", "phone", "status")
    list_filter = ("business", "status")
    search_fields = ("first_name", "last_name", "second_last_name", "phone", "code")
    readonly_fields = ("code", "created_at", "updated_at")
