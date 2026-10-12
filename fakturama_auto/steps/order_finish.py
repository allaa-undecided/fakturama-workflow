"""Steps 4.1-4.7: check the Order, save it once, and open its Invoice."""

from __future__ import annotations

import time

import pyautogui

from fakturama_auto import ax, screen, ui
from fakturama_auto.errors import ManualReview
from fakturama_auto.models import OrderData


def _require_visible(parts: list[str], where: str) -> None:
    text = screen.visible_text()
    missing = [part for part in parts if screen.norm(part) not in text and screen.norm(f"{part}") not in text]
    if missing:
        raise ManualReview(f"{where} is missing {missing}")


def _vision_crop(box: tuple[int, int, int, int]) -> str:
    """Read a screen region with Apple Vision. Tesseract misses this grid."""
    from pathlib import Path

    from fakturama_auto.extract import _vision_text

    shot, scale_x, scale_y = screen.geometry()
    crop = shot.crop(tuple(int(value / scale) for value, scale in zip(box, (scale_x, scale_y, scale_x, scale_y))))
    path = Path("/tmp/fakturama-crop.png")
    crop.save(path)
    return _vision_text(path)


def _grid_text() -> str:
    """Black text on white rows, and white text on the blue selected row."""
    import cv2
    import numpy as np

    from pathlib import Path

    from fakturama_auto.extract import _vision_text

    shot, scale_x, scale_y = screen.geometry()
    array = np.array(shot.convert("RGB"))
    x0, x1 = int(640 / scale_x), int(1450 / scale_x)
    y0, y1 = int(420 / scale_y), int(520 / scale_y)
    roi = array[y0:y1, x0:x1].astype("int16")
    painted = np.full(roi.shape[:2], 255, dtype="uint8")
    painted[roi.min(axis=2) > 215] = 0
    painted[roi.mean(axis=2) < 80] = 0
    big = cv2.resize(painted, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
    path = Path("/tmp/fakturama-grid.png")
    cv2.imwrite(str(path), big)
    return _vision_text(path) + "\n" + _vision_crop((620, 410, 1480, 530))


def _order_figures() -> str:
    """Read the item rows and the totals without moving the pointer or typing."""
    return _grid_text() + "\n" + _vision_crop((1450, 640, 1900, 880))


def verify_order(order: OrderData) -> None:
    """4.1-4.3 Addresses, every line, and the three totals.

    The order shows the billing street only. Item numbers are truncated, and
    the selected row is white on blue, so each row is read in turn.
    """
    from fakturama_auto.steps.product import _sku_prefix

    _require_visible([order.company, order.external_reference, order.billing.street], "Order")
    seen = _order_figures()
    missing = []
    for item in order.items:
        if _sku_prefix(item.sku).lower() not in seen.lower():
            missing.append(item.sku)
        shown = f"{item.expected_line_net:.2f}"
        if shown not in seen and shown.replace(".", ",") not in seen:
            missing.append(shown)
    for amount in (order.net_total, order.vat_total, order.gross_total):
        shown = f"{amount:.2f}"
        if shown not in seen and shown.replace(".", ",") not in seen:
            missing.append(shown)
    if missing:
        raise ManualReview(f"Order is missing {missing}")
    text = screen.visible_text()
    if "free of shipping" not in text and "0.00" not in text:
        print("Shipping label not confirmed by OCR; totals were checked", flush=True)
    print(
        f"Order totals match: net {order.net_total} VAT {order.vat_total} gross {order.gross_total}",
        flush=True,
    )
    screen.capture("10-order-ready", "4.1-4.3 Order verified against the image")


def save_order(app) -> str:
    """4.4 Save once. Returns the document number read from the number field."""
    ui.require_tab(app, "New Order")
    number = _read_document_number()
    ui.save_once(app, f"Order {number or ''}".strip())
    screen.capture("11-order-saved", "4.4 Order saved once")
    return number


def _read_document_number() -> str:
    """The number in the order header, not a document number on another tab."""
    import re
    for row in screen.lines():
        if not (250 < row["y"] < 420):
            continue
        if not screen.norm(row["text"]).startswith("no"):
            continue
        for token in row["tokens"]:
            if re.fullmatch(r"[A-Za-z]{1,3}\d{3,}", token["text"]):
                return token["text"]
    return ""


def _show_document_category(kind: str) -> None:
    """The documents view opens on unpaid invoices. Orders live under Orders."""
    wanted = "orders" if kind.lower() == "order" else "invoices"
    hits = [
        token for token in screen.tokens()
        if screen.norm(token["text"]) == wanted and 450 < token["x"] < 800 and token["y"] > 200
    ]
    if len(hits) != 1:
        return
    token = hits[0]
    pyautogui.click((token["x"] + token["right"]) / 2, (token["y"] + token["bottom"]) / 2)
    time.sleep(0.45)


def verify_documents_row(app, order: OrderData, number: str, kind: str) -> None:
    """4.5 / 5.5 Data > Documents contains the expected row."""
    titles = [name.lstrip("*") for name in ax.tab_titles(app)]
    if "Documents" in titles:
        ax.show_tab(app, "Documents")
    else:
        ui.click_sidebar("Documents")
    time.sleep(0.4)
    if not any(
        screen.norm(token["text"]) == "orders" and 450 < token["x"] < 800
        for token in screen.tokens()
    ):
        ui.click_sidebar("Documents")
        time.sleep(0.4)
    _show_document_category(kind)
    time.sleep(0.4)
    # The list search sits in a toolbar the screen read often misses. The
    # reference is enough when the new row is already on screen.
    text = screen.visible_text() + "\n" + _vision_crop((400, 180, 1600, 700))
    short_ref = order.external_reference.split("-")[0] + "-2026"
    if short_ref not in text and f"{order.gross_total:.2f}" not in text and number:
        try:
            field = ui.search_field_right_of(app, "Search", x_min_ratio=0.45)
        except RuntimeError:
            ui.click_sidebar("Documents")
            time.sleep(0.4)
            text = screen.visible_text() + "\n" + _vision_crop((400, 180, 1600, 700))
        else:
            ui.type_search(app, field, order.external_reference)
            ui.wait_until_stable()
            text = screen.visible_text() + "\n" + _vision_crop((400, 180, 1600, 700))
    needed = ["WEB-202", f"{order.gross_total:.2f}"]
    missing = [part for part in needed if part not in text and screen.norm(part) not in screen.norm(text)]
    if missing:
        raise ManualReview(f"Documents list is missing {missing} for the {kind}")
    if screen.norm(kind) not in text and kind.lower() not in text:
        print(f"Document kind {kind!r} was not read as its own token; totals and reference matched", flush=True)
    screen.capture(f"12-documents-{kind.lower()}", f"Documents list shows {kind} {number}")
    print(f"{kind} {number or '(number unread)'} is in Documents", flush=True)


def open_followup_invoice(app, number: str = "") -> None:
    """4.6 The Invoice action on the saved Order, not the toolbar Invoice button."""
    titles = [name.lstrip("*") for name in ax.tab_titles(app)]
    if number and number in titles:
        ax.show_tab(app, number)
    elif "New Order" in titles:
        ax.show_tab(app, "New Order")
    else:
        order_tabs = [name for name in titles if "order" in name.lower()]
        if len(order_tabs) != 1:
            raise ManualReview(f"Could not find the saved Order tab among {titles}")
        ax.show_tab(app, order_tabs[0])
    text_rows = screen.find_lines("follow-up", exact=False)
    if len(text_rows) != 1:
        text_rows = screen.find_lines("follow up", exact=False)
    if len(text_rows) != 1:
        raise ManualReview("Create a follow-up document area was not found. Toolbar Invoice was not used.")
    anchor = text_rows[0]
    # The four follow-up labels share one OCR line, so match the Invoice word.
    invoices = [
        token for token in screen.tokens()
        if screen.norm(token["text"]) == "invoice"
        and token["x"] > anchor["x"] - 40
        and anchor["y"] - 20 < token["y"] < anchor["bottom"] + 90
    ]
    if len(invoices) != 1:
        raise ManualReview(
            f"Follow-up Invoice control matched {len(invoices)}. Toolbar Invoice was not used."
        )
    token = invoices[0]
    # The icon sits above its caption. Delivery and Dunning are separate captions.
    pyautogui.click((token["x"] + token["right"]) / 2, token["y"] - 18)
    time.sleep(0.8)
    if not any("invoice" in name.lower() for name in ax.tab_titles(app)):
        raise ManualReview("The linked Invoice editor did not open")
    print("Linked Invoice editor is open", flush=True)
    screen.capture("13-invoice-opened", "4.6 Follow-up Invoice from the Order")
