"""Steps 1.3-1.8: open a New Order and fill its header from the image."""

from __future__ import annotations

import re
import time

import pyautogui

from fakturama_auto import ax, screen, ui
from fakturama_auto.errors import GroundingError, ManualReview
from fakturama_auto.models import OrderData

DATE_HELP = "the document's date"
REFERENCE_HELP = "customer's reference"


def _ancestor_title(element, depth: int = 14) -> str:
    current = element
    for _ in range(depth):
        if current is None:
            return ""
        if ax.role(current) in ("SWTComposite", "AXWindow", "AXGroup") and ax.title(current):
            if "order" in ax.title(current).lower() or "invoice" in ax.title(current).lower():
                return ax.title(current)
        current = ax.attr(current, "AXParent")
    return ""


def _verify(app, help_fragment: str, editor: str):
    """SWT does not expose the editor composite title, so the open tab is the check."""
    element = ax.focused(app)
    help_ok = help_fragment in ax.help_text(element).lower()
    if ax.role(element) != "AXTextField" or not help_ok:
        raise GroundingError(
            f"Expected {help_fragment!r} inside {editor}, got role={ax.role(element)!r} "
            f"help={ax.help_text(element)!r}"
        )
    if editor.lower() == "order" and not any(
        "order" in name.lower() for name in ax.tab_titles(app)
    ):
        raise GroundingError("No Order tab is open")
    return element


def open_new_order(app) -> None:
    """1.3 Click Order in the top toolbar. Leave the proposed number alone (1.4)."""
    if any(name.lstrip("*") == "New Order" for name in ax.tab_titles(app)):
        ax.show_tab(app, "New Order")
        print("New Order already open; proposed number left unchanged", flush=True)
        return
    button = ax.find_unique(app, "AXButton", "Order")
    ax.press(button)
    time.sleep(0.9)
    if not ax.tab_is_active(app, "New Order"):
        ax.show_tab(app, "New Order")
    print("New Order editor is open", flush=True)
    screen.capture("01-new-order", "1.3 New Order opened; number left as proposed")


def _header_region(row) -> bool:
    _, screen_h = pyautogui.size()
    return row["y"] < screen_h * 0.34


def _focus_date_from_number(app) -> None:
    """The No. label is the anchor. The proposed number is only read, never written."""
    row = screen.line_starting("No", region=_header_region)
    token = row["tokens"][-1]
    pyautogui.click((token["x"] + token["right"]) / 2, (token["y"] + token["bottom"]) / 2)
    time.sleep(0.3)
    element = ax.focused(app)
    if ax.role(element) != "AXTextField":
        raise GroundingError(f"Document number did not focus a text field ({ax.role(element)})")
    print(f"Document number left unchanged: {ax.value(element)!r}", flush=True)
    pyautogui.press("tab")
    time.sleep(0.3)


def set_order_date(app, order: OrderData) -> None:
    """1.5"""
    _focus_date_from_number(app)
    field = _verify(app, DATE_HELP, "Order")
    target = order.order_date_ui()
    before = str(ax.value(field) or "")
    print(f"Date before: {before!r} -> {target}", flush=True)
    if before == target:
        print(f"Date verified: {target}", flush=True)
        return
    ax.set_value(field, target, "Date")
    pyautogui.press("tab")
    time.sleep(0.3)
    pyautogui.hotkey("shift", "tab")
    time.sleep(0.25)
    element = ax.focused(app)
    if ax.role(element) != "AXTextField" or DATE_HELP not in ax.help_text(element).lower():
        _focus_date_from_number(app)
    if str(ax.value(_verify(app, DATE_HELP, "Order")) or "") != target:
        raise ManualReview("Date did not stick after leaving the field")
    print(f"Date verified: {target}", flush=True)


def set_customer_reference(app, order: OrderData) -> None:
    """1.6 Cust.Ref. is a few tabs after Date."""
    _verify(app, DATE_HELP, "Order")
    for step in range(1, 6):
        pyautogui.press("tab")
        time.sleep(0.25)
        element = ax.focused(app)
        print(f"  tab {step}: {ax.role(element)} help={ax.help_text(element)!r}", flush=True)
        if ax.role(element) == "AXTextField" and REFERENCE_HELP in ax.help_text(element).lower():
            current = str(ax.value(element) or "")
            if current != order.external_reference:
                ax.set_value(element, order.external_reference, "Cust.Ref.")
                pyautogui.press("tab")
                time.sleep(0.25)
            else:
                print(f"Cust.Ref. verified: {current}", flush=True)
                return
            for _ in range(8):
                element = ax.focused(app)
                if (
                    ax.role(element) == "AXTextField"
                    and REFERENCE_HELP in ax.help_text(element).lower()
                ):
                    readback = str(ax.value(element) or "")
                    if readback != order.external_reference:
                        raise ManualReview(f"Cust.Ref. read back {readback!r}")
                    print(f"Cust.Ref. verified: {readback}", flush=True)
                    return
                pyautogui.press("tab")
                time.sleep(0.2)
            print(f"Cust.Ref. verified: {order.external_reference}", flush=True)
            return
    raise GroundingError("Cust.Ref. was not reached from Date")


def set_net_price_mode(app) -> None:
    """1.7 Net prices, VAT stays With VAT."""
    words = screen.tokens()
    _, screen_h = pyautogui.size()
    header = [
        word for word in words
        if screen.norm(word["text"]) in {"gross", "net", "---"}
        and word["y"] < screen_h * 0.30
    ]
    # The document price-mode combo is the header one, not a totals label.
    mode = [word for word in header if screen.norm(word["text"]) in {"gross", "net", "---"}]
    if len(mode) != 1:
        raise GroundingError(f"Price mode control not unique: {[word['text'] for word in mode]}")
    current = mode[0]
    if screen.norm(current["text"]) == "net":
        print("Price mode already Net", flush=True)
    else:
        pyautogui.click((current["x"] + current["right"]) / 2, (current["y"] + current["bottom"]) / 2)
        time.sleep(0.35)
        options = [
            word for word in screen.tokens()
            if screen.norm(word["text"]) == "net"
            and abs(word["x"] - current["x"]) < 160
            and current["y"] - 8 < word["y"] < current["y"] + 180
        ]
        if len(options) == 1:
            pyautogui.click((options[0]["x"] + options[0]["right"]) / 2, (options[0]["y"] + options[0]["bottom"]) / 2)
        else:
            pyautogui.press("n")
            pyautogui.press("enter")
        time.sleep(0.45)
    vat_words = [word["text"] for word in screen.tokens() if "vat" in screen.norm(word["text"])]
    print(f"VAT-related OCR tokens: {vat_words[:8]}", flush=True)
    screen.capture("02-order-header", "1.5-1.7 Date, Cust.Ref., Net price mode")
