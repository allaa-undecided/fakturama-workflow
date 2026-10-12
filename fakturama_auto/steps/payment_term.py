"""Steps 2.10.1-2.10.6: reuse or create the Payment Method, then select it."""

from __future__ import annotations

import time

import pyautogui

from fakturama_auto import ax, screen, ui
from fakturama_auto.errors import GroundingError, ManualReview
from fakturama_auto.models import OrderData


def _payment_list_matches(method: str) -> list[dict]:
    screen_w, screen_h = pyautogui.size()
    return [
        row for row in screen.lines()
        if screen.norm(row["text"]) == screen.norm(method)
        and row["x"] < screen_w * 0.72
        and row["y"] < screen_h * 0.70
    ]


def open_terms(app) -> None:
    """2.10.1 Data > terms of payment."""
    ui.open_list_via_data_menu(
        app,
        "terms of payment",
        "Terms of payment",
        "Terms of Payment",
        "Payment terms",
    )
    text = screen.visible_text()
    if "net days" not in text and "disc" not in text and "payment" not in text:
        raise GroundingError("Terms of payment list did not open")
    screen.capture("pay-01-terms-list", "2.10.1 terms of payment")


def search_terms(app, method: str) -> list[dict]:
    field = ui.search_field_right_of(app, "Search", x_min_ratio=0.55)
    ui.type_search(app, field, method)
    ui.wait_until_stable()
    # The search box itself contains the method name; ignore that one line.
    rows = [
        row for row in _payment_list_matches(method)
        if row["y"] > field_top(field)
    ]
    return rows


def field_top(field) -> float:
    position = str(ax.attr(field, "AXPosition"))
    import re
    match = re.search(r"y:\s*([\d.]+)", position)
    return float(match.group(1)) if match else 0


def payment_already_exact(app, order: OrderData) -> bool:
    """2.10.2 One exact row: go back and select it. Several rows: stop."""
    open_terms(app)
    field = ui.search_field_right_of(app, "Search", x_min_ratio=0.55)
    ui.type_search(app, field, order.payment_method)
    ui.wait_until_stable()
    top = field_top(field)
    rows = [row for row in _payment_list_matches(order.payment_method) if row["y"] > top + 10]
    screen.capture("pay-02-search", f"2.10.2 search {order.payment_method}: {len(rows)} row(s)")
    if len(rows) > 1:
        raise ManualReview(
            f"{len(rows)} payment terms match {order.payment_method!r}. "
            "Stopped for manual review."
        )
    if len(rows) == 1:
        print(f"Payment term {order.payment_method!r} already exists", flush=True)
        ax.show_tab(app, "New Debtor")
        return True
    return False


def _editor_label(label: str) -> dict:
    """Labels inside the payment-term editor.

    The editor opens in the left half of the window, so the cut is the
    navigator edge rather than the middle of the screen.
    """
    screen_w, screen_h = pyautogui.size()

    def region(row):
        return 480 < row["x"] < screen_w * 0.92 and 230 < row["y"] < screen_h * 0.75

    return screen.unique_line(label, exact=False, region=region)


def _write_editor_field(app, label: str, text: str, offset: int = 110) -> None:
    row = _editor_label(label)
    pyautogui.click(row["right"] + offset, (row["y"] + row["bottom"]) / 2)
    time.sleep(0.15)
    element = ui._focused_editable(app, label)
    ax.set_value(element, text, label)


def _require_blank_or_zero(app, label: str, zero: bool) -> None:
    row = _editor_label(label)
    pyautogui.click(row["right"] + 110, (row["y"] + row["bottom"]) / 2)
    time.sleep(0.15)
    element = ui._focused_editable(app, label)
    current = str(ax.value(element) or "").strip()
    allowed = {"", "0", "0%", "0.0", "0.0%", "0.00", "0.00%"} if zero else {""}
    if current not in allowed:
        if zero and current == "":
            ax.set_value(element, "0", label)
            current = str(ax.value(element) or "").strip()
        else:
            raise ManualReview(f"{label} is {current!r}; expected {'0' if zero else 'blank'}")
    print(f"  {label}: {current or 'blank'}", flush=True)


def _payment_code_label() -> dict:
    """The payment-code label. OCR usually glues it into one word."""
    hits = [
        token for token in screen.tokens()
        if "paymentcode" in "".join(ch for ch in screen.norm(token["text"]) if "a" <= ch <= "z")
        and token["x"] > 480
        and token["y"] > 230
    ]
    if len(hits) != 1:
        raise GroundingError(
            f"Payment code label matched {len(hits)}. Nothing was typed."
        )
    return hits[0]


