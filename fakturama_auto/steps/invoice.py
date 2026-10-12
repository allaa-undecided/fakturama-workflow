"""Steps 5.1-5.7: payment status on the linked Invoice, then verify both documents."""

from __future__ import annotations

import time

import pyautogui

from fakturama_auto import ax, screen, ui
from fakturama_auto.errors import ManualReview
from fakturama_auto.models import OrderData
from fakturama_auto.steps import order_finish


def _show_invoice(app) -> None:
    titles = [name.lstrip("*") for name in ax.tab_titles(app) if "invoice" in name.lower()]
    unique = [name for name in titles if titles.count(name) == 1]
    if len(titles) == 1:
        ax.show_tab(app, titles[0])
        return
    # Two unsaved invoices can be open. The one on screen is the one just edited.
    if any(screen.norm(token["text"]) == "paid" and token["y"] > 680 for token in screen.tokens()):
        print(f"Invoice editor already showing. Tabs: {titles}", flush=True)
        return
    if len(unique) == 1:
        ax.show_tab(app, unique[0])
        return
    raise ManualReview(f"Expected one Invoice tab, found {titles}")


def verify_copied_fields(order: OrderData) -> None:
    """5.1 Leave number, invoice date and service date. Confirm the copy."""
    parts = [
        order.external_reference,
        order.billing.street,
        order.order_date_ui(),
    ]
    text = screen.visible_text() + "\n" + order_finish._order_figures()
    missing = [part for part in parts if screen.norm(part) not in screen.norm(text)]
    for item in order.items:
        if item.sku.lower() not in text.lower() and item.sku.split("-")[0].lower() not in text.lower():
            missing.append(item.sku)
    if f"{order.gross_total:.2f}" not in text:
        missing.append(f"{order.gross_total:.2f}")
    if missing:
        raise ManualReview(f"Invoice was not copied from the Order. Missing {missing}")
    print("Invoice copied Cust.Ref., addresses, lines and totals from the Order", flush=True)
    screen.capture("14-invoice-copied", "5.1 Invoice populated from the Order")


def set_payment_method(app, order: OrderData) -> None:
    """5.2 The method must already exist. Do not create one from the Invoice.

    The invoice has no Payment label. The method is the combo beside paid.
    """
    banks = [
        token for token in screen.tokens()
        if token["y"] > 680 and "bank" in screen.norm(token["text"])
    ]
    if banks:
        print("Invoice payment already shows Bank Transfer", flush=True)
        return
    # Before paid is ticked the combo shows Pay Cash and the next label is Due.
    # After paid is ticked the next label is "at".
    paid = [row for row in screen.find_lines("paid", exact=True) if row["y"] > 680]
    if len(paid) != 1:
        raise ManualReview(f"Invoice payment combo was not beside paid ({len(paid)}).")
    followers = [
        token for token in screen.tokens()
        if token["y"] > 680
        and token["x"] > paid[0]["right"] + 40
        and screen.norm(token["text"]) in {"due", "at"}
    ]
    if len(followers) != 1:
        raise ManualReview(
            f"Invoice payment combo was not before Due or at ({len(followers)})."
        )
    pyautogui.click(followers[0]["x"] - 34, (paid[0]["y"] + paid[0]["bottom"]) / 2)
    time.sleep(0.45)
    options = [
        token for token in screen.tokens()
        if "bank" in screen.norm(token["text"]) and token["y"] > paid[0]["bottom"] - 8
    ]
    if len(options) != 1:
        raise ManualReview(
            f"Invoice payment method {order.payment_method!r} matched {len(options)} rows. "
            "Nothing was chosen."
        )
    screen.click_line(options[0])
    time.sleep(0.35)
    if not any("bank" in screen.norm(token["text"]) and token["y"] > 680 for token in screen.tokens()):
        raise ManualReview(f"Invoice payment did not show {order.payment_method!r}.")
    print(f"Invoice payment: {order.payment_method}", flush=True)


