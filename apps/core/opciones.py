"""Catalogos compartidos entre negocios y creditos."""
from django.db import models


class FrecuenciaPago(models.TextChoices):
    DIARIO = "diario", "Diario"
    SEMANAL = "semanal", "Semanal"
    QUINCENAL = "quincenal", "Quincenal (cada 15 dias)"
    MENSUAL = "mensual", "Mensual"
    PERSONALIZADO = "personalizado", "Personalizado (cada N dias)"


#: Dias naturales entre cuotas para cada frecuencia.
#: ``mensual`` se calcula por calendario, no por dias fijos.
DIAS_POR_FRECUENCIA = {
    FrecuenciaPago.DIARIO: 1,
    FrecuenciaPago.SEMANAL: 7,
    FrecuenciaPago.QUINCENAL: 15,
}


class ModalidadInteres(models.TextChoices):
    FIJO_CAPITAL = "fijo_capital", "Interes fijo sobre el capital (tasa x capital)"
    SIMPLE_PERIODO = "simple_periodo", "Interes simple por periodo (tasa x capital x cuotas)"
    SIN_INTERES = "sin_interes", "Sin interes"


class PeriodoTasa(models.TextChoices):
    """Periodo contractual al que corresponde la tasa configurada.

    IMPORTANTE: el sistema NO asume que la tasa sea mensual o anual.
    El periodo debe quedar explicito aqui y en el contrato del credito.
    """

    CONTRATO = "contrato", "Por el plazo completo del contrato"
    DIARIO = "diario", "Por dia"
    SEMANAL = "semanal", "Por semana"
    QUINCENAL = "quincenal", "Por quincena"
    MENSUAL = "mensual", "Por mes"
