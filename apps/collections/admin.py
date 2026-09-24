from django.contrib import admin

from apps.collections.models import CollectionAction


@admin.register(CollectionAction)
class CollectionActionAdmin(admin.ModelAdmin):
    list_display = ("performed_at", "customer", "loan", "action_type", "outcome", "user")
    list_filter = ("action_type", "outcome", "business")
    search_fields = ("customer__first_name", "loan__reference")
    date_hierarchy = "performed_at"
