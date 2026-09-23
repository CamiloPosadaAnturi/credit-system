"""Constructores de objetos para las pruebas y los datos de demostracion."""
import datetime as dt
from decimal import Decimal

from apps.clientes.models import Cliente
from apps.core.fechas import hoy_local
from apps.creditos import servicios as servicios_credito
from apps.negocios.models import Negocio
from apps.usuarios.models import Rol, Usuario


def crear_negocio(nombre="Prestamos Demo", **extra) -> Negocio:
    datos = {
        "nombre_comercial": nombre,
        "tasa_interes": Decimal("0.4000"),
        "numero_cuotas": 4,
        "frecuencia_pago": "semanal",
        "activo": True,
    }
    datos.update(extra)
    return Negocio.objects.create(**datos)


def crear_usuario(username, rol=Rol.ADMIN, negocios=(), password="Prueba12345",
                  **extra) -> Usuario:
    usuario = Usuario.objects.create_user(
        username=username, password=password, rol=rol,
        first_name=extra.pop("first_name", username.capitalize()),
        last_name=extra.pop("last_name", "Demo"),
        **extra,
    )
    if negocios:
        usuario.negocios.set(negocios)
    return usuario


def crear_cliente(negocio, nombres="Ana", apellido="Ramirez", **extra) -> Cliente:
    datos = {
        "negocio": negocio,
        "nombres": nombres,
        "apellido_paterno": apellido,
        "telefono_principal": "5555555555",
    }
    datos.update(extra)
    return Cliente.objects.create(**datos)


def crear_credito(cliente, usuario=None, capital=Decimal("1000"), cuotas=4,
                  frecuencia="semanal", primer_pago: dt.date | None = None,
                  desembolsar=True, **extra):
    credito = servicios_credito.crear_credito(
        cliente=cliente,
        negocio=cliente.negocio,
        capital=capital,
        numero_cuotas=cuotas,
        frecuencia=frecuencia,
        fecha_primer_pago=primer_pago or hoy_local(),
        usuario=usuario,
        **extra,
    )
    if desembolsar and usuario is not None:
        servicios_credito.aprobar_credito(credito, usuario)
        credito.refresh_from_db()
        servicios_credito.desembolsar_credito(credito, usuario)
        credito.refresh_from_db()
    return credito
