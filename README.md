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
