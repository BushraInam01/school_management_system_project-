from decimal import Decimal


CENT = Decimal("0.01")


def money(value):
    """Format a monetary value consistently to two decimal places."""
    if value is None:
        value = Decimal("0")
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return f"{value.quantize(CENT):.2f}"
