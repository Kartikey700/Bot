from config import FEE_SLABS, CURRENCY


def calc_fee(amount: float):
    """Return (fee, total) for a given amount."""
    for lo, hi, (kind, val) in FEE_SLABS:
        if lo <= amount <= hi:
            if kind == "fixed":
                fee = val
            else:
                fee = round(amount * val / 100, 2)
            return fee, round(amount + fee, 2)
    return 0, amount


def fmt(amount: float) -> str:
    return f"{CURRENCY}{amount:,.2f}".rstrip("0").rstrip(".")


def is_valid_amount(text: str):
    try:
        v = float(text)
        return v > 0, v
    except (TypeError, ValueError):
        return False, 0


async def escrow_only(update, deal, user_id):
    """Returns True if user is the original escrower of the deal."""
    return deal and deal["escrower_id"] == user_id
