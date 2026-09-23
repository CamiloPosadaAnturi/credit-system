from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.dashboard.urls")),
    path("usuarios/", include("apps.usuarios.urls")),
    path("negocios/", include("apps.negocios.urls")),
    path("clientes/", include("apps.clientes.urls")),
    path("creditos/", include("apps.creditos.urls")),
    path("pagos/", include("apps.pagos.urls")),
    path("cobranza/", include("apps.cobranza.urls")),
    path("reportes/", include("apps.reportes.urls")),
    path("notificaciones/", include("apps.notificaciones.urls")),
    path("auditoria/", include("apps.auditoria.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "Sistema de Creditos"
admin.site.site_title = "Sistema de Creditos"
admin.site.index_title = "Administracion"
