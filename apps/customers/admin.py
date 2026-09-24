from django.contrib import admin

from apps.customers.models import Customer, PersonalReference


class ReferenceInline(admin.TabularInline):
    model = PersonalReference
    extra = 0


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("code", "full_name", "business", "phone", "collector", "status")
    list_filter = ("business", "status", "collector")
    search_fields = ("first_name", "last_name", "second_last_name", "phone", "code")
    inlines = [ReferenceInline]
    readonly_fields = ("code", "created_at", "updated_at")