def _payment_code_values(token: dict) -> list[dict]:
    values = [
        other for other in screen.tokens()
        if other["x"] > token["right"] - 4
        and abs(other["y"] - token["y"]) < 18
        and other["x"] < token["right"] + 360
    ]
    values.sort(key=lambda other: other["x"])
    return values


def _code_matches(blob: str, code: str) -> bool:
    """OCR often shortens the second word, as in 'Credit trar'."""
    wanted = screen.norm(code)
    if wanted in blob:
        return True
    parts = wanted.split()
    return len(parts) >= 2 and parts[0] in blob and parts[1][:4] in blob


def _payment_code_shown(token: dict, code: str) -> bool:
    blob = screen.norm(" ".join(other["text"] for other in _payment_code_values(token)))
    return _code_matches(blob, code)


def _type_payment_code(code: str) -> None:
    """Replace the combo text. Wait first so the keystrokes are not a notification."""
    import subprocess

    time.sleep(1.0)
    pyautogui.hotkey("command", "a")
    time.sleep(0.15)
    safe = code.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(
        ["osascript", "-e", f'tell application "System Events" to keystroke "{safe}"'],
        check=True,
    )
    time.sleep(0.45)
    pyautogui.press("enter")
    time.sleep(0.45)


def create_payment_term(app, order: OrderData) -> None:
    """2.10.3-2.10.6 Create the missing term and return to the Debtor."""
    print(f"Creating payment term {order.payment_method!r}", flush=True)
    open_titles = [name.lstrip("*") for name in ax.tab_titles(app)]
    if any(name.startswith("New Term of Payment") for name in open_titles):
        ax.show_tab(app, "New Term of Payment")
        time.sleep(0.4)
        print("Using the payment term editor already open", flush=True)
    else:
        plus = ui.green_plus_in(0.60, 0.06, 0.98, 0.32)
        pyautogui.click(plus[0], plus[1])
        time.sleep(0.6)
    text = screen.visible_text()
    if "cash discount" not in text and "net days" not in text and "payment" not in text:
        raise GroundingError("New term of payment editor did not open")
    _write_editor_field(app, "Name", order.payment_method)
    _require_blank_or_zero(app, "Account", zero=False)
    _write_editor_field(app, "Description", order.payment_method)
    code = order.payment_code
    token = _payment_code_label()
    if _payment_code_shown(token, code):
        print(f"  Payment code already {code}", flush=True)
    else:
        values = _payment_code_values(token)
        if values:
            click_x = (values[0]["x"] + values[0]["right"]) / 2
            click_y = (values[0]["y"] + values[0]["bottom"]) / 2
        else:
            click_x = token["right"] + 36
            click_y = (token["y"] + token["bottom"]) / 2
        pyautogui.mouseUp()
        pyautogui.click(click_x, click_y)
        time.sleep(0.25)
        _type_payment_code(code)
        shown = False
        for _ in range(2):
            try:
                shown = _payment_code_shown(_payment_code_label(), code)
            except GroundingError:
                shown = _code_matches(screen.visible_text(), code)
            if shown:
                break
            time.sleep(0.45)
        if not shown:
            raise ManualReview(f"Payment code {code!r} was not verified. Term not saved.")
    print(f"  Payment code: {code}", flush=True)
    for label in ("Cash discount", "Discount days", "Net days"):
        _require_blank_or_zero(app, label, zero=True)
    print("  unpaid/deposit/paid text left blank; Set as standard not clicked", flush=True)
    screen.capture("pay-03-term-filled", f"2.10.3-2.10.5 {order.payment_method} / {code}")
    ui.save_once(app, "payment term")
    time.sleep(0.4)
    ax.show_tab(app, "New Debtor")
    if not ax.tab_is_active(app, "New Debtor"):
        raise GroundingError("Could not return to the New Debtor editor")
    print("Returned to the Debtor editor", flush=True)


def ensure_payment_method(app, order: OrderData) -> None:
    """Select the method on the Debtor. Create the term first when it does not exist."""
    if not payment_already_exact(app, order):
        # search_terms left the filter active and the list empty. Clear it, then add.
        field = ui.search_field_right_of(app, "Search", x_min_ratio=0.55)
        ui.type_search(app, field, "")
        create_payment_term(app, order)
    from fakturama_auto.steps.debtor import select_payment_method
    select_payment_method(app, order)
