"""Load fictitious demo data.

Every name, phone number and address is made up. Do NOT put real personal
data into this command.

    python manage.py load_demo_data
"""
import datetime as dt
import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.businesses.models import Business
from apps.collections.models import ActionOutcome, ActionType, CollectionAction
from apps.core.dates import today_local
from apps.customers.models import Customer, CustomerStatus, PersonalReference
from apps.loans import services as loan_services
from apps.payments import services as payment_services
from apps.payments.models import PaymentMethod
from apps.users.models import Role, User

NAMES = [
    ("Ana Sofia", "Perez", "Lopez"), ("Luis Fernando", "Ramirez", "Cruz"),
    ("Maria Jose", "Hernandez", "Gomez"), ("Jorge Alberto", "Martinez", "Diaz"),
    ("Claudia", "Sanchez", "Reyes"), ("Miguel Angel", "Torres", "Nunez"),
    ("Patricia", "Flores", "Mendoza"), ("Ricardo", "Castillo", "Vargas"),
    ("Gabriela", "Morales", "Rios"), ("Hector", "Jimenez", "Salas"),
    ("Veronica", "Guzman", "Pina"), ("Alejandro", "Rojas", "Campos"),
    ("Diana Laura", "Ortiz", "Serrano"), ("Fernando", "Medina", "Aguilar"),
    ("Karla", "Vega", "Delgado"), ("Oscar", "Navarro", "Pacheco"),
    ("Lucia", "Cabrera", "Fuentes"), ("Raul", "Espinoza", "Montes"),
    ("Monica", "Silva", "Herrera"), ("Javier", "Duran", "Peralta"),
]
# Values stored in the database and shown in the UI, so they are in Spanish.
OCCUPATIONS = ["Comerciante", "Taxista", "Estilista", "Vendedor ambulante",
               "Costurera", "Carpintero", "Trabajadora del hogar", "Abarrotero",
               "Mecánico", "Panadero"]
CITIES = [("Guadalajara", "JAL"), ("Monterrey", "NL"), ("Puebla", "PUE"),
          ("Leon", "GTO"), ("Merida", "YUC")]


