"""OCR extraction of the supplied sales-order image."""

from pathlib import Path

from fakturama_auto.extract import extract_order

IMAGE = Path(__file__).resolve().parents[1] / "samples" / "order_northstar.png"


def test_sample_image_extracts_and_validates():
    order = extract_order(IMAGE)
    assert order.external_reference == "WEB-2026-0714-A17"
    assert order.order_date == "2026-07-14"
    assert order.source_customer_id == "CUST-1007"
    assert order.currency == "EUR"
    assert order.company == "Northstar Office GmbH"
    assert order.first_name == "Marta"
    assert order.last_name == "Klein"
    assert order.alias == "NORTHSTAR-BERLIN"
    assert order.email == "marta.klein@example.test"
    assert "5550" in order.telephone
    assert order.billing.street.startswith("Friedrich")
    assert order.billing.zip_code == "10117"
    assert order.billing.city == "Berlin"
    assert order.billing.country == "Germany"
    assert order.delivery.company.startswith("Northstar Office Warehouse")
    assert order.delivery.street.startswith("Beussel")
    assert order.delivery.zip_code == "10553"
    assert order.payment_method == "Bank Transfer"
    assert order.paid_status == "PAID"
    assert order.payment_date == "2026-07-18"
    assert [item.sku for item in order.items] == ["CHR-ERG-01", "MAT-DESK-02"]
    assert order.items[0].description.startswith("Ergonomic")
    assert order.items[1].description.startswith("Anti-Fatigue")
    assert order.net_total == order.net_total  # validated inside extract
    assert str(order.gross_total) == "678.30"
    assert str(order.vat_total) == "108.30"
    assert str(order.net_total) == "570.00"
