"""Pruebas de los calculos financieros puros."""
import datetime as dt
from decimal import Decimal

from django.test import SimpleTestCase

from apps.core.dinero import dividir_en_cuotas, q
from apps.core.opciones import FrecuenciaPago, ModalidadInteres
from apps.creditos.calculos import (
    calcular_interes,
    calcular_total_a_pagar,
    construir_calendario,
    fechas_de_vencimiento,
    simular,
)

FIJO = ModalidadInteres.FIJO_CAPITAL


class InteresPorCadaMilTests(SimpleTestCase):
    """La regla comercial: 400 MXN de interes por cada 1,000 MXN prestados."""

    def test_tabla_de_la_regla_comercial(self):
        casos = [
            ("1000", "400.00", "1400.00"),
            ("2000", "800.00", "2800.00"),
            ("3000", "1200.00", "4200.00"),
            ("5000", "2000.00", "7000.00"),
            ("10000", "4000.00", "14000.00"),
        ]
        for capital, interes_esperado, total_esperado in casos:
            with self.subTest(capital=capital):
                interes = calcular_interes(Decimal(capital), FIJO, Decimal("0.40"))
                self.assertEqual(interes, Decimal(interes_esperado))
                self.assertEqual(
                    calcular_total_a_pagar(Decimal(capital), interes),
                    Decimal(total_esperado),
                )

    def test_capital_no_divisible_redondea_a_centavos(self):
        interes = calcular_interes(Decimal("1333.33"), FIJO, Decimal("0.40"))
        self.assertEqual(interes, Decimal("533.33"))

    def test_sin_interes(self):
        self.assertEqual(
            calcular_interes(Decimal("1000"), ModalidadInteres.SIN_INTERES, Decimal("0.40")),
            Decimal("0.00"),
        )

    def test_interes_simple_por_periodo_no_es_compuesto(self):
        # 1,000 al 5% por periodo, 4 periodos = 200, NO 215.51 (compuesto).
        interes = calcular_interes(
            Decimal("1000"), ModalidadInteres.SIMPLE_PERIODO, Decimal("0.05"), 4)
        self.assertEqual(interes, Decimal("200.00"))

    def test_capital_invalido(self):
        with self.assertRaises(ValueError):
            calcular_interes(Decimal("0"), FIJO, Decimal("0.40"))

    def test_tasa_negativa(self):
        with self.assertRaises(ValueError):
            calcular_interes(Decimal("1000"), FIJO, Decimal("-0.1"))


class RedondeoDeCuotasTests(SimpleTestCase):
    def test_suma_de_cuotas_igual_al_total(self):
        for total, numero in [("1400", 4), ("1000", 3), ("999.99", 7), ("100", 6)]:
            with self.subTest(total=total, numero=numero):
                cuotas = dividir_en_cuotas(Decimal(total), numero)
                self.assertEqual(len(cuotas), numero)
                self.assertEqual(sum(cuotas), q(Decimal(total)))

    def test_ultima_cuota_absorbe_la_diferencia(self):
        cuotas = dividir_en_cuotas(Decimal("1000"), 3)
        self.assertEqual(cuotas, [Decimal("333.33"), Decimal("333.33"), Decimal("333.34")])

    def test_una_sola_cuota(self):
        self.assertEqual(dividir_en_cuotas(Decimal("1400"), 1), [Decimal("1400.00")])

    def test_cero_cuotas_es_error(self):
        with self.assertRaises(ValueError):
            dividir_en_cuotas(Decimal("1000"), 0)


class CalendarioTests(SimpleTestCase):
    def setUp(self):
        self.inicio = dt.date(2026, 1, 5)

    def test_ejemplo_del_prompt_cuatro_cuotas_semanales(self):
        calendario = construir_calendario(
            Decimal("1000"), Decimal("400"), 4, self.inicio, FrecuenciaPago.SEMANAL)
        self.assertEqual(len(calendario), 4)
        for fila in calendario:
            self.assertEqual(fila["importe_programado"], Decimal("350.00"))
        self.assertEqual(
            [f["fecha_vencimiento"] for f in calendario],
            [dt.date(2026, 1, 5), dt.date(2026, 1, 12),
             dt.date(2026, 1, 19), dt.date(2026, 1, 26)],
        )

    def test_sumas_del_calendario_cuadran(self):
        calendario = construir_calendario(
            Decimal("1333.33"), Decimal("533.33"), 7, self.inicio, FrecuenciaPago.DIARIO)
        self.assertEqual(sum(f["capital_programado"] for f in calendario), Decimal("1333.33"))
        self.assertEqual(sum(f["interes_programado"] for f in calendario), Decimal("533.33"))
        self.assertEqual(sum(f["importe_programado"] for f in calendario), Decimal("1866.66"))

    def test_frecuencias(self):
        casos = {
            FrecuenciaPago.DIARIO: dt.date(2026, 1, 6),
            FrecuenciaPago.SEMANAL: dt.date(2026, 1, 12),
            FrecuenciaPago.QUINCENAL: dt.date(2026, 1, 20),
            FrecuenciaPago.MENSUAL: dt.date(2026, 2, 5),
        }
        for frecuencia, segunda_fecha in casos.items():
            with self.subTest(frecuencia=frecuencia):
                fechas = fechas_de_vencimiento(self.inicio, frecuencia, 2)
                self.assertEqual(fechas[1], segunda_fecha)

    def test_mensual_respeta_fin_de_mes(self):
        fechas = fechas_de_vencimiento(dt.date(2026, 1, 31), FrecuenciaPago.MENSUAL, 3)
        self.assertEqual(fechas[1], dt.date(2026, 2, 28))
        self.assertEqual(fechas[2], dt.date(2026, 3, 31))

    def test_personalizado_requiere_dias(self):
        with self.assertRaises(ValueError):
            fechas_de_vencimiento(self.inicio, FrecuenciaPago.PERSONALIZADO, 3)
        fechas = fechas_de_vencimiento(
            self.inicio, FrecuenciaPago.PERSONALIZADO, 3, dias_personalizados=10)
        self.assertEqual(fechas[2], dt.date(2026, 1, 25))

    def test_simulacion_completa(self):
        resultado = simular(Decimal("5000"), FIJO, Decimal("0.40"), 10,
                            self.inicio, FrecuenciaPago.SEMANAL)
        self.assertEqual(resultado["interes_total"], Decimal("2000.00"))
        self.assertEqual(resultado["total_a_pagar"], Decimal("7000.00"))
        self.assertEqual(resultado["importe_cuota"], Decimal("700.00"))
        self.assertEqual(resultado["fecha_vencimiento_final"], dt.date(2026, 3, 9))
