from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.generic import TemplateView, View

from apps.audit.models import AuditAction
from apps.audit.services import log
from apps.core.mixins import ActionRequiredMixin
from apps.reports.definitions import REPORTS
from apps.reports.exporters import EXPORTERS
from apps.reports.forms import ReportFilterForm
from apps.users import permissions

VIEW_ROW_LIMIT = 500


class ReportCatalogView(ActionRequiredMixin, TemplateView):
    action = permissions.VIEW_REPORTS
    template_name = "reports/catalog.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["reports"] = list(REPORTS.values())
        context["title"] = _("Reports")
        return context


class ReportView(ActionRequiredMixin, View):
    action = permissions.VIEW_REPORTS
    template_name = "reports/detail.html"

    def get(self, request, key):
        report = REPORTS.get(key)
        if not report:
            raise Http404("Report not found")
        form = ReportFilterForm(request.GET or None, user=request.user)
        filters = form.cleaned_data if form.is_valid() else {}

        export_format = request.GET.get("format")
        if export_format:
            return self.export(request, report, filters, export_format)

        rows = list(report.generator(request.user, filters))
        return render(request, self.template_name, {
            "report": report,
            "form": form,
            "rows": rows[:VIEW_ROW_LIMIT],
            "row_count": len(rows),
            "limit": VIEW_ROW_LIMIT,
            "querystring": request.GET.urlencode(),
            "title": report.name,
        })

    def export(self, request, report, filters, export_format):
        exporter = EXPORTERS.get(export_format)
        if not exporter:
            messages.error(request, _("Unsupported export format."))
            return redirect("reports:detail", key=report.key)
        rows = list(report.generator(request.user, filters))
        try:
            response = exporter(report, rows)
        except NotImplementedError as error:
            messages.warning(request, str(error))
            return redirect("reports:detail", key=report.key)
        log(
            AuditAction.EXPORT,
            f"Exported the report '{report.name}' as {export_format}",
            user=request.user,
            business=filters.get("business"),
            data={"rows": len(rows), "filters": {
                key: str(value) for key, value in filters.items() if value}},
        )
        return response