def apply_paid_status(app, order: OrderData) -> None:
    """5.3 Paid: tick paid, set the payment date and the full total. Otherwise leave it."""
    if not order.is_paid:
        print("Paid status is not PAID. Leaving paid clear.", flush=True)
        return
    paid = screen.find_lines("paid", exact=True)
    # The checkbox label, not the PAID badge from some other view.
    _, screen_h = pyautogui.size()
    paid = [row for row in paid if row["y"] > screen_h * 0.35]
    if len(paid) != 1:
        raise ManualReview(f"Invoice 'paid' control matched {len(paid)}. Nothing was marked paid.")
    row = paid[0]
    already = [
        token for token in screen.tokens()
        if screen.norm(token["text"]) == "at" and token["y"] > 680
    ]
    if not already:
        pyautogui.click(row["x"] - 16, (row["y"] + row["bottom"]) / 2)
        time.sleep(0.3)
    # "at" is the paid date. The header field named Date is the invoice date.
    ats = [
        token for token in screen.tokens()
        if screen.norm(token["text"]) == "at" and token["y"] > 680
    ]
    if len(ats) != 1:
        raise ManualReview(f"Paid date matched {len(ats)}. The invoice date was not changed.")
    paid_on = ats[0]
    pyautogui.click(paid_on["right"] + 36, (paid_on["y"] + paid_on["bottom"]) / 2)
    time.sleep(0.2)
    ax.set_value(ax.focused(app), order.payment_date_ui(), "paid date")
    value = f"{order.gross_total:.2f}"
    ui.set_text_right_of(app, "Value", value, offset=50)
    print(f"Paid on {order.payment_date_ui()} value {value}", flush=True)
    screen.capture("15-invoice-paid", "5.3 paid, payment date, full value")


def save_invoice(app) -> None:
    """5.4"""
    _show_invoice(app)
    ui.save_once(app, "Invoice")
    screen.capture("16-invoice-saved", "5.4 Invoice saved once")


def _documents_text() -> str:
    """The documents grid. Tesseract misses it, and the toolbar search is a gray placeholder."""
    return screen.visible_text() + "\n" + order_finish._vision_crop((400, 180, 1600, 700))


def _document_header():
    headers = [
        token for token in screen.tokens()
        if screen.norm(token["text"]) == "document" and 150 < token["y"] < 420
    ]
    return headers[0] if len(headers) == 1 else None


def _title_is(word: str) -> bool:
    """The view title above the grid. A selected tree row is white and is not read."""
    header = _document_header()
    ceiling = header["y"] - 6 if header else 280
    for token in screen.tokens():
        if token["y"] > ceiling or token["x"] < 400:
            continue
        name = screen.norm(token["text"])
        if word == "paid":
            if "unpaid" in name:
                continue
            if name == "paid" or name.endswith("/paid") or name.endswith(" paid"):
                return True
            continue
        if word in name:
            return True
    return False


def _tree_hits(word: str) -> list[dict]:
    """Category labels in the tree column, left of Document and above the terminal."""
    header = _document_header()
    _, screen_h = pyautogui.size()
    if header:
        left, right = header["x"] - 280, header["x"] - 8
        top, bottom = header["y"] - 30, min(header["y"] + 220, screen_h * 0.62)
    else:
        left, right, top, bottom = 350, 900, 180, screen_h * 0.5
    hits = []
    for token in screen.tokens():
        if not (top < token["y"] < bottom and left < token["x"] < right):
            continue
        name = screen.norm(token["text"])
        if word == "paid":
            if name != "paid":
                continue
        elif name != word and not name.startswith(word):
            continue
        hits.append(token)
    return hits


