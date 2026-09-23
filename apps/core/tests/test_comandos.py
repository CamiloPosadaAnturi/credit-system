"""Pruebas de los comandos de gestion."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.clientes.models import Cliente
from apps.creditos.models import Credito, EstadoCredito
from apps.negocios.models import Negocio
from apps.pagos.models import Pago
from apps.usuarios.models import Usuario


class CargarDatosDemoTests(TestCase):
    def test_carga_un_conjunto_coherente(self):
        salida = StringIO()
        call_command("cargar_datos_demo", stdout=salida)

        self.assertEqual(Negocio.objects.count(), 2)
        self.assertEqual(Cliente.objects.count(), 20)
        self.assertEqual(Usuario.objects.count(), 4)
        self.assertGreater(Credito.objects.count(), 15)
        self.assertGreater(Pago.objects.count(), 5)

        self.assertTrue(Credito.objects.filter(estado=EstadoCredito.LIQUIDADO).exists())
        self.assertTrue(Credito.objects.filter(estado=EstadoCredito.EN_MORA).exists())
        self.assertTrue(Credito.objects.filter(estado=EstadoCredito.PENDIENTE).exists())
        self.assertIn("Datos de demostracion cargados", salida.getvalue())

    def test_los_saldos_cuadran_con_las_aplicaciones(self):
        """Cada credito debe poder reconstruirse desde sus aplicaciones de pago."""
        from apps.pagos.models import AplicacionPago, EstadoPago

        call_command("cargar_datos_demo", stdout=StringIO())
        for credito in Credito.objects.desembolsados():
            aplicado = sum(
                aplicacion.importe
                for aplicacion in AplicacionPago.objects.filter(
                    cuota__credito=credito, pago__estado=EstadoPago.CONFIRMADO)
            )
            self.assertEqual(
                credito.saldo_pendiente, max(credito.total_a_pagar - aplicado, 0),
                f"El saldo de {credito.folio} no cuadra con sus aplicaciones de pago.")
            self.assertEqual(
                sum(cuota.importe_programado for cuota in credito.cuotas.all()),
                credito.total_a_pagar)
