"""One Order-first run, resumable at a PDF step number."""

from __future__ import annotations

from pathlib import Path

from fakturama_auto import ax, screen
from fakturama_auto.errors import ManualReview
from fakturama_auto.extract import extract_order
from fakturama_auto.models import OrderData
from fakturama_auto.steps import debtor, invoice, order_finish, order_header, payment_term, product


def _steps(app, order: OrderData, dry_run: bool):
    """Callables in PDF order. Each one leaves Fakturama ready for the next."""

    def header():
        order_header.open_new_order(app)
        order_header.set_order_date(app, order)
        order_header.set_customer_reference(app, order)
        order_header.set_net_price_mode(app)

    def select_or_note():
        debtor.click_existing_contact_icon()
        debtor.search_debtor(app, order)
        return debtor.try_select_existing(app, order)

    def create_debtor():
        debtor.open_new_debtor(app)
        debtor.fill_identity(app, order)
        debtor.fill_main_address(app, order)
        debtor.add_delivery_address(app, order)
        debtor.fill_miscellaneous(app, order)

    def payment():
        payment_term.ensure_payment_method(app, order)

    def save_and_reselect():
        if dry_run:
            print("Dry run: Debtor not saved", flush=True)
            screen.capture("dry-run-debtor", "Debtor filled, not saved")
            return
        debtor.save_debtor(app)
        debtor.reselect_on_order(app, order)

    def products():
        product.add_all_products(app, order)

    def finish_order():
        order_finish.verify_order(order)
        if dry_run:
            print("Dry run: Order not saved", flush=True)
            return ""
        return order_finish.save_order(app)

    def documents_and_invoice(number):
        if dry_run:
            return
        order_finish.verify_documents_row(app, order, number, "Order")
        order_finish.open_followup_invoice(app, number)

    def finish_invoice():
        invoice.verify_copied_fields(order)
        invoice.set_payment_method(app, order)
        invoice.apply_paid_status(app, order)
        if dry_run:
            print("Dry run: Invoice not saved", flush=True)
            screen.capture("dry-run-invoice", "Invoice filled, not saved")
            return
        invoice.save_invoice(app)
        invoice.verify_both_documents(app, order)
        invoice.confirm_persisted_payment(app, order)

    return [
        ("1.3", "Open a New Order and fill its header", header),
        ("2.1", "Select an existing Debtor, or start creation", select_or_note),
        ("2.5", "Create the Debtor, addresses and miscellaneous", create_debtor),
        ("2.10", "Select or create the payment method", payment),
        ("2.11", "Save the Debtor and select it on the Order", save_and_reselect),
        ("3.1", "Select or create every product line", products),
        ("4.1", "Verify and save the Order", finish_order),
        ("4.5", "Confirm the Order and open its Invoice", documents_and_invoice),
        ("5.1", "Complete and verify the Invoice", finish_invoice),
    ]


def run(image: Path, from_step: str = "1.3", dry_run: bool = False) -> OrderData:
    order = extract_order(image)
    print(
        f"Extracted {order.external_reference}: {order.company}, "
        f"{len(order.items)} items, {order.gross_total} {order.currency}, "
        f"payment {order.payment_method} {order.paid_status}",
        flush=True,
    )
    app = ax.activate()
    screen.capture("00-before", f"Before step {from_step}")
    steps = _steps(app, order, dry_run)
    known = [step_id for step_id, _, _ in steps]
    if from_step not in known:
        raise ManualReview(f"--from-step must be one of {known}")

    selected_existing = False
    document_number = ""
    started = False
    for step_id, description, action in steps:
        if not started:
            if step_id != from_step:
                continue
            started = True
        # An exact Debtor match skips creation and payment setup.
        if selected_existing and step_id in {"2.5", "2.10", "2.11"}:
            print(f"Skipping {step_id} {description}: existing Debtor was selected", flush=True)
            if step_id == "2.11":
                debtor.confirm_addresses_on_order(order)
            continue
        print(f"\n=== {step_id} {description} ===", flush=True)
        if step_id == "2.1":
            selected_existing = bool(action())
            continue
        if step_id == "4.1":
            document_number = action() or ""
            continue
        if step_id == "4.5":
            action(document_number)
            continue
        action()
    print("\nDone.", flush=True)
    return order
