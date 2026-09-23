"""Pruebas de integracion: del alta del credito a su liquidacion."""
import datetime as dt
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.core.factorias import crear_cliente, crear_negocio, crear_usuario
from apps.core.fechas import hoy_local
from apps.creditos import servicios as servicios_credito
from apps.creditos.models import Credito, EstadoCredito, EstadoCuota
from apps.pagos import servicios as servicios_pago
from apps.pagos.models import AplicacionPago, EstadoPago
from apps.usuarios.models import Rol


class FlujoCompletoTests(TestCase):
    """1,000 MXN al 40%, 4 cuotas semanales de 350, pagadas una por una."""

    def setUp(self):
        self.negocio = crear_negocio()
        self.admin = crear_usuario("admin", Rol.ADMIN, [self.negocio])
        self.cobrador = crear_usuario("cobrador", Rol.COBRADOR, [self.negocio])
        self.cliente = crear_cliente(self.negocio, cobrador=self.cobrador)

    def test_del_alta_a_la_liquidacion(self):
        inicio = hoy_local() - dt.timedelta(days=21)
        credito = servicios_credito.crear_credito(
            cliente=self.cliente, negocio=self.negocio, capital=Decimal("1000"),
            numero_cuotas=4, frecuencia="semanal", fecha_primer_pago=inicio,
            usuario=self.admin, cobrador=self.cobrador)

        self.assertEqual(credito.estado, EstadoCredito.PENDIENTE)
        self.assertEqual(credito.total_a_pagar, Decimal("1400.00"))

        servicios_credito.aprobar_credito(credito, self.admin)
        credito.refresh_from_db()
        servicios_credito.desembolsar_credito(credito, self.admin)
        credito.refresh_from_db()
        self.assertEqual(credito.estado, EstadoCredito.EN_MORA)  # 3 cuotas ya vencidas

        saldos_esperados = ["1050.00", "700.00", "350.00", "0.00"]
        for indice, esperado in enumerate(saldos_esperados):
            servicios_pago.registrar_pago(
                credito=credito, importe=Decimal("350"), usuario=self.cobrador,
                cobrador=self.cobrador, forzar_duplicado=True)
            credito.refresh_from_db()
            self.assertEqual(credito.saldo_pendiente, Decimal(esperado),
                             f"saldo incorrecto tras el pago {indice + 1}")

        self.assertEqual(credito.estado, EstadoCredito.LIQUIDADO)
        self.assertEqual(credito.capital_pagado, Decimal("1000.00"))
        self.assertEqual(credito.interes_pagado, Decimal("400.00"))
        self.assertEqual(credito.cuotas.filter(estado=EstadoCuota.PAGADA).count(), 4)

        # El saldo se puede reconstruir desde las aplicaciones de pago.
        aplicado = sum(
            aplicacion.importe for aplicacion in AplicacionPago.objects.filter(
                cuota__credito=credito, pago__estado=EstadoPago.CONFIRMADO))
        self.assertEqual(aplicado, credito.total_a_pagar)

    def test_pagos_irregulares_y_reverso(self):
        credito = servicios_credito.crear_credito(
            cliente=self.cliente, negocio=self.negocio, capital=Decimal("3000"),
            numero_cuotas=6, frecuencia="quincenal", fecha_primer_pago=hoy_local(),
            usuario=self.admin)
        servicios_credito.aprobar_credito(credito, self.admin)
        credito.refresh_from_db()
        servicios_credito.desembolsar_credito(credito, self.admin)
        credito.refresh_from_db()
        self.assertEqual(credito.total_a_pagar, Decimal("4200.00"))
        self.assertEqual(credito.importe_cuota, Decimal("700.00"))

        servicios_pago.registrar_pago(credito=credito, importe=Decimal("250"),
                                      usuario=self.admin)
        servicios_pago.registrar_pago(credito=credito, importe=Decimal("1000"),
                                      usuario=self.admin)
        malo = servicios_pago.registrar_pago(credito=credito, importe=Decimal("500"),
                                             usuario=self.admin)
        credito.refresh_from_db()
        self.assertEqual(credito.saldo_pendiente, Decimal("2450.00"))

        servicios_pago.reversar_pago(malo, self.admin, "Cheque devuelto")
        credito.refresh_from_db()
        self.assertEqual(credito.saldo_pendiente, Decimal("2950.00"))
        self.assertEqual(credito.total_pagado, Decimal("1250.00"))

        servicios_pago.liquidar_anticipadamente(credito, self.admin)
        credito.refresh_from_db()
        self.assertEqual(credito.estado, EstadoCredito.LIQUIDADO)
        self.assertEqual(credito.saldo_pendiente, Decimal("0.00"))


