"""Excepciones de dominio del sistema de creditos."""


class ErrorDeNegocio(Exception):
    """Regla de negocio violada. Se muestra al usuario como mensaje de error."""


class ErrorDePago(ErrorDeNegocio):
    pass


class ErrorDeCredito(ErrorDeNegocio):
    pass