def _pick_tree_hit(word: str) -> dict | None:
    """One tree row. paid sits under Invoices; a second paid elsewhere is not that row."""
    hits = _tree_hits(word)
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0]
    if word == "paid":
        anchors = _tree_hits("unpaid") or _tree_hits("invoices")
        if anchors:
            floor = min(token["y"] for token in anchors)
            below = [token for token in hits if token["y"] >= floor - 4]
            if below:
                return min(below, key=lambda token: token["y"])
    return min(hits, key=lambda token: (token["x"], token["y"]))


def _click_document_tree(word: str) -> None:
    """Open a documents category. The title counts when that category is already open."""
    if _title_is(word):
        print(f"Documents is already showing {word}", flush=True)
        return
    token = None
    for _ in range(3):
        token = _pick_tree_hit(word)
        if token is not None:
            break
        time.sleep(0.4)
    if token is None:
        raise ManualReview(
            f"Documents category {word!r} matched 0. The list was not opened."
        )
    pyautogui.click((token["x"] + token["right"]) / 2, (token["y"] + token["bottom"]) / 2)
    time.sleep(0.45)


def _list_shows_document(order: OrderData) -> bool:
    text = _documents_text()
    folded = screen.norm(text)
    total = f"{order.gross_total:.2f}"
    return "web-202" in folded and (total in text or total in folded)


def verify_both_documents(app, order: OrderData) -> None:
    """5.5 The Invoice is under Invoices/paid and the Order is under Orders.

    The toolbar search is placeholder text, not a label, so it is not clicked.
    The reference is truncated in this list. The total identifies the row.
    """
    titles = [name.lstrip("*") for name in ax.tab_titles(app)]
    if "Documents" in titles:
        ax.show_tab(app, "Documents")
        time.sleep(0.4)
    else:
        ui.open_list_via_data_menu(app, "Documents", "Document")
        time.sleep(0.5)
    _click_document_tree("orders")
    if not _list_shows_document(order):
        raise ManualReview("Documents Orders list does not show the reference and the gross total")
    print("Orders list shows the source Order", flush=True)
    # Clicking Invoices while it is open collapses it and hides paid.
    if not _title_is("paid") and _pick_tree_hit("paid") is None:
        _click_document_tree("invoices")
    _click_document_tree("paid")
    text = _documents_text()
    if not _list_shows_document(order) or "paid" not in screen.norm(text):
        raise ManualReview(
            "Documents Invoices/paid list does not show the paid Invoice and the gross total"
        )
    screen.capture("17-documents-final", "5.5 Invoice under paid and Order under Orders")
    print("Documents list shows the paid Invoice and the source Order", flush=True)


def confirm_persisted_payment(app, order: OrderData) -> None:
    """5.6 Reopen the Invoice and read the payment method, paid state, date and value."""
    # Cust.Ref. is truncated to WEB-202… in this list. The newest matching row is the lowest.
    refs = [
        token for token in screen.tokens()
        if "web-202" in screen.norm(token["text"]) and token["x"] > 700 and token["y"] > 180
    ]
    if not refs:
        raise ManualReview("Could not reopen the Invoice from Documents")
    token = max(refs, key=lambda item: item["y"])
    pyautogui.click((token["x"] + token["right"]) / 2, (token["y"] + token["bottom"]) / 2)
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(0.7)
    _show_invoice(app)
    text = screen.visible_text()
    expected = [
        screen.norm(order.payment_method),
        screen.norm(order.payment_date_ui()) if order.is_paid else "",
        screen.norm(f"{order.gross_total:.2f}") if order.is_paid else "",
    ]
    missing = [part for part in expected if part and part not in text]
    if missing:
        raise ManualReview(f"Reopened Invoice is missing {missing}")
    if order.is_paid and "paid" not in text:
        raise ManualReview("Reopened Invoice does not show paid")
    screen.capture("18-invoice-reopened", "5.6 Persisted payment method, paid, date and value")
    print("Persisted payment verified on the reopened Invoice", flush=True)
    print("Flow complete. No delivery, correction or dunning document was created.", flush=True)
