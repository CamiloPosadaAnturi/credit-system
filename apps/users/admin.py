from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from apps.users.models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "first_name", "last_name", "role", "is_active")
    list_filter = ("role", "is_active", "businesses")
    filter_horizontal = ("businesses", "groups", "user_permissions")
    fieldsets = UserAdmin.fieldsets + (
        (_("Credit system"), {"fields": ("role", "phone", "businesses")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (_("Credit system"), {"fields": ("role", "phone", "businesses")}),
    )
