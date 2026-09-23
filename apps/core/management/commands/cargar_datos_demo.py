"""Carga datos ficticios de demostracion.

Todos los nombres, telefonos y direcciones son inventados. NO uses datos
reales de personas en este comando.

    python manage.py cargar_datos_demo
"""
import datetime as dt
import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.clientes.models import Cliente, EstadoCliente, ReferenciaPersonal
from apps.cobranza.models import GestionCobranza, ResultadoGestion, TipoGestion
from apps.core.fechas import hoy_local
from apps.creditos import servicios as servicios_credito
from apps.negocios.models import Negocio
from apps.pagos import servicios as servicios_pago
from apps.pagos.models import MetodoPago
from apps.usuarios.models import Rol, Usuario

NOMBRES = [
    ("Ana Sofia", "Perez", "Lopez"), ("Luis Fernando", "Ramirez", "Cruz"),
    ("Maria Jose", "Hernandez", "Gomez"), ("Jorge Alberto", "Martinez", "Diaz"),
    ("Claudia", "Sanchez", "Reyes"), ("Miguel Angel", "Torres", "Nunez"),
    ("Patricia", "Flores", "Mendoza"), ("Ricardo", "Castillo", "Vargas"),
    ("Gabriela", "Morales", "Rios"), ("Hector", "Jimenez", "Salas"),
    ("Veronica", "Guzman", "Pina"), ("Alejandro", "Rojas", "Campos"),
    ("Diana Laura", "Ortiz", "Serrano"), ("Fernando", "Medina", "Aguilar"),
    ("Karla", "Vega", "Delgado"), ("Oscar", "Navarro", "Pacheco"),
    ("Lucia", "Cabrera", "Fuentes"), ("Raul", "Espinoza", "Montes"),
    ("Monica", "Silva", "Herrera"), ("Javier", "Duran", "Peralta"),
]
OCUPACIONES = ["Comerciante", "Taxista", "Estilista", "Vendedor ambulante",
               "Costurera", "Carpintero", "Empleada domestica", "Tendero",
               "Mecanico", "Panadero"]
CIUDADES = [("Guadalajara", "JAL"), ("Monterrey", "NL"), ("Puebla", "PUE"),
            ("Leon", "GTO"), ("Merida", "YUC")]


