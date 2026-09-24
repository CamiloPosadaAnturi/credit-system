"""Single entry point for writing to the audit log."""
import json

from apps.audit.middleware import current_ip, current_user
from apps.audit.models import AuditLog


def _serializable(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def log(action: str, description: str, target=None, user=None,
        business=None, data: dict | None = None) -> AuditLog | None:
    """Create an audit entry.

    It never raises into the business operation: a failure to audit must
    not block a payment, but it is written to the system log.
    """
    data = {key: _serializable(value) for key, value in (data or {}).items()}
    try:
        return AuditLog.objects.create(
            user=user or current_user(),
            business=business or getattr(target, "business", None),
            action=action,
            model_name=target.__class__.__name__ if target is not None else "",
            object_id=str(getattr(target, "pk", "") or ""),
            description=description[:255],
            data=data,
            ip_address=current_ip(),
        )
    except Exception:  # noqa: BLE001 - auditing must never break the operation
        import logging

        logging.getLogger(__name__).exception("Could not write the audit entry")
        return None
