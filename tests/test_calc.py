"""Line math that does not need the sample image."""

from decimal import Decimal

from fakturama_auto.models import PAYMENT_CODES, Address, Item, OrderData, fakturama_date, money


def _item(**overrides) -> Item:
    values = dict(
        sku="CHR-ERG-01",
        description="Ergonomic Desk Chair",
        quantity=Decimal("2"),
        unit="pcs",
        unit_net=Decimal("250.00"),
        discount_percent=Decimal("10"),
        vat_percent=Decimal("19"),
        line_net=Decimal("450.00"),
    )
    values.update(overrides)
    return Item(**values)


def test_chair_prices():
    item = _item()
    assert item.gross_unit == Decimal("297.50")
    assert item.expected_line_net == Decimal("450.00")
    assert item.line_vat == Decimal("85.50")
    assert item.vat_name == "VAT 19%"


def test_mat_prices():
    item = _item(
        sku="MAT-DESK-02",
        description="Anti-Fatigue Desk Mat",
        quantity=Decimal("3"),
        unit_net=Decimal("40.00"),
        discount_percent=Decimal("0"),
        line_net=Decimal("120.00"),
    )
    assert item.gross_unit == Decimal("47.60")
    assert item.expected_line_net == Decimal("120.00")
    assert item.line_vat == Decimal("22.80")


def test_order_totals_accept_the_sample():
    billing = Address("Northstar Office GmbH", "Friedrichstrasse 88", "10117", "Berlin", "Germany")
    delivery = Address("Northstar Office Warehouse", "Beusselstrasse 44", "10553", "Berlin", "Germany")
    order = OrderData(
        external_reference="WEB-2026-0714-A17",
        order_date="2026-07-14",
        source_customer_id="CUST-1007",
        currency="EUR",
        company="Northstar Office GmbH",
        first_name="Marta",
        last_name="Klein",
        alias="NORTHSTAR-BERLIN",
        email="marta.klein@example.test",
        telephone="+49 30 5550 1420",
        billing=billing,
        delivery=delivery,
        payment_method="Bank Transfer",
        paid_status="PAID",
        payment_date="2026-07-18",
        items=[
            _item(),
            _item(
                sku="MAT-DESK-02",
                description="Anti-Fatigue Desk Mat",
                quantity=Decimal("3"),
                unit_net=Decimal("40.00"),
                discount_percent=Decimal("0"),
                line_net=Decimal("120.00"),
            ),
        ],
        net_total=Decimal("570.00"),
        vat_total=Decimal("108.30"),
        gross_total=Decimal("678.30"),
    )
    order.validate()
    assert order.payment_code == "Credit transfer"
    assert order.order_date_ui() == "Jul 14, 2026"
    assert order.payment_date_ui() == "Jul 18, 2026"
    assert order.is_paid
    assert not order.delivery_same_as_billing
    assert fakturama_date("2026-07-14") == "Jul 14, 2026"
    assert money("108.3") == Decimal("108.30")
    assert "Bank Transfer" in PAYMENT_CODES


def test_validation_rejects_a_bad_line():
    billing = Address("A", "Street 1", "10117", "Berlin", "Germany")
    order = OrderData(
        external_reference="X",
        order_date="2026-07-14",
        source_customer_id="C",
        currency="EUR",
        company="A",
        first_name="A",
        last_name="B",
        alias="A",
        email="a@b.c",
        telephone="1",
        billing=billing,
        delivery=billing,
        payment_method="Bank Transfer",
        paid_status="PAID",
        payment_date="2026-07-18",
        items=[_item(line_net=Decimal("1.00"))],
        net_total=Decimal("1.00"),
        vat_total=Decimal("0.00"),
        gross_total=Decimal("1.00"),
    )
    try:
        order.validate()
    except ValueError as exc:
        assert "CHR-ERG-01" in str(exc)
    else:
        raise AssertionError("bad line was accepted")
