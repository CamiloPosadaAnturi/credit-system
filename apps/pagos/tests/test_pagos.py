"""Pruebas del registro y la aplicacion de pagos."""
import datetime as dt
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.core.errores import ErrorDePago
from apps.core.factorias import crear_cliente, crear_credito, crear_negocio, crear_usuario
from apps.core.fechas import hoy_local
from apps.creditos.models import EstadoCredito, EstadoCuota
from apps.pagos import servicios
from apps.pagos.models import EstadoPago, MetodoPago, Pago, TipoPago
from apps.usuarios.models import Rol


class BasePagosTests(TestCase):
    def setUp(self):
        self.negocio = crear_negocio()
        self.admin = crear_usuario("admin", Rol.ADMIN, [self.negocio])
        self.cliente = crear_cliente(self.negocio)
        # 1,000 de capital + 400 de interes = 1,400 en 4 cuotas de 350.
        self.credito = crear_credito(self.cliente, self.admin, Decimal("1000"), 4)


class AbonosTests(BasePagosTests):
    def test_abono_parcial_actualiza_cuota_y_saldo(self):
        servicios.registrar_pago(credito=self.credito, importe=Decimal("200"),
                                 usuario=self.admin)
        self.credito.refresh_from_db()
        cuota = self.credito.cuotas.first()
        self.assertEqual(cuota.importe_pagado, Decimal("200.00"))
        self.assertEqual(cuota.estado, EstadoCuota.PARCIAL)
        self.assertEqual(self.credito.saldo_pendiente, Decimal("1200.00"))

    def test_pago_exacto_de_cuota_la_marca_pagada(self):
        servicios.registrar_pago(credito=self.credito, importe=Decimal("350"),
                                 usuario=self.admin)
        cuota = self.credito.cuotas.first()
        cuota.refresh_from_db()
        self.assertEqual(cuota.estado, EstadoCuota.PAGADA)
        self.assertIsNotNone(cuota.fecha_liquidacion)

    def test_pago_cubre_varias_cuotas_en_orden(self):
        servicios.registrar_pago(credito=self.credito, importe=Decimal("800"),
                                 usuario=self.admin)
        cuotas = list(self.credito.cuotas.order_by("numero"))
        self.assertEqual(cuotas[0].estado, EstadoCuota.PAGADA)
        self.assertEqual(cuotas[1].estado, EstadoCuota.PAGADA)
        self.assertEqual(cuotas[2].importe_pagado, Decimal("100.00"))
        self.assertEqual(cuotas[3].importe_pagado, Decimal("0.00"))

    def test_separacion_de_capital_e_interes(self):
        """Dentro de una cuota se cubre primero el interes y luego el capital."""
        pago = servicios.registrar_pago(credito=self.credito, importe=Decimal("350"),
                                        usuario=self.admin)
        aplicacion = pago.aplicaciones.get()
        self.assertEqual(aplicacion.interes, Decimal("100.00"))
        self.assertEqual(aplicacion.capital, Decimal("250.00"))
        self.credito.refresh_from_db()
        self.assertEqual(self.credito.interes_pagado, Decimal("100.00"))
        self.assertEqual(self.credito.capital_pagado, Decimal("250.00"))

    def test_abono_menor_al_interes_solo_cubre_interes(self):
        pago = servicios.registrar_pago(credito=self.credito, importe=Decimal("60"),
                                        usuario=self.admin)
        aplicacion = pago.aplicaciones.get()
        self.assertEqual(aplicacion.interes, Decimal("60.00"))
        self.assertEqual(aplicacion.capital, Decimal("0.00"))

    def test_pago_total_liquida_el_credito(self):
        servicios.registrar_pago(credito=self.credito, importe=Decimal("1400"),
                                 usuario=self.admin)
        self.credito.refresh_from_db()
        self.assertEqual(self.credito.saldo_pendiente, Decimal("0.00"))
        self.assertEqual(self.credito.estado, EstadoCredito.LIQUIDADO)
        self.assertEqual(self.credito.capital_pagado, Decimal("1000.00"))
        self.assertEqual(self.credito.interes_pagado, Decimal("400.00"))
        self.assertFalse(self.credito.cuotas.exclude(estado=EstadoCuota.PAGADA).exists())

    def test_el_interes_no_se_recalcula_al_pagar(self):
        for _ in range(4):
            servicios.registrar_pago(credito=self.credito, importe=Decimal("350"),
                                     usuario=self.admin, forzar_duplicado=True)
        self.credito.refresh_from_db()
        self.assertEqual(self.credito.interes_total, Decimal("400.00"))
        self.assertEqual(self.credito.total_a_pagar, Decimal("1400.00"))
        self.assertEqual(self.credito.saldo_pendiente, Decimal("0.00"))

    def test_importe_cero_o_negativo(self):
        for importe in [Decimal("0"), Decimal("-100")]:
            with self.subTest(importe=importe):
                with self.assertRaises(ErrorDePago):
                    servicios.registrar_pago(credito=self.credito, importe=importe,
                                             usuario=self.admin)

    def test_pago_mayor_al_saldo_requiere_autorizacion(self):
        with self.assertRaises(ErrorDePago):
            servicios.registrar_pago(credito=self.credito, importe=Decimal("2000"),
                                     usuario=self.admin)
        pago = servicios.registrar_pago(credito=self.credito, importe=Decimal("2000"),
                                        usuario=self.admin, permitir_excedente=True)
        self.assertEqual(pago.importe_aplicado, Decimal("1400.00"))
        self.assertEqual(pago.excedente, Decimal("600.00"))

    def test_no_se_paga_un_credito_no_vigente(self):
        servicios.registrar_pago(credito=self.credito, importe=Decimal("1400"),
                                 usuario=self.admin)
        self.credito.refresh_from_db()
        with self.assertRaises(ErrorDePago):
            servicios.registrar_pago(credito=self.credito, importe=Decimal("50"),
                                     usuario=self.admin)