class Command(BaseCommand):
    help = "Load fictitious users, customers, loans and payments."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password", default="Demo12345",
            help="Password for the demo users.")
        parser.add_argument(
            "--seed", type=int, default=2026,
            help="Random seed (for reproducible results).")

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(options["seed"])
        password = options["password"]
        today = today_local()

        if User.objects.filter(username="demo_admin").exists():
            self.stdout.write(self.style.WARNING(
                "Demo data already exists. More records will be added."))

        # Single-business mode: the demo data goes into the one business. Its
        # commercial rules are only set when the database had no business yet,
        # so an existing configuration is never overwritten.
        fresh_install = not Business.objects.exists()
        business = Business.objects.current()
        if fresh_install:
            business.trade_name = "[DEMO] Creditos del Centro"
            business.legal_name = "Creditos del Centro SA de CV"
            business.tax_id = "CDC010101AB1"
            business.phone = "3312345678"
            business.email = "contacto@demo-creditos.mx"
            business.address = "Av. Ficticia 100"
            business.city = "Guadalajara"
            business.state = "JAL"
            business.interest_rate = Decimal("0.4000")
            business.installment_count = 4
            business.payment_frequency = "weekly"
            business.grace_days = 1
            business.notes = "Negocio de demostración. Datos ficticios."
            business.save()

        admin = self._user("demo_admin", Role.ADMIN, "Alma", "Administradora", password)
        manager = self._user("demo_manager", Role.MANAGER, "Gustavo", "Gerente", password)
        collector_one = self._user("demo_collector", Role.COLLECTOR, "Carlos",
                                   "Cobrador", password)
        collector_two = self._user("demo_collector2", Role.COLLECTOR, "Cecilia",
                                   "Cobradora", password)
        if fresh_install:
            business.manager = admin
            business.save(update_fields=["manager"])

        customers = []
        for index, (first_name, last_name, second_last_name) in enumerate(NAMES):
            collector = collector_one if index < 13 else collector_two
            city, state = random.choice(CITIES)
            customer = Customer.objects.create(
                business=business, first_name=first_name, last_name=last_name,
                second_last_name=second_last_name,
                phone=f"55{random.randint(10000000, 99999999)}",
                occupation=random.choice(OCCUPATIONS),
                address=f"Calle Ficticia {random.randint(1, 500)}",
                city=city, state=state,
                postal_code=f"{random.randint(10000, 99999)}",
                collector=collector,
                status=CustomerStatus.RESTRICTED if index == 19 else CustomerStatus.ACTIVE,
                notes="Cliente de demostración (datos ficticios).",
                created_by=admin,
            )
            PersonalReference.objects.create(
                customer=customer, name="Referencia de demostración",
                relationship=random.choice(["Hermano", "Vecino", "Amigo", "Primo"]),
                phone=f"55{random.randint(10000000, 99999999)}")
            customers.append(customer)

        created = {"settled": 0, "live": 0, "past_due": 0, "pending": 0}

        # --- Settled loans ---------------------------------------------------
        for customer in customers[:4]:
            loan = self._loan(customer, admin, Decimal(random.choice([1000, 2000, 3000])),
                              today - dt.timedelta(days=60))
            for _ in range(loan.installment_count):
                loan.refresh_from_db()
                if loan.outstanding_balance <= 0:
                    break
                next_installment = loan.installments.exclude(status="paid").first()
                payment_services.register_payment(
                    loan=loan, amount=next_installment.balance,
                    user=customer.collector, collector=customer.collector,
                    method=PaymentMethod.CASH, force_duplicate=True,
                    paid_at=timezone.now() - dt.timedelta(days=random.randint(1, 50)))
            created["settled"] += 1

        # --- Live loans, up to date ------------------------------------------
        for customer in customers[4:11]:
            loan = self._loan(customer, admin, Decimal(random.choice([1500, 2500, 4000])),
                              today - dt.timedelta(days=random.randint(0, 10)))
            if random.random() > 0.3:
                installment = loan.installments.first()
                payment_services.register_payment(
                    loan=loan, amount=installment.scheduled_amount,
                    user=customer.collector, collector=customer.collector,
                    force_duplicate=True)
            created["live"] += 1

        # --- Past-due loans with partial payments -----------------------------
        for customer in customers[11:17]:
            loan = self._loan(customer, admin, Decimal(random.choice([2000, 5000, 8000])),
                              today - dt.timedelta(days=random.randint(25, 70)))
            if random.random() > 0.4:
                payment_services.register_payment(
                    loan=loan, amount=Decimal(random.choice([200, 350, 500])),
                    user=customer.collector, collector=customer.collector,
                    force_duplicate=True,
                    paid_at=timezone.now() - dt.timedelta(days=random.randint(1, 20)))
            loan_services.refresh_status(loan)
            CollectionAction.objects.create(
                loan=loan, customer=customer, business=customer.business,
                user=customer.collector,
                performed_at=timezone.now() - dt.timedelta(days=2),
                action_type=random.choice([ActionType.CALL, ActionType.VISIT,
                                           ActionType.PROMISE]),
                outcome=random.choice([ActionOutcome.PROMISED,
                                       ActionOutcome.NO_ANSWER,
                                       ActionOutcome.RESCHEDULED]),
                promised_amount=Decimal(random.choice([0, 350, 700])),
                promise_date=today + dt.timedelta(days=3),
                next_contact_date=today + dt.timedelta(days=1),
                notes="Acción de cobranza de demostración.")
            created["past_due"] += 1

        # --- Loans pending approval -------------------------------------------
        for customer in customers[17:19]:
            loan_services.create_loan(
                customer=customer, business=customer.business,
                principal=Decimal("3000"),
                installment_count=customer.business.installment_count,
                frequency=customer.business.payment_frequency,
                first_payment_date=today + dt.timedelta(days=7), user=manager,
                collector=customer.collector,
                notes="Solicitud de demostración pendiente de aprobación.")
            created["pending"] += 1

        self.stdout.write(self.style.SUCCESS("Demo data loaded:"))
        self.stdout.write(f"  Business: {business}   Customers: {len(customers)}")
        self.stdout.write(
            f"  Settled loans: {created['settled']}, live: {created['live']}, "
            f"past due: {created['past_due']}, pending: {created['pending']}")
        self.stdout.write(f"  Users (password: {password}):")
        for user in [admin, manager, collector_one, collector_two]:
            self.stdout.write(f"    {user.username} -> {user.get_role_display()}")
        self.stdout.write(self.style.WARNING(
            "All data is fictitious. Never use real personal information."))

    def _user(self, username, role, first_name, last_name, password):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"role": role, "first_name": first_name, "last_name": last_name,
                      "email": f"{username}@demo.mx"},
        )
        if created:
            user.set_password(password)
            user.save()
        return user

    def _loan(self, customer, user, principal, first_payment_date):
        business = customer.business
        loan = loan_services.create_loan(
            customer=customer, business=business, principal=principal,
            installment_count=business.installment_count,
            frequency=business.payment_frequency,
            first_payment_date=first_payment_date, user=user,
            collector=customer.collector,
            application_date=first_payment_date - dt.timedelta(days=1),
            notes="Crédito de demostración.")
        loan_services.approve_loan(loan, user,
                                   date=first_payment_date - dt.timedelta(days=1))
        loan.refresh_from_db()
        loan_services.disburse_loan(loan, user,
                                    date=first_payment_date - dt.timedelta(days=1))
        loan.refresh_from_db()
        return loan
