# Sistema de Creditos (MXN)

Plataforma web para administrar negocios de prestamos: clientes, creditos,
calendarios de pago, abonos, cobranza, cartera vencida, indicadores y reportes.

Construida con **Django 5 + PostgreSQL + Bootstrap 5 + Chart.js**, en espanol,
con moneda **MXN** y zona horaria **America/Mexico_City**.

> **Antes de usarlo con clientes reales:** revisa que las condiciones
> comerciales, el contrato y las practicas de cobranza cumplan la normativa
> mexicana aplicable. El sistema calcula lo que le configures; no valida
> legalidad. Ver `docs/reglas_financieras.md`.

---

## 1. Que hace

- **Negocios / sucursales**: CRUD, configuracion de intereses y mora, dashboard propio, aislamiento total de la informacion entre negocios.
- **Usuarios y permisos**: modelo propio con 5 roles (superadministrador, administrador, gerente, cobrador, consulta), validados en las vistas **y** en el ORM.
- **Clientes**: CRUD, referencias, historial crediticio, puntualidad de pago, datos sensibles (CURP/RFC) restringidos por rol.
- **Creditos**: folio unico, estados, interes configurable congelado por credito, calendario automatico, cancelacion y reestructuracion auditadas.
- **Pagos**: abonos parciales, aplicacion a cuotas vencidas primero, separacion capital/interes, anti-duplicados, excedentes autorizados, reversos auditados, liquidacion anticipada.
- **Cobranza**: cuotas de hoy, proximas, vencidas, creditos en mora, gestiones (llamada, visita, promesa, acuerdo), cartera por cobrador.
- **Dashboard**: 12 indicadores con definicion explicita, graficos, rankings de clientes y desempeno de cobradores.
- **Reportes**: 13 reportes filtrables, exportables a CSV y Excel (arquitectura lista para PDF).
- **Auditoria**: bitacora inmutable de toda operacion financiera.

---

## 2. Instalacion

### Requisitos

- Python 3.10 o superior (probado con 3.10 y 3.12)
- PostgreSQL 13+ (opcional en desarrollo: sin `DATABASE_URL` se usa SQLite)
- Git

### Pasos (Windows)

```bat
cd C:\Users\<tu-usuario>\Desktop\credit-system

:: 1. Entorno virtual
python -m venv venv
venv\Scripts\activate

:: 2. Dependencias (con uv, recomendado)
pip install uv
uv pip install -r pyproject.toml

::    ...o con pip a secas:
:: pip install "django>=5.1,<5.2" django-environ "psycopg[binary]" openpyxl whitenoise

:: 3. Variables de entorno
copy .env.example .env
::    edita .env y cambia DJANGO_SECRET_KEY

:: 4. Base de datos
python manage.py migrate

:: 5. Usuario administrador
python manage.py createsuperuser

:: 6. Datos de demostracion (opcional)
python manage.py cargar_datos_demo

:: 7. Arrancar
python manage.py runserver
```

### Pasos (Linux / macOS)

```bash
python3 -m venv venv && source venv/bin/activate
pip install uv && uv pip install -r pyproject.toml
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py cargar_datos_demo
python manage.py runserver
```

Abre <http://127.0.0.1:8000/>. El login esta en `/usuarios/entrar/`.

### Generar una SECRET_KEY

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

### Cambiar a PostgreSQL

Crea la base y ajusta `.env`:

```sql
CREATE DATABASE sistema_creditos;
CREATE USER creditos WITH PASSWORD 'una-clave-segura';
GRANT ALL PRIVILEGES ON DATABASE sistema_creditos TO creditos;
```

```ini
DATABASE_URL=postgres://creditos:una-clave-segura@localhost:5432/sistema_creditos
```

Luego `python manage.py migrate`.

---

## 3. Usuarios de demostracion

`python manage.py cargar_datos_demo` crea 2 negocios, 20 clientes ficticios,
creditos liquidados / activos / en mora / pendientes, pagos completos y
parciales, y estos usuarios (contrasena `Demo12345`):

| Usuario | Rol | Ve |
|---|---|---|
| `demo_admin` | Administrador | Los dos negocios, todas las operaciones |
| `demo_gerente` | Gerente | Negocio 1, reportes, sin aprobar creditos |
| `demo_cobrador` | Cobrador | Solo su cartera del negocio 1 |
| `demo_cobrador2` | Cobradora | Solo su cartera del negocio 2 |

Todos los datos son inventados.

---

## 4. Como probar las funcionalidades

