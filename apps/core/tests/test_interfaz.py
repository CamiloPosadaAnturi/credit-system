"""Pruebas de la interfaz: plantillas, paginacion y pantallas publicas."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.core.factorias import crear_cliente, crear_negocio, crear_usuario
from apps.usuarios.models import Rol


class PaginacionTests(TestCase):
    """Regresion: la paginacion fallaba en la primera pagina de un listado largo."""

    def setUp(self):
        self.negocio = crear_negocio()
        self.admin = crear_usuario("admin", Rol.ADMIN, [self.negocio])
        for indice in range(60):
            crear_cliente(self.negocio, f"Cliente{indice}", "Apellido")
        self.client.force_login(self.admin)

    def test_primera_pagina(self):
        respuesta = self.client.get(reverse("clientes:lista"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Pagina 1 de 3")
        self.assertContains(respuesta, "page=2")

    def test_ultima_pagina(self):
        respuesta = self.client.get(reverse("clientes:lista"), {"page": 3})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Pagina 3 de 3")

    def test_paginacion_conserva_los_filtros(self):
        respuesta = self.client.get(reverse("clientes:lista"), {"q": "Cliente", "page": 2})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "q=Cliente")


class PantallasPublicasTests(TestCase):
    def test_login_se_muestra(self):
        respuesta = self.client.get(reverse("usuarios:login"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Sistema de Creditos")

    def test_pagina_inexistente(self):
        self.assertEqual(self.client.get("/ruta-que-no-existe/").status_code, 404)


class DatosSensiblesTests(TestCase):
    def setUp(self):
        self.negocio = crear_negocio()
        self.admin = crear_usuario("admin", Rol.ADMIN, [self.negocio])
        self.gerente = crear_usuario("gerente", Rol.GERENTE, [self.negocio])
        self.cliente = crear_cliente(self.negocio, curp="RAMA850101HDFMNN09",
                                     rfc="RAMA850101AB1")

    def test_el_admin_ve_curp_y_rfc(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("clientes:detalle", args=[self.cliente.pk]))
        self.assertContains(respuesta, "RAMA850101HDFMNN09")

    def test_el_gerente_no_ve_curp(self):
        self.client.force_login(self.gerente)
        respuesta = self.client.get(reverse("clientes:detalle", args=[self.cliente.pk]))
        self.assertNotContains(respuesta, "RAMA850101HDFMNN09")
        self.assertContains(respuesta, "datos sensibles")


class SimuladorTests(TestCase):
    def setUp(self):
        self.negocio = crear_negocio()
        self.admin = crear_usuario("admin", Rol.ADMIN, [self.negocio])
        self.client.force_login(self.admin)

    def test_la_simulacion_devuelve_los_mismos_numeros_que_el_backend(self):
        respuesta = self.client.post(
            reverse("creditos:simular"),
            data='{"capital": "10000", "tasa_interes": "0.40", "numero_cuotas": 10,'
                 ' "modalidad_interes": "fijo_capital", "frecuencia_pago": "semanal"}',
            content_type="application/json")
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertEqual(Decimal(datos["interes_total"]), Decimal("4000.00"))
        self.assertEqual(Decimal(datos["total_a_pagar"]), Decimal("14000.00"))
        self.assertEqual(Decimal(datos["importe_cuota"]), Decimal("1400.00"))

    def test_datos_invalidos_devuelven_400(self):
        respuesta = self.client.post(
            reverse("creditos:simular"), data='{"capital": "0"}',
            content_type="application/json")
        self.assertEqual(respuesta.status_code, 400)
