"""Pruebas de clasificacion de cartera y calculo de mora."""
import datetime as dt
from decimal import Decimal

from django.test import TestCase

from apps.cobranza import servicios
from apps.core.factorias import crear_cliente, crear_credito, crear_negocio, crear_usuario
from apps.core.fechas import hoy_local
from apps.creditos.models import Credito
from apps.pagos.servicios import registrar_pago
from apps.usuarios.models import Rol


class MoraTests(TestCase):
    def setUp(self):
        self.negocio = crear_negocio()
        self.admin = crear_usuario("admin", Rol.ADMIN, [self.negocio])
        self.cliente = crear_cliente(self.negocio)
        self.hoy = hoy_local()

    def crear(self, dias_atras=0, capital=Decimal("1000"), cuotas=4):
        return crear_credito(
            self.cliente, self.admin, capital, cuotas,
            primer_pago=self.hoy - dt.timedelta(days=dias_atras))

    def test_cuotas_que_vencen_hoy(self):
        self.crear(dias_atras=0)
        self.assertEqual(servicios.cuotas_que_vencen(Credito.objects.all(), self.hoy).count(), 1)

    def test_cuotas_vencidas_y_saldo_vencido(self):
        self.crear(dias_atras=14)  # cuotas 1 y 2 vencidas (dia 0 y dia 7)
        vencidas = servicios.cuotas_vencidas(Credito.objects.all(), self.hoy)
        self.assertEqual(vencidas.count(), 2)
        self.assertEqual(
            servicios.saldo_vencido_queryset(Credito.objects.all(), self.hoy),
            Decimal("700.00"))

    def test_dias_de_atraso_de_cuota_y_de_credito(self):
        credito = self.crear(dias_atras=20)
        cuota_mas_antigua = credito.cuotas.order_by("numero").first()
        self.assertEqual(cuota_mas_antigua.dias_atraso, 20)
        self.assertEqual(credito.dias_atraso, 20)  # el del credito = su cuota mas vieja

    def test_cuota_pagada_no_cuenta_como_atraso(self):
        credito = self.crear(dias_atras=14)
        registrar_pago(credito=credito, importe=Decimal("350"), usuario=self.admin)
        credito.refresh_from_db()
        self.assertEqual(servicios.cuotas_vencidas(Credito.objects.all(), self.hoy).count(), 1)
        self.assertEqual(credito.dias_atraso, 7)

    def test_saldo_vencido_vs_saldo_total(self):
        credito = self.crear(dias_atras=14)
        self.assertEqual(credito.saldo_vencido, Decimal("700.00"))
        self.assertEqual(credito.saldo_pendiente, Decimal("1400.00"))

    def test_filtro_por_atraso_minimo(self):
        self.crear(dias_atras=14)
        self.assertEqual(
            servicios.cuotas_vencidas(Credito.objects.all(), self.hoy, dias_minimos=10).count(),
            1)
        self.assertEqual(
            servicios.cuotas_vencidas(Credito.objects.all(), self.hoy, dias_minimos=30).count(),
            0)

    def test_clasificacion_de_cartera(self):
        self.crear(dias_atras=14)
        self.crear(dias_atras=0)
        clasificacion = servicios.clasificacion_cartera(Credito.objects.all(), self.hoy)
        self.assertEqual(clasificacion["creditos_activos"], 2)
        self.assertEqual(clasificacion["vencen_hoy"], 2)
        self.assertEqual(clasificacion["vencidas"], 2)
        self.assertEqual(clasificacion["saldo_total"], Decimal("2800.00"))
        self.assertEqual(clasificacion["clientes_multiples_creditos"], 1)

    def test_sin_politica_no_hay_cargo_moratorio(self):
        credito = self.crear(dias_atras=30)
        self.assertEqual(servicios.calcular_cargo_moratorio(credito, self.hoy), Decimal("0.00"))

    def test_cargo_moratorio_solo_si_esta_configurado(self):
        self.negocio.aplica_mora = True
        self.negocio.tasa_mora = Decimal("0.0100")  # 1% diario sobre el saldo vencido
        self.negocio.save()
        credito = self.crear(dias_atras=7)
        credito.refresh_from_db()
        # Cuota 1 (350) con 7 dias de atraso: 350 * 0.01 * 7 = 24.50
        self.assertEqual(servicios.calcular_cargo_moratorio(credito, self.hoy), Decimal("24.50"))

    def test_resumen_de_mora_por_credito(self):
        credito = self.crear(dias_atras=21)
        filas = servicios.resumen_mora_por_credito(Credito.objects.all(), self.hoy)
        self.assertEqual(len(filas), 1)
        fila = filas[0]
        self.assertEqual(fila["credito"], credito)
        self.assertEqual(fila["cuotas_vencidas"], 3)
        self.assertEqual(fila["saldo_vencido"], Decimal("1050.00"))
        self.assertEqual(fila["dias_atraso"], 21)
