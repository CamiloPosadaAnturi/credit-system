"""API unica para escribir en la bitacora."""
import json

from apps.auditoria.middleware import ip_actual, usuario_actual
from apps.auditoria.models import RegistroAuditoria


def _serializable(valor):
    try:
        json.dumps(valor)
        return valor
    except TypeError:
        return str(valor)


def registrar(accion: str, descripcion: str, objeto=None, usuario=None,
              negocio=None, datos: dict | None = None) -> RegistroAuditoria:
    """Crea un registro de auditoria.

    Nunca lanza excepciones hacia la operacion de negocio: una falla al
    auditar no debe impedir un pago, pero si queda en el log del sistema.
    """
    datos = {clave: _serializable(valor) for clave, valor in (datos or {}).items()}
    try:
        return RegistroAuditoria.objects.create(
            usuario=usuario or usuario_actual(),
            negocio=negocio or getattr(objeto, "negocio", None),
            accion=accion,
            modelo=objeto.__class__.__name__ if objeto is not None else "",
            objeto_id=str(getattr(objeto, "pk", "") or ""),
            descripcion=descripcion[:255],
            datos=datos,
            ip=ip_actual(),
        )
    except Exception:  # noqa: BLE001  - auditar nunca debe romper la operacion
        import logging

        logging.getLogger(__name__).exception("No se pudo registrar la auditoria")
        return None