class Command(BaseCommand):
    help = "Carga negocios, usuarios, clientes, creditos y pagos ficticios de demostracion."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password", default="Demo12345",
            help="Contrasena para los usuarios de demostracion.")
        parser.add_argument(
            "--semilla", type=int, default=2026,
            help="Semilla del generador aleatorio (para resultados reproducibles).")

    @transaction.atomic
    def handle(self, *args, **opciones):
        random.seed(opciones["semilla"])
        password = opciones["password"]
        hoy = hoy_local()

        if Negocio.objects.filter(nombre_comercial__startswith="[DEMO]").exists():
            self.stdout.write(self.style.WARNING(
                "Ya existen datos de demostracion. Se agregaran mas registros."))

        negocio1 = Negocio.objects.create(
            nombre_comercial="[DEMO] Creditos del Centro",
            razon_social="Creditos del Centro SA de CV",
            rfc="CDC010101AB1", telefono="3312345678",
            email="contacto@demo-creditos.mx",
            direccion="Av. Ficticia 100", ciudad="Guadalajara", estado="JAL",
            tasa_interes=Decimal("0.4000"), numero_cuotas=4,
            frecuencia_pago="semanal", dias_gracia=1,
            observaciones="Negocio de demostracion. Datos ficticios.",
        )
        negocio2 = Negocio.objects.create(
            nombre_comercial="[DEMO] Sucursal Norte",
            telefono="8112345678", ciudad="Monterrey", estado="NL",
            tasa_interes=Decimal("0.3000"), numero_cuotas=6,
            frecuencia_pago="quincenal", dias_gracia=3,
            permite_liquidacion_anticipada=True,
            descuento_liquidacion_anticipada=Decimal("0.2000"),
            observaciones="Sucursal de demostracion. Datos ficticios.",
        )

        admin = self._usuario("demo_admin", Rol.ADMIN, "Alma", "Administradora",
                              password, [negocio1, negocio2])
        gerente = self._usuario("demo_gerente", Rol.GERENTE, "Gustavo", "Gerente",
                                password, [negocio1])
        cobrador1 = self._usuario("demo_cobrador", Rol.COBRADOR, "Carlos", "Cobrador",
                                  password, [negocio1])
        cobrador2 = self._usuario("demo_cobrador2", Rol.COBRADOR, "Cecilia", "Cobradora",
                                  password, [negocio2])
        negocio1.responsable = admin
        negocio1.save(update_fields=["responsable"])
        negocio2.responsable = admin
        negocio2.save(update_fields=["responsable"])

        clientes = []
        for indice, (nombres, paterno, materno) in enumerate(NOMBRES):
            negocio = negocio1 if indice < 13 else negocio2
            cobrador = cobrador1 if negocio == negocio1 else cobrador2
            ciudad, estado = random.choice(CIUDADES)
            cliente = Cliente.objects.create(
                negocio=negocio, nombres=nombres, apellido_paterno=paterno,
                apellido_materno=materno,
                telefono_principal=f"55{random.randint(10000000, 99999999)}",
                ocupacion=random.choice(OCUPACIONES),
                direccion=f"Calle Ficticia {random.randint(1, 500)}",
                ciudad=ciudad, estado_republica=estado,
                codigo_postal=f"{random.randint(10000, 99999)}",
                cobrador=cobrador,
                estado=EstadoCliente.RESTRINGIDO if indice == 19 else EstadoCliente.ACTIVO,
                observaciones="Cliente de demostracion (datos ficticios).",
                creado_por=admin,
            )
            ReferenciaPersonal.objects.create(
                cliente=cliente, nombre="Referencia Demo",
                parentesco=random.choice(["Hermano", "Vecina", "Amiga", "Primo"]),
                telefono=f"55{random.randint(10000000, 99999999)}")
            clientes.append(cliente)

        creados = {"liquidados": 0, "activos": 0, "mora": 0, "pendientes": 0}

        # --- Creditos liquidados --------------------------------------------
        for cliente in clientes[:4]:
            credito = self._credito(cliente, admin, Decimal(random.choice([1000, 2000, 3000])),
                                    hoy - dt.timedelta(days=60))
            for _ in range(credito.numero_cuotas):
                credito.refresh_from_db()
                if credito.saldo_pendiente <= 0:
                    break
                servicios_pago.registrar_pago(
                    credito=credito, importe=credito.cuotas.exclude(
                        estado="pagada").first().saldo,
                    usuario=cliente.cobrador, cobrador=cliente.cobrador,
                    metodo=MetodoPago.EFECTIVO, forzar_duplicado=True,
                    fecha=timezone.now() - dt.timedelta(days=random.randint(1, 50)))
            creados["liquidados"] += 1

        # --- Creditos activos al corriente ----------------------------------
        for cliente in clientes[4:11]:
            credito = self._credito(cliente, admin, Decimal(random.choice([1500, 2500, 4000])),
                                    hoy - dt.timedelta(days=random.randint(0, 10)))
            if random.random() > 0.3:
                cuota = credito.cuotas.first()
                servicios_pago.registrar_pago(
                    credito=credito, importe=cuota.importe_programado,
                    usuario=cliente.cobrador, cobrador=cliente.cobrador,
                    forzar_duplicado=True)
            creados["activos"] += 1

        # --- Creditos con atraso y pagos parciales ---------------------------
        for cliente in clientes[11:17]:
            credito = self._credito(cliente, admin, Decimal(random.choice([2000, 5000, 8000])),
                                    hoy - dt.timedelta(days=random.randint(25, 70)))
            if random.random() > 0.4:
                servicios_pago.registrar_pago(
                    credito=credito, importe=Decimal(random.choice([200, 350, 500])),
                    usuario=cliente.cobrador, cobrador=cliente.cobrador,
                    forzar_duplicado=True,
                    fecha=timezone.now() - dt.timedelta(days=random.randint(1, 20)))
            servicios_credito.actualizar_estado(credito)
            GestionCobranza.objects.create(
                credito=credito, cliente=cliente, negocio=cliente.negocio,
                usuario=cliente.cobrador, fecha=timezone.now() - dt.timedelta(days=2),
                tipo=random.choice([TipoGestion.LLAMADA, TipoGestion.VISITA,
                                    TipoGestion.PROMESA]),
                resultado=random.choice([ResultadoGestion.PROMESA,
                                         ResultadoGestion.SIN_RESPUESTA,
                                         ResultadoGestion.REAGENDA]),
                monto_prometido=Decimal(random.choice([0, 350, 700])),
                fecha_promesa=hoy + dt.timedelta(days=3),
                proxima_fecha_contacto=hoy + dt.timedelta(days=1),
                observaciones="Gestion de demostracion.")
            creados["mora"] += 1

        # --- Creditos pendientes de aprobacion -------------------------------
        for cliente in clientes[17:19]:
            servicios_credito.crear_credito(
                cliente=cliente, negocio=cliente.negocio, capital=Decimal("3000"),
                numero_cuotas=cliente.negocio.numero_cuotas,
                frecuencia=cliente.negocio.frecuencia_pago,
                fecha_primer_pago=hoy + dt.timedelta(days=7), usuario=gerente,
                cobrador=cliente.cobrador,
                observaciones="Solicitud de demostracion pendiente de aprobacion.")
            creados["pendientes"] += 1

        self.stdout.write(self.style.SUCCESS("Datos de demostracion cargados:"))
        self.stdout.write(f"  Negocios: 2   Clientes: {len(clientes)}")
        self.stdout.write(
            f"  Creditos liquidados: {creados['liquidados']}, activos: {creados['activos']}, "
            f"con atraso: {creados['mora']}, pendientes: {creados['pendientes']}")
        self.stdout.write(f"  Usuarios (contrasena: {password}):")
        for usuario in [admin, gerente, cobrador1, cobrador2]:
            self.stdout.write(f"    {usuario.username} -> {usuario.get_rol_display()}")
        self.stdout.write(self.style.WARNING(
            "Todos los datos son ficticios. No uses informacion real de personas."))

    def _usuario(self, username, rol, nombre, apellido, password, negocios):
        usuario, creado = Usuario.objects.get_or_create(
            username=username,
            defaults={"rol": rol, "first_name": nombre, "last_name": apellido,
                      "email": f"{username}@demo.mx"},
        )
        if creado:
            usuario.set_password(password)
            usuario.save()
        usuario.negocios.add(*negocios)
        return usuario

    def _credito(self, cliente, usuario, capital, primer_pago):
        negocio = cliente.negocio
        credito = servicios_credito.crear_credito(
            cliente=cliente, negocio=negocio, capital=capital,
            numero_cuotas=negocio.numero_cuotas, frecuencia=negocio.frecuencia_pago,
            fecha_primer_pago=primer_pago, usuario=usuario, cobrador=cliente.cobrador,
            fecha_solicitud=primer_pago - dt.timedelta(days=1),
            observaciones="Credito de demostracion.")
        servicios_credito.aprobar_credito(credito, usuario,
                                          fecha=primer_pago - dt.timedelta(days=1))
        credito.refresh_from_db()
        servicios_credito.desembolsar_credito(credito, usuario,
                                              fecha=primer_pago - dt.timedelta(days=1))
        credito.refresh_from_db()
        return credito
