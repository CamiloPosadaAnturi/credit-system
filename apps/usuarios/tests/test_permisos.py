"""Pruebas de la matriz de permisos y del aislamiento entre negocios."""
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from apps.clientes.models import Cliente
from apps.core.factorias import crear_cliente, crear_credito, crear_negocio, crear_usuario
from apps.creditos.models import Credito
from apps.usuarios import permisos
from apps.usuarios.models import Rol


class MatrizDePermisosTests(TestCase):
    def setUp(self):
        self.negocio = crear_negocio()
        self.roles = {
            rol: crear_usuario(f"u_{rol}", rol, [self.negocio])
            for rol in [Rol.SUPERADMIN, Rol.ADMIN, Rol.GERENTE, Rol.COBRADOR, Rol.CONSULTA]
        }

    def test_solo_admin_y_superadmin_aprueban_creditos(self):
        self.assertTrue(permisos.puede(self.roles[Rol.SUPERADMIN], permisos.APROBAR_CREDITO))
        self.assertTrue(permisos.puede(self.roles[Rol.ADMIN], permisos.APROBAR_CREDITO))
        for rol in [Rol.GERENTE, Rol.COBRADOR, Rol.CONSULTA]:
            self.assertFalse(permisos.puede(self.roles[rol], permisos.APROBAR_CREDITO))

    def test_cobrador_registra_pagos_pero_no_los_reversa(self):
        cobrador = self.roles[Rol.COBRADOR]
        self.assertTrue(permisos.puede(cobrador, permisos.REGISTRAR_PAGO))
        self.assertFalse(permisos.puede(cobrador, permisos.REVERSAR_PAGO))

    def test_consulta_solo_lee(self):
        consulta = self.roles[Rol.CONSULTA]
        self.assertTrue(permisos.puede(consulta, permisos.VER_CREDITOS))
        for accion in [permisos.REGISTRAR_PAGO, permisos.CREAR_CREDITO,
                       permisos.GESTIONAR_CLIENTES, permisos.GESTIONAR_USUARIOS]:
            self.assertFalse(permisos.puede(consulta, accion))

    def test_datos_sensibles_restringidos(self):
        self.assertTrue(permisos.puede(self.roles[Rol.ADMIN], permisos.VER_DATOS_SENSIBLES))
        self.assertFalse(permisos.puede(self.roles[Rol.GERENTE], permisos.VER_DATOS_SENSIBLES))
        self.assertFalse(permisos.puede(self.roles[Rol.COBRADOR], permisos.VER_DATOS_SENSIBLES))

    def test_usuario_inactivo_no_puede_nada(self):
        usuario = self.roles[Rol.ADMIN]
        usuario.is_active = False
        self.assertFalse(permisos.puede(usuario, permisos.VER_DASHBOARD))

    def test_exigir_lanza_permission_denied(self):
        with self.assertRaises(PermissionDenied):
            permisos.exigir(self.roles[Rol.CONSULTA], permisos.CREAR_CREDITO)

    def test_accion_desconocida(self):
        with self.assertRaises(ValueError):
            permisos.puede(self.roles[Rol.ADMIN], "accion_inventada")


class AislamientoEntreNegociosTests(TestCase):
    def setUp(self):
        self.negocio_a = crear_negocio("Negocio A")
        self.negocio_b = crear_negocio("Negocio B")
        self.admin_a = crear_usuario("admin_a", Rol.ADMIN, [self.negocio_a])
        self.admin_b = crear_usuario("admin_b", Rol.ADMIN, [self.negocio_b])
        self.super = crear_usuario("jefe", Rol.SUPERADMIN)
        self.cliente_a = crear_cliente(self.negocio_a, "Ana")
        self.cliente_b = crear_cliente(self.negocio_b, "Beto")
        self.credito_a = crear_credito(self.cliente_a, self.admin_a, Decimal("1000"))
        self.credito_b = crear_credito(self.cliente_b, self.admin_b, Decimal("2000"))

    def test_el_orm_filtra_por_negocio(self):
        vistos = permisos.filtrar_por_negocio(Cliente.objects.all(), self.admin_a)
        self.assertEqual(list(vistos), [self.cliente_a])

        creditos = permisos.filtrar_por_negocio(Credito.objects.all(), self.admin_b)
        self.assertEqual(list(creditos), [self.credito_b])

    def test_el_superadmin_ve_todo(self):
        self.assertEqual(
            permisos.filtrar_por_negocio(Cliente.objects.all(), self.super).count(), 2)

    def test_exigir_negocio(self):
        permisos.exigir_negocio(self.admin_a, self.negocio_a)
        with self.assertRaises(PermissionDenied):
            permisos.exigir_negocio(self.admin_a, self.negocio_b)

    def test_vista_de_detalle_devuelve_404_para_otro_negocio(self):
        self.client.force_login(self.admin_a)
        propia = self.client.get(reverse("creditos:detalle", args=[self.credito_a.pk]))
        self.assertEqual(propia.status_code, 200)
        ajena = self.client.get(reverse("creditos:detalle", args=[self.credito_b.pk]))
        self.assertEqual(ajena.status_code, 404)

    def test_lista_de_clientes_solo_muestra_los_propios(self):
        self.client.force_login(self.admin_a)
        respuesta = self.client.get(reverse("clientes:lista"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ana")
        self.assertNotContains(respuesta, "Beto")


class CarteraDelCobradorTests(TestCase):
    def setUp(self):
        self.negocio = crear_negocio()
        self.admin = crear_usuario("admin", Rol.ADMIN, [self.negocio])
        self.cobrador1 = crear_usuario("cobra1", Rol.COBRADOR, [self.negocio])
        self.cobrador2 = crear_usuario("cobra2", Rol.COBRADOR, [self.negocio])
        self.cliente1 = crear_cliente(self.negocio, "Ana", cobrador=self.cobrador1)
        self.cliente2 = crear_cliente(self.negocio, "Beto", cobrador=self.cobrador2)
        self.credito1 = crear_credito(self.cliente1, self.admin)
        self.credito2 = crear_credito(self.cliente2, self.admin)

    def test_el_cobrador_solo_ve_su_cartera(self):
        vistos = permisos.filtrar_cartera_cobrador(Credito.objects.all(), self.cobrador1)
        self.assertEqual(list(vistos), [self.credito1])

    def test_el_admin_ve_toda_la_cartera(self):
        vistos = permisos.filtrar_cartera_cobrador(Credito.objects.all(), self.admin)
        self.assertEqual(vistos.count(), 2)

    def test_el_cobrador_no_abre_un_credito_ajeno(self):
        self.client.force_login(self.cobrador1)
        self.assertEqual(
            self.client.get(reverse("creditos:detalle", args=[self.credito1.pk])).status_code,
            200)
        self.assertEqual(
            self.client.get(reverse("creditos:detalle", args=[self.credito2.pk])).status_code,
            404)

    def test_el_cobrador_no_entra_a_reportes(self):
        self.client.force_login(self.cobrador1)
        self.assertEqual(self.client.get(reverse("reportes:catalogo")).status_code, 403)

    def test_el_cobrador_no_crea_creditos(self):
        self.client.force_login(self.cobrador1)
        self.assertEqual(self.client.get(reverse("creditos:crear")).status_code, 403)

    def test_login_requerido(self):
        respuesta = self.client.get(reverse("creditos:lista"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/usuarios/entrar/", respuesta["Location"])
