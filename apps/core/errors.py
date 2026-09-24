"""Domain exceptions of the credit system."""


class BusinessRuleError(Exception):
    """A business rule was violated. Shown to the user as an error message."""


class PaymentError(BusinessRuleError):
    pass


class LoanError(BusinessRuleError):
    pass
