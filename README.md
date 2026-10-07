# Credit System (MXN)

Plataforma web para administrar negocios de prestamos: clientes, creditos,
calendarios de pago, abonos, cobranza, cartera vencida, indicadores y reportes.

**El codigo fuente esta en ingles; la interfaz se muestra en espanol** mediante
el sistema de traducciones de Django (`locale/es`). Cambiar a ingles es una
linea en el `.env`.

Construida con **Django 5 + PostgreSQL + Bootstrap 5 + Chart.js**, con moneda
**MXN** y zona horaria **America/Mexico_City**.

> **Antes de usarlo con clientes reales:** revisa que las condiciones
> comerciales, el contrato y las practicas de cobranza cumplan la normativa
> mexicana aplicable. El sistema calcula lo que le configures; no valida
> legalidad. Ver `docs/reglas_financieras.md`.

---

## 1. Que hace

- **Configuracion del negocio**: el sistema opera un solo negocio. En *Configuracion* se editan sus datos y reglas comerciales (tasa de interes, frecuencia, dias de gracia, mora y liquidacion anticipada). Clientes, creditos y pagos se asignan solos a ese negocio.
- **Users (usuarios y permisos)**: modelo propio con 5 roles (superadministrador, administrador, gerente, cobrador, consulta), validados en las vistas **y** en el ORM.
- **Customers (clientes)**: CRUD, referencias, historial crediticio, puntualidad de pago, datos sensibles (CURP/RFC) restringidos por rol.
- **Loans (creditos)**: folio unico, estados, interes configurable congelado por credito, calendario automatico, cancelacion y reestructuracion auditadas.
- **Payments (pagos)**: abonos parciales, aplicacion a cuotas vencidas primero, separacion capital/interes, anti-duplicados, excedentes autorizados, reversos auditados, liquidacion anticipada.
- **Collections (cobranza)**: cuotas de hoy, proximas, vencidas, creditos en mora, gestiones (llamada, visita, promesa, acuerdo), cartera por cobrador.
- **Dashboard**: 12 indicadores con definicion explicita, graficos, rankings de clientes y desempeno de cobradores.
- **Reports (reportes)**: 13 reportes filtrables, exportables a CSV y Excel (arquitectura lista para PDF).
- **Audit (auditoria)**: bitacora inmutable de toda operacion financiera.

---

## 2. Instalacion

### Requisitos

- Python 3.10 o superior (probado con 3.10 y 3.12)
- PostgreSQL 13+ (opcional en desarrollo: sin `DATABASE_URL` se usa SQLite)

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
python manage.py load_demo_data

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
python manage.py load_demo_data
python manage.py runserver
```

Abre <http://127.0.0.1:8000/>. El login esta en `/users/sign-in/`.

### Generar una SECRET_KEY

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

### Cambiar a PostgreSQL

```sql
CREATE DATABASE sistema_creditos;
CREATE USER creditos WITH PASSWORD 'una-clave-segura';
GRANT ALL PRIVILEGES ON DATABASE sistema_creditos TO creditos;
```

```ini
DATABASE_URL=postgres://creditos:una-clave-segura@localhost:5432/sistema_creditos
```

Luego `python manage.py migrate`. Si la contrasena tiene `@`, `:`, `/`, `#` o
`?`, hay que codificarla (`Cami@123` -> `Cami%40123`).

---

## 3. Idioma de la interfaz

| Quieres... | Haz esto |
|---|---|
| La app en espanol (predeterminado) | Nada: `DJANGO_LANGUAGE_CODE=es-mx` |
| La app en ingles | `DJANGO_LANGUAGE_CODE=en` en el `.env` |
| Cambiar un texto del espanol | Edita `locale/es/LC_MESSAGES/django.po` y ejecuta `python scripts/compile_messages.py` |
| Agregar textos nuevos al catalogo | `python scripts/extract_messages.py es`, traduce, y compila |

El idioma lo fija **solo** `DJANGO_LANGUAGE_CODE`: la app no sigue el idioma
del navegador (no se usa `LocaleMiddleware`), asi que un navegador en ingles
tambien ve la interfaz en espanol.

Los scripts de `scripts/` usan `polib` (`pip install polib`) y **no requieren
instalar las herramientas gettext**, que en Windows son un estorbo. Si prefieres
las de Django, `makemessages` y `compilemessages` funcionan igual.

---

## 4. Usuarios de demostracion

`python manage.py load_demo_data` usa el negocio configurado (si la base esta vacia lo crea con datos de demostracion), 20 clientes ficticios,
creditos liquidados / activos / en mora / pendientes, pagos completos y
parciales, y estos usuarios (contrasena `Demo12345`):

| Usuario | Rol | Ve |
|---|---|---|
| `demo_admin` | Administrador | Todas las operaciones y la configuracion |
| `demo_manager` | Gerente | Reportes, sin aprobar creditos |
| `demo_collector` | Cobrador | Solo su cartera |
| `demo_collector2` | Cobradora | Solo su cartera |

Todos los datos son inventados.

---

## 5. Como probar las funcionalidades

