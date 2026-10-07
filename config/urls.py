from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.dashboard.urls")),
    path("users/", include("apps.users.urls")),
    path("settings/", include("apps.businesses.urls")),
    path("customers/", include("apps.customers.urls")),
    path("loans/", include("apps.loans.urls")),
    path("payments/", include("apps.payments.urls")),
    path("collections/", include("apps.collections.urls")),
    path("reports/", include("apps.reports.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("audit/", include("apps.audit.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "Credit System"
admin.site.site_title = "Credit System"
admin.site.index_title = "Administration"
