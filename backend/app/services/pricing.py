from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def calculate_patient_price(original_price: Decimal, discount_percentage: Decimal) -> Decimal:
    """Calculate a unit price in INR using conventional half-up paise rounding."""
    return (original_price * (Decimal("1") - discount_percentage / Decimal("100"))).quantize(CENT, rounding=ROUND_HALF_UP)