1. **Alta de negocio**: *Negocios -> Nuevo negocio*. Define la tasa (0.40 = 40 %, es decir 400 por cada 1,000) y la frecuencia predeterminada.
2. **Alta de cliente**: *Clientes -> Nuevo cliente*, asigna negocio y cobrador.
3. **Nuevo credito**: desde la ficha del cliente o *Creditos -> Nuevo credito*. Captura capital, cuotas y frecuencia: el sistema muestra una **pantalla de confirmacion** con interes, total, cuota y calendario antes de guardar nada.
4. **Aprobar y desembolsar**: en la ficha del credito. Al aprobar se congela la tasa; al desembolsar el credito pasa a `activo` y empieza a contar el calendario.
5. **Registrar un pago**: boton *Registrar pago*. Prueba un abono parcial (por ejemplo 100) y observa la cuota en estado `parcial`, y luego el resto.
6. **Reversar un pago**: *Pagos -> ver pago -> Reversar*. El pago queda marcado, nunca se borra, y el saldo se recalcula.
7. **Liquidacion anticipada**: *Liquidar* en la ficha del credito.
8. **Cobranza**: *Cobranza* muestra vencimientos de hoy, proximos, vencidos y creditos en mora; *Mi cartera* es la vista diaria del cobrador.
9. **Reportes**: *Reportes*, aplica filtros y exporta a Excel o CSV.
10. **Permisos**: entra como `demo_cobrador` y comprueba que no ve reportes, no crea creditos y solo ve su cartera.
11. **Auditoria**: *Auditoria* lista cada operacion con usuario, fecha e IP.

---

## 5. Ejecutar las pruebas

```bash
python manage.py test apps --settings=config.settings.test
```

La suite (99 pruebas) cubre: interes por cada $1,000, total a pagar, generacion
y redondeo de cuotas, frecuencias y fin de mes, abonos parciales, aplicacion a
cuotas vencidas, separacion capital/interes, liquidacion anticipada, pagos
duplicados, excedentes, reversos, deteccion de mora, permisos entre negocios,
acceso de cobradores, creditos cancelados y reestructurados, datos de
demostracion y los flujos completos de credito a liquidacion.

Con cobertura:

```bash
pip install coverage
coverage run manage.py test apps --settings=config.settings.test
coverage report
```

---

## 6. Estructura del proyecto

```text
credit-system/
├── config/
│   ├── settings/          base.py, local.py, test.py, production.py
│   ├── urls.py  wsgi.py  asgi.py
├── apps/
│   ├── core/              politica monetaria, fechas, validadores, mixins, factorias
│   ├── usuarios/          usuario personalizado + matriz de permisos
│   ├── negocios/          negocios/sucursales y su configuracion
│   ├── clientes/          clientes, referencias, historial
│   ├── creditos/          creditos, cuotas, calculos y servicios
│   ├── pagos/             pagos, aplicaciones, reversos, liquidacion
│   ├── cobranza/          cartera, mora y gestiones
│   ├── dashboard/         indicadores y graficos
│   ├── reportes/          catalogo de reportes y exportadores
│   ├── notificaciones/    avisos internos
│   └── auditoria/         bitacora de operaciones
├── templates/             base.html, components/ y una carpeta por app
├── static/                css/estilos.css, js/app.js
├── docs/reglas_financieras.md
├── manage.py  pyproject.toml  .env.example
```

### Donde vive la logica financiera

| Archivo | Responsabilidad |
|---|---|
| `apps/core/dinero.py` | Redondeo, division en cuotas, prorrateo |
| `apps/creditos/calculos.py` | Interes, total, calendario (funciones puras, sin BD) |
| `apps/creditos/servicios.py` | Alta, aprobacion, desembolso, cancelacion, reestructuracion, recalculo |
| `apps/pagos/servicios.py` | Registro y aplicacion de pagos, reversos, liquidacion |
| `apps/cobranza/servicios.py` | Mora, saldo vencido, clasificacion de cartera |
| `apps/dashboard/servicios.py` | Indicadores y rankings |

Las vistas **no calculan dinero**: siempre llaman a estos servicios.

---

## 7. Seguridad

- CSRF activo en todos los formularios; validacion siempre en el servidor.
- Permisos por rol comprobados en las vistas y en cada consulta al ORM.
- Aislamiento por negocio: un usuario solo consulta lo de sus negocios autorizados.
- CURP y RFC visibles solo para roles con `ver_datos_sensibles`.
- Importes positivos garantizados por validadores y por `CheckConstraint` en la base.
- Folios unicos y restricciones de integridad en la base de datos.
- `transaction.atomic` + `select_for_update` en desembolsos, pagos y reversos.
- Pagos y creditos no se borran: se reversan o cancelan, con bitacora.
- Nunca se confia en calculos enviados por JavaScript: la previsualizacion del
  credito es informativa y el backend recalcula todo al guardar.

### Antes de producción

1. `DJANGO_SETTINGS_MODULE=config.settings.production` y `DJANGO_DEBUG=False`.
2. `DJANGO_SECRET_KEY` nueva y secreta; `DJANGO_ALLOWED_HOSTS` con tu dominio.
3. HTTPS obligatorio (`DJANGO_SECURE_SSL_REDIRECT=True`).
4. `python manage.py check --deploy` sin advertencias criticas.
5. `python manage.py collectstatic`.
6. Respaldos: `pg_dump` diario con retencion (documenta y **prueba** la restauracion).
7. Revisa el cumplimiento legal y el aviso de privacidad antes de capturar datos reales.

---

## 8. Documentacion adicional

- `docs/reglas_financieras.md`: formulas, politica de redondeo, orden de
  aplicacion de pagos, definicion de mora y significado exacto de cada
  indicador.
