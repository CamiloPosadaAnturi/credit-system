"""Object builders used by the tests and the demo data command."""
import datetime as dt
from decimal import Decimal

from apps.businesses.models import Business
from apps.core.dates import today_local
from apps.customers.models import Customer
from apps.loans import services as loan_services
from apps.users.models import Role, User


def create_business(name="Demo Lending", **extra) -> Business:
    data = {
        "trade_name": name,
        "interest_rate": Decimal("0.4000"),
        "installment_count": 4,
        "payment_frequency": "weekly",
        "is_active": True,
    }
    data.update(extra)
    return Business.objects.create(**data)


def create_user(username, role=Role.ADMIN, businesses=(), password="Testing12345",
                **extra) -> User:
    user = User.objects.create_user(
        username=username, password=password, role=role,
        first_name=extra.pop("first_name", username.capitalize()),
        last_name=extra.pop("last_name", "Demo"),
        **extra,
    )
    if businesses:
        user.businesses.set(businesses)
    return user


def create_customer(business, first_name="Ana", last_name="Ramirez", **extra) -> Customer:
    data = {
        "business": business,
        "first_name": first_name,
        "last_name": last_name,
        "phone": "5555555555",
    }
    data.update(extra)
    return Customer.objects.create(**data)


def create_loan(customer, user=None, principal=Decimal("1000"), installments=4,
                frequency="weekly", first_payment_date: dt.date | None = None,
                disburse=True, **extra):
    loan = loan_services.create_loan(
        customer=customer,
        business=customer.business,
        principal=principal,
        installment_count=installments,
        frequency=frequency,
        first_payment_date=first_payment_date or today_local(),
        user=user,
        **extra,
    )
    if disburse and user is not None:
        loan_services.approve_loan(loan, user)
        loan.refresh_from_db()
        loan_services.disburse_loan(loan, user)
        loan.refresh_from_db()
    return loan
