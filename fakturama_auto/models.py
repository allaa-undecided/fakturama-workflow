"""Structured order extracted from a source image."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP


TWOPLACES = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def fakturama_date(iso_date: str) -> str:
    """US medium date, matching this Fakturama installation (e.g. Jul 14, 2026)."""
    parsed = datetime.strptime(iso_date, "%Y-%m-%d")
    return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year}"


@dataclass
class Address:
    company: str
    street: str
    zip_code: str
    city: str
    country: str
    additional_name: str = ""
    specification: str = ""
    district: str = ""

    def same_place(self, other: "Address") -> bool:
        return (
            self.street.casefold() == other.street.casefold()
            and self.zip_code == other.zip_code
            and self.city.casefold() == other.city.casefold()
            and self.country.casefold() == other.country.casefold()
        )


@dataclass
class Item:
    sku: str
    description: str
    quantity: Decimal
    unit: str
    unit_net: Decimal
    discount_percent: Decimal
    vat_percent: Decimal
    line_net: Decimal

    @property
    def gross_unit(self) -> Decimal:
        """Product master price. Line discount is not applied."""
        return money(self.unit_net * (Decimal(1) + self.vat_percent / Decimal(100)))

    @property
    def expected_line_net(self) -> Decimal:
        factor = Decimal(1) - self.discount_percent / Decimal(100)
        return money(self.quantity * self.unit_net * factor)

    @property
    def line_vat(self) -> Decimal:
        return money(self.expected_line_net * self.vat_percent / Decimal(100))

    @property
    def vat_name(self) -> str:
        if self.vat_percent == self.vat_percent.to_integral():
            return f"VAT {int(self.vat_percent)}%"
        text = format(self.vat_percent.normalize(), "f")
        return f"VAT {text}%"


PAYMENT_CODES = {
    "Bank Transfer": "Credit transfer",
    "Credit Card": "Credit card",
    "SEPA Direct Debit": "SEPA direct debit",
}


@dataclass
class OrderData:
    external_reference: str
    order_date: str
    source_customer_id: str
    currency: str
    company: str
    first_name: str
    last_name: str
    alias: str
    email: str
    telephone: str
    billing: Address
    delivery: Address
    payment_method: str
    paid_status: str
    payment_date: str
    items: list[Item] = field(default_factory=list)
    net_total: Decimal = Decimal("0")
    vat_total: Decimal = Decimal("0")
    gross_total: Decimal = Decimal("0")

    @property
    def delivery_same_as_billing(self) -> bool:
        return self.billing.same_place(self.delivery) and (
            self.billing.company.casefold() == self.delivery.company.casefold()
        )

    @property
    def payment_code(self) -> str:
        try:
            return PAYMENT_CODES[self.payment_method]
        except KeyError as exc:
            raise ValueError(
                f"No payment-code mapping for {self.payment_method!r}. "
                "Supported: " + ", ".join(PAYMENT_CODES)
            ) from exc

    @property
    def is_paid(self) -> bool:
        return self.paid_status.strip().upper() == "PAID"

    def order_date_ui(self) -> str:
        return fakturama_date(self.order_date)

    def payment_date_ui(self) -> str:
        return fakturama_date(self.payment_date)

    def validate(self) -> None:
        problems = []
        line_sum = Decimal("0")
        vat_sum = Decimal("0")
        for item in self.items:
            if item.line_net != item.expected_line_net:
                problems.append(
                    f"{item.sku}: source line {item.line_net} != "
                    f"qty x net x (1 - discount) {item.expected_line_net}"
                )
            line_sum += item.expected_line_net
            vat_sum += item.line_vat
        if money(line_sum) != self.net_total:
            problems.append(f"net total {self.net_total} != sum of lines {money(line_sum)}")
        if money(vat_sum) != self.vat_total:
            problems.append(f"VAT total {self.vat_total} != computed {money(vat_sum)}")
        if money(self.net_total + self.vat_total) != self.gross_total:
            problems.append(
                f"gross {self.gross_total} != net + VAT {money(self.net_total + self.vat_total)}"
            )
        if not self.items:
            problems.append("no line items")
        if problems:
            raise ValueError("Order image failed validation:\n- " + "\n- ".join(problems))
