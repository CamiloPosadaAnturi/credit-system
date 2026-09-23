from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.usuarios.models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ("username", "first_name", "last_name", "rol", "is_active")
    list_filter = ("rol", "is_active", "negocios")
    filter_horizontal = ("negocios", "groups", "user_permissions")
    fieldsets = UserAdmin.fieldsets + (
        ("Sistema de creditos", {"fields": ("rol", "telefono", "negocios")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Sistema de creditos", {"fields": ("rol", "telefono", "negocios")}),
    )