class VistasPrincipalesTests(TestCase):
    """Comprueba que las pantallas principales responden 200 con datos reales."""

    def setUp(self):
        self.negocio = crear_negocio()
        self.admin = crear_usuario("admin", Rol.ADMIN, [self.negocio])
        self.cliente = crear_cliente(self.negocio)
        from apps.core.factorias import crear_credito

        self.credito = crear_credito(self.cliente, self.admin, Decimal("2000"), 4)
        servicios_pago.registrar_pago(credito=self.credito, importe=Decimal("700"),
                                      usuario=self.admin)
        self.client.force_login(self.admin)

    def test_pantallas(self):
        rutas = [
            reverse("dashboard:inicio"),
            reverse("negocios:lista"),
            reverse("negocios:detalle", args=[self.negocio.pk]),
            reverse("negocios:dashboard", args=[self.negocio.pk]),
            reverse("clientes:lista"),
            reverse("clientes:detalle", args=[self.cliente.pk]),
            reverse("creditos:lista"),
            reverse("creditos:detalle", args=[self.credito.pk]),
            reverse("creditos:calendario", args=[self.credito.pk]),
            reverse("pagos:lista"),
            reverse("pagos:registrar", args=[self.credito.pk]),
            reverse("pagos:liquidar", args=[self.credito.pk]),
            reverse("cobranza:tablero"),
            reverse("cobranza:mi_cartera"),
            reverse("cobranza:gestiones"),
            reverse("cobranza:registrar_gestion", args=[self.credito.pk]),
            reverse("reportes:catalogo"),
            reverse("auditoria:lista"),
            reverse("notificaciones:lista"),
            reverse("usuarios:lista"),
            reverse("usuarios:perfil"),
        ]
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 200)

    def test_todos_los_reportes_responden(self):
        from apps.reportes.definiciones import REPORTES

        for clave in REPORTES:
            with self.subTest(reporte=clave):
                respuesta = self.client.get(reverse("reportes:detalle", args=[clave]))
                self.assertEqual(respuesta.status_code, 200)

    def test_exportacion_csv_y_excel(self):
        csv = self.client.get(reverse("reportes:detalle", args=["creditos_otorgados"]),
                              {"formato": "csv"})
        self.assertEqual(csv.status_code, 200)
        self.assertIn("text/csv", csv["Content-Type"])

        excel = self.client.get(reverse("reportes:detalle", args=["cartera"]),
                                {"formato": "excel"})
        self.assertEqual(excel.status_code, 200)
        self.assertIn("spreadsheetml", excel["Content-Type"])

    def test_registro_de_pago_por_la_vista(self):
        respuesta = self.client.post(
            reverse("pagos:registrar", args=[self.credito.pk]),
            {"importe": "500", "metodo": "efectivo", "clave_idempotencia": "form-1"},
            follow=True)
        self.assertEqual(respuesta.status_code, 200)
        self.credito.refresh_from_db()
        self.assertEqual(self.credito.saldo_pendiente, Decimal("1600.00"))

        # Reenviar el mismo formulario (misma clave) no duplica el pago.
        self.client.post(
            reverse("pagos:registrar", args=[self.credito.pk]),
            {"importe": "500", "metodo": "efectivo", "clave_idempotencia": "form-1"},
            follow=True)
        self.credito.refresh_from_db()
        self.assertEqual(self.credito.saldo_pendiente, Decimal("1600.00"))
        self.assertEqual(self.credito.pagos.confirmados().count(), 2)

    def test_alta_de_credito_por_la_vista(self):
        datos = {
            "negocio": self.negocio.pk, "cliente": self.cliente.pk,
            "fecha_solicitud": hoy_local().isoformat(),
            "capital": "5000", "modalidad_interes": "fijo_capital",
            "tasa_interes": "0.40", "periodo_tasa": "contrato",
            "frecuencia_pago": "semanal", "numero_cuotas": 10,
            "fecha_primer_pago": hoy_local().isoformat(),
        }
        # Primer envio: pantalla de confirmacion, sin crear nada.
        previa = self.client.post(reverse("creditos:crear"), datos)
        self.assertEqual(previa.status_code, 200)
        self.assertContains(previa, "Confirmar")
        self.assertEqual(Credito.objects.filter(capital=Decimal("5000")).count(), 0)

        datos["confirmar"] = "1"
        final = self.client.post(reverse("creditos:crear"), datos, follow=True)
        self.assertEqual(final.status_code, 200)
        credito = Credito.objects.get(capital=Decimal("5000"))
        self.assertEqual(credito.interes_total, Decimal("2000.00"))
        self.assertEqual(credito.total_a_pagar, Decimal("7000.00"))
        self.assertEqual(credito.cuotas.count(), 10)
