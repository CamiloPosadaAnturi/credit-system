"""Pruebas del ciclo de vida del credito."""
import datetime as dt
from decimal import Decimal

from django.test import TestCase

from apps.core.errores import ErrorDeCredito
from apps.core.factorias import crear_cliente, crear_credito, crear_negocio, crear_usuario
from apps.core.fechas import hoy_local
from apps.creditos import servicios
from apps.creditos.models import Credito, EstadoCredito
from apps.usuarios.models import Rol


class CicloDeVidaTests(TestCase):
    def setUp(self):
        self.negocio = crear_negocio()
        self.admin = crear_usuario("admin", Rol.ADMIN, [self.negocio])
        self.cliente = crear_cliente(self.negocio)

    def test_creacion_calcula_interes_y_calendario(self):
        credito = crear_credito(self.cliente, self.admin, Decimal("1000"), 4,
                                desembolsar=False)
        self.assertEqual(credito.interes_total, Decimal("400.00"))
        self.assertEqual(credito.total_a_pagar, Decimal("1400.00"))
        self.assertEqual(credito.cuotas.count(), 4)
        self.assertEqual(credito.importe_cuota, Decimal("350.00"))
        self.assertEqual(credito.estado, EstadoCredito.PENDIENTE)
        self.assertTrue(credito.folio.startswith("CR-"))

    def test_folios_unicos_y_consecutivos(self):
        primero = crear_credito(self.cliente, self.admin, desembolsar=False)
        segundo = crear_credito(self.cliente, self.admin, desembolsar=False)
        self.assertNotEqual(primero.folio, segundo.folio)
        self.assertEqual(int(segundo.folio.split("-")[-1]),
                         int(primero.folio.split("-")[-1]) + 1)

    def test_flujo_aprobacion_desembolso(self):
        credito = crear_credito(self.cliente, self.admin, desembolsar=False)
        servicios.aprobar_credito(credito, self.admin)
        credito.refresh_from_db()
        self.assertEqual(credito.estado, EstadoCredito.APROBADO)
        self.assertEqual(credito.fecha_aprobacion, hoy_local())

        servicios.desembolsar_credito(credito, self.admin)
        credito.refresh_from_db()
        self.assertEqual(credito.estado, EstadoCredito.ACTIVO)
        self.assertEqual(credito.saldo_pendiente, Decimal("1400.00"))

    def test_no_se_desembolsa_sin_aprobar(self):
        credito = crear_credito(self.cliente, self.admin, desembolsar=False)
        with self.assertRaises(ErrorDeCredito):
            servicios.desembolsar_credito(credito, self.admin)

    def test_credito_desembolsado_no_es_editable(self):
        credito = crear_credito(self.cliente, self.admin)
        self.assertFalse(credito.es_editable)
        with self.assertRaises(ErrorDeCredito):
            servicios.recalcular_condiciones(credito, self.admin)

    def test_tasa_del_credito_no_cambia_al_cambiar_la_del_negocio(self):
        credito = crear_credito(self.cliente, self.admin)
        self.negocio.tasa_interes = Decimal("0.6000")
        self.negocio.save()
        credito.refresh_from_db()
        self.assertEqual(credito.tasa_interes, Decimal("0.4000"))
        self.assertEqual(credito.interes_total, Decimal("400.00"))

    def test_cancelacion_requiere_motivo_y_sin_pagos(self):
        credito = crear_credito(self.cliente, self.admin)
        with self.assertRaises(ErrorDeCredito):
            servicios.cancelar_credito(credito, self.admin, "")
        servicios.cancelar_credito(credito, self.admin, "Cliente desistio")
        credito.refresh_from_db()
        self.assertEqual(credito.estado, EstadoCredito.CANCELADO)
        self.assertEqual(credito.saldo_pendiente, Decimal("0.00"))

    def test_cliente_restringido_no_se_aprueba(self):
        self.cliente.estado = "restringido"
        self.cliente.save()
        credito = crear_credito(self.cliente, self.admin, desembolsar=False)
        with self.assertRaises(ErrorDeCredito):
            servicios.aprobar_credito(credito, self.admin)

    def test_credito_de_cliente_de_otro_negocio(self):
        otro = crear_negocio("Otro negocio")
        with self.assertRaises(ErrorDeCredito):
            servicios.crear_credito(
                cliente=self.cliente, negocio=otro, capital=Decimal("1000"),
                numero_cuotas=4, frecuencia="semanal",
                fecha_primer_pago=hoy_local(), usuario=self.admin)

    def test_reestructuracion_conserva_el_historial(self):
        from apps.pagos.servicios import registrar_pago

        credito = crear_credito(self.cliente, self.admin, Decimal("1000"), 4)
        registrar_pago(credito=credito, importe=Decimal("350"), usuario=self.admin)
        credito.refresh_from_db()

        nuevo = servicios.reestructurar_credito(
            credito, self.admin, numero_cuotas=6, frecuencia="semanal",
            fecha_primer_pago=hoy_local() + dt.timedelta(days=7))

        credito.refresh_from_db()
        self.assertEqual(credito.estado, EstadoCredito.REESTRUCTURADO)
        self.assertEqual(credito.saldo_pendiente, Decimal("0.00"))
        self.assertEqual(credito.pagos.count(), 1)  # el pago original sigue ahi
        self.assertEqual(nuevo.capital, Decimal("1050.00"))  # saldo reestructurado
        self.assertEqual(nuevo.credito_origen_id, credito.pk)
        self.assertEqual(nuevo.numero_cuotas, 6)
        self.assertEqual(nuevo.estado, EstadoCredito.ACTIVO)

    def test_calendario_no_se_regenera_con_pagos_aplicados(self):
        from apps.pagos.servicios import registrar_pago

        credito = crear_credito(self.cliente, self.admin)
        registrar_pago(credito=credito, importe=Decimal("100"), usuario=self.admin)
        credito.refresh_from_db()
        with self.assertRaises(ErrorDeCredito):
            servicios.generar_calendario(credito)