1. **Configuracion**: *Configuracion -> Editar*. Define la tasa (0.40 = 40 %, es decir 400 por cada 1,000) y la frecuencia predeterminada.
2. **Alta de cliente**: *Clientes -> Nuevo cliente*, asigna el cobrador.
3. **Nuevo credito**: desde la ficha del cliente o *Creditos -> Nuevo credito*. El sistema muestra una **pantalla de confirmacion** con interes, total, cuota y calendario antes de guardar nada.
4. **Aprobar y desembolsar**: en la ficha del credito. Al aprobar se congela la tasa; al desembolsar empieza a contar el calendario.
5. **Registrar un pago**: boton *Registrar pago*. Prueba un abono parcial y observa la cuota en estado `Parcial`.
6. **Reversar un pago**: *Pagos -> ver pago -> Reversar*. El pago queda marcado, nunca se borra, y el saldo se recalcula.
7. **Liquidacion anticipada**: *Liquidar* en la ficha del credito.
8. **Cobranza**: *Cobranza* muestra vencimientos de hoy, proximos, vencidos y creditos en mora; *Mi cartera* es la vista diaria del cobrador.
9. **Reportes**: *Reportes*, aplica filtros y exporta a Excel o CSV.
10. **Permisos**: entra como `demo_collector` y comprueba que no ve reportes, no crea creditos y solo ve su cartera.
11. **Auditoria**: *Auditoria* lista cada operacion con usuario, fecha e IP.

---

## 6. Ejecutar las pruebas

```bash
python manage.py test apps --settings=config.settings.test
```

La suite (105 pruebas) cubre: interes por cada $1,000, total a pagar, generacion
y redondeo de cuotas, frecuencias y fin de mes, abonos parciales, aplicacion a
cuotas vencidas, separacion capital/interes, liquidacion anticipada, pagos
duplicados, excedentes, reversos, deteccion de mora, modo de negocio unico,
acceso de cobradores, creditos cancelados y reestructurados, datos de
demostracion y los flujos completos de credito a liquidacion.

Las pruebas corren con `LANGUAGE_CODE="en"` para comparar contra los textos
originales del codigo, no contra la traduccion.

Con cobertura:

```bash
pip install coverage
coverage run manage.py test apps --settings=config.settings.test
coverage report
```

---

## 7. Estructura del proyecto

```text
credit-system/
├── config/
│   ├── settings/          base.py, local.py, test.py, production.py
│   ├── urls.py  wsgi.py  asgi.py
├── apps/
│   ├── core/              politica monetaria, fechas, validadores, mixins, factories
│   ├── users/             usuario personalizado + matriz de permisos
│   ├── businesses/        configuracion del negocio (unico)
│   ├── customers/         clientes, referencias, historial
│   ├── loans/             creditos, cuotas, calculos y servicios
│   ├── payments/          pagos, aplicaciones, reversos, liquidacion
│   ├── collections/       cartera, mora y gestiones
│   ├── dashboard/         indicadores y graficos
│   ├── reports/           catalogo de reportes y exportadores
│   ├── notifications/     avisos internos
│   └── audit/             bitacora de operaciones
├── templates/             base.html, components/ y una carpeta por app
├── static/                css/styles.css, js/app.js
├── locale/es/             traduccion al espanol (.po y .mo)
├── scripts/               extract_messages.py, compile_messages.py
├── docs/reglas_financieras.md
├── manage.py  pyproject.toml  .env.example
```

### Donde vive la logica financiera

| Archivo | Responsabilidad |
|---|---|
| `apps/core/money.py` | Redondeo, division en cuotas, prorrateo |
| `apps/loans/calculations.py` | Interes, total, calendario (funciones puras, sin BD) |
| `apps/loans/services.py` | Alta, aprobacion, desembolso, cancelacion, reestructuracion, recalculo |
| `apps/payments/services.py` | Registro y aplicacion de pagos, reversos, liquidacion |
| `apps/collections/services.py` | Mora, saldo vencido, clasificacion de cartera |
| `apps/dashboard/services.py` | Indicadores y rankings |

Las vistas **no calculan dinero**: siempre llaman a estos servicios.

### Glosario ingles / espanol

| Codigo | Interfaz |
|---|---|
| `Business` | Negocio (configuracion) |
| `Customer` | Cliente |
| `Loan` / `reference` / `principal` | Credito / folio / capital |
| `Installment` / `due_date` | Cuota / fecha de vencimiento |
| `Payment` / `PaymentAllocation` | Pago / aplicacion de pago |
| `CollectionAction` | Gestion de cobranza |
| `outstanding_balance` / `overdue_balance` | Saldo pendiente / saldo vencido |
| `days_past_due` | Dias de atraso |
| `write-off` | Condonacion |
| `AuditLog` | Registro de auditoria |

---

## 8. Seguridad

- CSRF activo en todos los formularios; validacion siempre en el servidor.
- Permisos por rol comprobados en las vistas y en cada consulta al ORM.
- Un administrador no puede ver ni modificar a los superadministradores.
- CURP y RFC visibles solo para roles con `view_sensitive_data`.
- Importes positivos garantizados por validadores y por `CheckConstraint` en la base.
- Folios unicos y restricciones de integridad en la base de datos.
- `transaction.atomic` + `select_for_update` en desembolsos, pagos y reversos.
- Pagos y creditos no se borran: se reversan o cancelan, con bitacora.
- Nunca se confia en calculos enviados por JavaScript: la previsualizacion del
  credito es informativa y el backend recalcula todo al guardar.

### Antes de produccion

1. `DJANGO_SETTINGS_MODULE=config.settings.production` y `DJANGO_DEBUG=False`.
2. `DJANGO_SECRET_KEY` nueva y secreta; `DJANGO_ALLOWED_HOSTS` con tu dominio.
3. HTTPS obligatorio (`DJANGO_SECURE_SSL_REDIRECT=True`).
4. `python manage.py check --deploy` sin advertencias criticas.
5. `python manage.py collectstatic`.
6. Respaldos: `pg_dump` diario con retencion (documenta y **prueba** la restauracion).
7. Revisa el cumplimiento legal y el aviso de privacidad antes de capturar datos reales.

---

## 9. Documentacion adicional

- `docs/reglas_financieras.md`: formulas, politica de redondeo, orden de
  aplicacion de pagos, definicion de mora y significado exacto de cada
  indicador.