class DuplicadosTests(BasePagosTests):
    def test_clave_de_idempotencia_evita_el_doble_registro(self):
        primero = servicios.registrar_pago(
            credito=self.credito, importe=Decimal("350"), usuario=self.admin,
            clave_idempotencia="abc123")
        segundo = servicios.registrar_pago(
            credito=self.credito, importe=Decimal("350"), usuario=self.admin,
            clave_idempotencia="abc123")
        self.assertEqual(primero.pk, segundo.pk)
        self.assertEqual(Pago.objects.count(), 1)
        self.credito.refresh_from_db()
        self.assertEqual(self.credito.saldo_pendiente, Decimal("1050.00"))

    def test_pago_identico_inmediato_se_bloquea(self):
        servicios.registrar_pago(credito=self.credito, importe=Decimal("350"),
                                 usuario=self.admin)
        with self.assertRaises(ErrorDePago):
            servicios.registrar_pago(credito=self.credito, importe=Decimal("350"),
                                     usuario=self.admin)

    def test_pago_identico_puede_confirmarse_explicitamente(self):
        servicios.registrar_pago(credito=self.credito, importe=Decimal("350"),
                                 usuario=self.admin)
        servicios.registrar_pago(credito=self.credito, importe=Decimal("350"),
                                 usuario=self.admin, forzar_duplicado=True)
        self.assertEqual(Pago.objects.confirmados().count(), 2)


class ReversosTests(BasePagosTests):
    def test_reverso_restaura_el_saldo_y_conserva_el_registro(self):
        pago = servicios.registrar_pago(credito=self.credito, importe=Decimal("700"),
                                        usuario=self.admin)
        servicios.reversar_pago(pago, self.admin, "Deposito no acreditado")
        pago.refresh_from_db()
        self.credito.refresh_from_db()
        self.assertEqual(pago.estado, EstadoPago.REVERSADO)
        self.assertEqual(pago.motivo_reverso, "Deposito no acreditado")
        self.assertEqual(Pago.objects.count(), 1)  # nunca se borra
        self.assertEqual(self.credito.saldo_pendiente, Decimal("1400.00"))
        self.assertEqual(self.credito.cuotas.first().importe_pagado, Decimal("0.00"))

    def test_reverso_devuelve_un_credito_liquidado_a_vigente(self):
        pago = servicios.registrar_pago(credito=self.credito, importe=Decimal("1400"),
                                        usuario=self.admin)
        self.credito.refresh_from_db()
        self.assertEqual(self.credito.estado, EstadoCredito.LIQUIDADO)
        servicios.reversar_pago(pago, self.admin, "Error de captura")
        self.credito.refresh_from_db()
        self.assertIn(self.credito.estado, [EstadoCredito.ACTIVO, EstadoCredito.EN_MORA])
        self.assertEqual(self.credito.saldo_pendiente, Decimal("1400.00"))

    def test_reverso_requiere_motivo_y_no_se_repite(self):
        pago = servicios.registrar_pago(credito=self.credito, importe=Decimal("350"),
                                        usuario=self.admin)
        with self.assertRaises(ErrorDePago):
            servicios.reversar_pago(pago, self.admin, "")
        servicios.reversar_pago(pago, self.admin, "Motivo valido")
        with self.assertRaises(ErrorDePago):
            servicios.reversar_pago(pago, self.admin, "Otra vez")