class EstadosDerivadosTests(TestCase):
    def setUp(self):
        self.negocio = crear_negocio()
        self.admin = crear_usuario("admin", Rol.ADMIN, [self.negocio])
        self.cliente = crear_cliente(self.negocio)

    def test_credito_con_cuota_vencida_queda_en_mora(self):
        credito = crear_credito(
            self.cliente, self.admin, Decimal("1000"), 4,
            primer_pago=hoy_local() - dt.timedelta(days=10))
        servicios.actualizar_estado(credito)
        credito.refresh_from_db()
        self.assertEqual(credito.estado, EstadoCredito.EN_MORA)
        self.assertGreaterEqual(credito.dias_atraso, 10)

    def test_dias_de_gracia_evitan_la_mora(self):
        self.negocio.dias_gracia = 15
        self.negocio.save()
        credito = crear_credito(
            self.cliente, self.admin, Decimal("1000"), 4,
            primer_pago=hoy_local() - dt.timedelta(days=10))
        servicios.actualizar_estado(credito)
        credito.refresh_from_db()
        self.assertEqual(credito.estado, EstadoCredito.ACTIVO)

    def test_actualizacion_masiva(self):
        credito = crear_credito(self.cliente, self.admin, Decimal("1000"), 4,
                                primer_pago=hoy_local() - dt.timedelta(days=30))
        # Se fuerza un estado desactualizado para comprobar que el barrido lo corrige.
        Credito.objects.filter(pk=credito.pk).update(estado=EstadoCredito.ACTIVO)
        cambiados = servicios.actualizar_estados_masivo(Credito.objects.vigentes())
        self.assertEqual(cambiados, 1)
        credito.refresh_from_db()
        self.assertEqual(credito.estado, EstadoCredito.EN_MORA)
        # Un segundo barrido ya no cambia nada.
        self.assertEqual(
            servicios.actualizar_estados_masivo(Credito.objects.vigentes()), 0)
