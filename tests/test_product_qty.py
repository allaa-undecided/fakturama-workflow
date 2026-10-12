"""Quantity-cell selection. The item number sits immediately right of the decimal."""

from fakturama_auto.steps.product import _opened_is_quantity, _pick_quantity_token


def _token(text: str, x: float) -> dict:
    return {"text": text, "x": x, "right": x + 28, "y": 500, "bottom": 516}


def test_quantity_is_the_decimal_left_of_the_item_number():
    tokens = [
        _token("1", 20),
        _token("1.00", 156),
        _token("CHR-ERG-01", 220),
        _token("01", 280),
        _token("$250.00", 990),
        _token("-10.00", 1140),
        _token("$225.00", 1280),
    ]
    chosen = _pick_quantity_token(tokens, header_x=87, item_left=218)
    assert chosen is not None
    assert chosen["text"] == "1.00"


def test_price_decimal_is_not_the_quantity():
    tokens = [
        _token("250.00", 990),
        _token("225.00", 1280),
    ]
    assert _pick_quantity_token(tokens, header_x=87, item_left=218) is None


def test_opened_quantity_is_a_decimal():
    assert _opened_is_quantity("1.00")
    assert _opened_is_quantity("1,00")
    assert not _opened_is_quantity("1")
    assert not _opened_is_quantity("CHR-ERG-01")
    assert not _opened_is_quantity("$250.00")