class AplicacionAVencidasTests(TestCase):
    def setUp(self):
        self.negocio = crear_negocio()
        self.admin = crear_usuario("admin", Rol.ADMIN, [self.negocio])
        self.cliente = crear_cliente(self.negocio)
        self.credito = crear_credito(
            self.cliente, self.admin, Decimal("1000"), 4,
            primer_pago=hoy_local() - dt.timedelta(days=14))

    def test_el_pago_cubre_primero_la_cuota_vencida_mas_antigua(self):
        pago = servicios.registrar_pago(credito=self.credito, importe=Decimal("350"),
                                        usuario=self.admin)
        aplicacion = pago.aplicaciones.get()
        self.assertEqual(aplicacion.cuota.numero, 1)

    def test_saldo_vencido_se_reduce_con_el_pago(self):
        vencido_inicial = servicios.saldo_vencido(self.credito)
        self.assertEqual(vencido_inicial, Decimal("700.00"))  # cuotas 1 y 2 vencidas
        servicios.registrar_pago(credito=self.credito, importe=Decimal("350"),
                                 usuario=self.admin)
        self.assertEqual(servicios.saldo_vencido(self.credito), Decimal("350.00"))


class LiquidacionAnticipadaTests(BasePagosTests):
    def test_sin_descuento_se_paga_el_saldo_completo(self):
        calculo = servicios.calcular_liquidacion_anticipada(self.credito)
        self.assertEqual(calculo["descuento"], Decimal("0.00"))
        self.assertEqual(calculo["importe_liquidacion"], Decimal("1400.00"))
        servicios.liquidar_anticipadamente(self.credito, self.admin)
        self.credito.refresh_from_db()
        self.assertEqual(self.credito.estado, EstadoCredito.LIQUIDADO)
        self.assertEqual(self.credito.saldo_pendiente, Decimal("0.00"))

    def test_con_descuento_se_registra_una_condonacion(self):
        self.negocio.descuento_liquidacion_anticipada = Decimal("0.5000")
        self.negocio.save()
        credito = crear_credito(
            self.cliente, self.admin, Decimal("1000"), 4,
            primer_pago=hoy_local() + dt.timedelta(days=7))
        calculo = servicios.calcular_liquidacion_anticipada(credito)
        # Las 4 cuotas vencen en el futuro: interes no devengado = 400.
        self.assertEqual(calculo["interes_no_devengado"], Decimal("400.00"))
        self.assertEqual(calculo["descuento"], Decimal("200.00"))
        self.assertEqual(calculo["importe_liquidacion"], Decimal("1200.00"))

        servicios.liquidar_anticipadamente(credito, self.admin)
        credito.refresh_from_db()
        self.assertEqual(credito.estado, EstadoCredito.LIQUIDADO)
        self.assertEqual(credito.saldo_pendiente, Decimal("0.00"))
        condonacion = credito.pagos.get(tipo=TipoPago.CONDONACION)
        self.assertEqual(condonacion.importe, Decimal("200.00"))
        # El efectivo realmente recibido son 1,200, no 1,400:
        # la condonacion no cuenta como dinero cobrado.
        recibido = sum(p.importe for p in credito.pagos.en_efectivo_real())
        self.assertEqual(recibido, Decimal("1200.00"))

    def test_negocio_que_no_permite_liquidacion(self):
        self.negocio.permite_liquidacion_anticipada = False
        self.negocio.save()
        with self.assertRaises(ErrorDePago):
            servicios.liquidar_anticipadamente(self.credito, self.admin)


class MetodosYFoliosTests(BasePagosTests):
    def test_folio_consecutivo_por_negocio(self):
        primero = servicios.registrar_pago(credito=self.credito, importe=Decimal("100"),
                                           usuario=self.admin)
        segundo = servicios.registrar_pago(credito=self.credito, importe=Decimal("150"),
                                           usuario=self.admin)
        self.assertTrue(primero.folio.startswith("PG-"))
        self.assertEqual(int(segundo.folio.split("-")[-1]),
                         int(primero.folio.split("-")[-1]) + 1)

    def test_metodos_de_pago(self):
        pago = servicios.registrar_pago(
            credito=self.credito, importe=Decimal("100"), usuario=self.admin,
            metodo=MetodoPago.TRANSFERENCIA, referencia="REF-001",
            fecha=timezone.now())
        self.assertEqual(pago.metodo, MetodoPago.TRANSFERENCIA)
        self.assertEqual(pago.referencia, "REF-001")
