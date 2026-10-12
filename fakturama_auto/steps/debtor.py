"""Steps 2.1-2.13: select an existing Debtor from the Order, or create one."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pyautogui

from fakturama_auto import ax, screen, ui
from fakturama_auto.errors import GroundingError, ManualReview
from fakturama_auto.models import Address, OrderData

ICON = Path(__file__).resolve().parents[2] / "existing_contact_icon.png"


def _editor_region(row) -> bool:
    """Debtor form fields sit in the editor, to the right of the left navigator.

    The window is not always flush with the screen, so the cut is the window's
    own left edge plus the navigator width, not a fraction of the screen.
    """
    return row["x"] > 20 and row["y"] > 140


def _section_twistie(bar: dict) -> tuple[float, float]:
    """The disclosure triangle at the right end of the common-data bar."""
    shot, scale_x, scale_y = screen.geometry()
    array = np.array(shot.convert("RGB"))
    y0 = max(0, int(bar["y"] / scale_y) - 8)
    y1 = min(array.shape[0], int(bar["bottom"] / scale_y) + 10)
    band = array[y0:y1]
    red = band[:, :, 0].astype(int)
    green = band[:, :, 1].astype(int)
    blue = band[:, :, 2].astype(int)
    blue_bar = (blue > 190) & (blue > red + 40) & (blue > green + 15) & (red < 210)
    start = int(bar["right"] / scale_x)
    columns = np.where(blue_bar[:, start:].any(axis=0))[0]
    if len(columns) == 0:
        raise GroundingError("The common-data bar has no disclosure triangle.")
    right = start + int(columns.max())
    inset = max(0, right - int(14 / scale_x))
    rows = np.where(blue_bar[:, inset])[0]
    if len(rows) == 0:
        raise GroundingError("The common-data disclosure triangle is not on the bar.")
    return inset * scale_x, (y0 + float(np.median(rows))) * scale_y


def _letters(text: str) -> str:
    return "".join(ch for ch in screen.norm(text) if "a" <= ch <= "z")


def _cust_ref_visible() -> bool:
    """Cust.Ref. sits on the common-data bar, so the section is already open."""
    return any(
        "cust" in _letters(token["text"]) and "ref" in _letters(token["text"])
        and token["x"] > 400
        and token["y"] > 180
        for token in screen.tokens()
    )


def _invoice_address_line() -> dict | None:
    """The address tab.

    OCR reads this as 'invoice address', 'oice address', or 'Addresses invoice'.
    The two words are often split onto separate lines.
    """
    found = []
    for row in screen.lines():
        if row["x"] <= 400 or row["y"] <= 180:
            continue
        text = screen.norm(row["text"])
        if "oice address" in text or ("invoice" in text and "address" in text):
            found.append(row)
    if not found:
        tokens = [
            token for token in screen.tokens()
            if token["x"] > 400 and token["y"] > 180
        ]
        for token in tokens:
            name = _letters(token["text"])
            if "ddress" in name and ("oice" in name or "invo" in name):
                found.append(token)
                continue
            if "oice" not in name and "invo" not in name:
                continue
            neighbors = [
                other for other in tokens
                if "ddress" in _letters(other["text"])
                and abs(other["y"] - token["y"]) < 20
                and token["right"] - 8 < other["x"] < token["right"] + 150
            ]
            if len(neighbors) != 1:
                continue
            other = neighbors[0]
            found.append({
                "text": f"{token['text']} {other['text']}",
                "x": min(token["x"], other["x"]),
                "y": min(token["y"], other["y"]),
                "right": max(token["right"], other["right"]),
                "bottom": max(token["bottom"], other["bottom"]),
            })
    unique = []
    for row in found:
        if any(abs(row["y"] - kept["y"]) < 22 and abs(row["x"] - kept["x"]) < 160 for kept in unique):
            continue
        unique.append(row)
    if len(unique) > 1:
        raise ManualReview(
            f"Invoice address matched {len(unique)} times. The contact icon was not clicked."
        )
    return unique[0] if unique else None


def _common_data_bar() -> dict:
    found = [
        row for row in screen.lines()
        if "common" in screen.norm(row["text"]) and row["x"] > 400 and row["y"] > 180
    ]
    if len(found) != 1:
        sample = [row["text"] for row in found[:6]]
        raise GroundingError(
            f"The common-data bar matched {len(found)} times {sample}. "
            "The address section was left unchanged."
        )
    return found[0]


def ensure_address_visible() -> None:
    """Open the common-data section when it is hiding the address.

    A new order draws that section collapsed. Cust.Ref. and Invoice address
    are on screen only after the triangle at the right end of the bar is opened.
    """
    if _invoice_address_line() is not None:
        return
    # Cust.Ref. is on this bar. Clicking the triangle would collapse it.
    if _cust_ref_visible():
        time.sleep(0.35)
        if _invoice_address_line() is not None:
            return
        raise GroundingError(
            "Common data is open, but the invoice address tab was not read. Nothing was clicked."
        )
    bar = _common_data_bar()
    x, y = _section_twistie(bar)
    print(f"Opening common data at ({x:.0f}, {y:.0f})", flush=True)
    pyautogui.click(x, y)
    time.sleep(0.55)
    if _invoice_address_line() is None:
        raise GroundingError(
            "Invoice address is still hidden after opening the common-data section."
        )


def click_existing_contact_icon() -> None:
    """2.1 The upper icon beside Addresses. Never the green + under it.

    The two icons stack on the address rows. The green + is the lower one,
    on the delivery row. The selector is the same x, one row above.
    """
    ensure_address_visible()
    address = _invoice_address_line()
    if address is None:
        raise GroundingError("Invoice address is not visible, so the contact icon was not clicked.")
    pluses = screen.green_plus_buttons()
    near = [
        plus for plus in pluses
        if abs(plus[0] - address["x"]) < 140
        and 8 < plus[1] - address["y"] < 90
    ]
    if len(near) != 1:
        raise ManualReview(
            f"Address green + matched {len(near)} near {address['text']!r}. "
            "The selector was not clicked."
        )
    plus_x, plus_y, _ = near[0]
    x, y = plus_x, plus_y - 32
    print(f"Existing-contact icon at ({x:.0f}, {y:.0f}), above + at ({plus_x:.0f}, {plus_y:.0f})", flush=True)
    pyautogui.click(x, y)
    time.sleep(0.7)


def _selector_open(app) -> bool:
    titles = " ".join(ax.title(window) for window in ax.windows(app))
    if "address" in titles.lower() or "select" in titles.lower():
        return True
    text = screen.visible_text()
    return "select the address" in text or "select address" in text


def _park_pointer() -> None:
    """Leave the pointer in the middle of the screen.

    A corner hides every window. The search field sits in the dialog's title
    bar, so clicking it drags Fakturama off the screen.
    """
    pyautogui.mouseUp()
    width, height = pyautogui.size()
    pyautogui.moveTo(width / 2, height / 2)


def _set_address_search(app, text: str) -> None:
    """Replace the address search text without clicking the dialog title bar.

    The dialog focuses that field when it opens. The whole query is pasted so
    typing cannot stop halfway if the pointer later moves.
    """
    import pyperclip

    _park_pointer()
    field = ui.dialog_search_field(app, "Select the address")
    pyperclip.copy(text)
    pyautogui.hotkey("command", "a")
    if text:
        pyautogui.hotkey("command", "v")
    else:
        pyautogui.press("delete")
    time.sleep(0.45)
    actual = "" if ax.value(field) is None else str(ax.value(field))
    if text and screen.norm(text) not in screen.norm(actual):
        raise GroundingError(
            f"Address search read back {actual!r}, expected {text!r}. "
            "The window was not moved."
        )
    if not text and actual.strip():
        raise GroundingError(
            f"Address search still shows {actual!r} after it was cleared. "
            "The window was not moved."
        )


def search_debtor(app, order: OrderData) -> None:
    """2.2 Search the company name and wait until the list stops changing."""
    if not _selector_open(app):
        raise GroundingError("Select the address did not open")
    _set_address_search(app, order.company)
    screen.capture("03-debtor-search", f"2.2 searched {order.company}")


def _row_matches(row_text: str, order: OrderData) -> bool:
    text = screen.norm(row_text)
    needed = [
        screen.norm(order.company),
        screen.norm(order.first_name),
        screen.norm(order.last_name),
        order.billing.zip_code,
        screen.norm(order.billing.city),
    ]
    return all(part in text for part in needed)


def _dialog_table_rows(app) -> list[dict]:
    """OCR the address dialog as a table. Column gaps are wider than a sentence."""
    import cv2
    import numpy as np
    import pytesseract
    from pytesseract import Output

    dialog = ax.window_titled(app, "Select the address")
    position = str(ax.attr(dialog, "AXPosition"))
    size = str(ax.attr(dialog, "AXSize"))
    import re
    left = float(re.search(r"x:\s*([\d.]+)", position).group(1))
    top = float(re.search(r"y:\s*([\d.]+)", position).group(1))
    width = float(re.search(r"w:\s*([\d.]+)", size).group(1))
    height = float(re.search(r"h:\s*([\d.]+)", size).group(1))
    shot, scale_x, scale_y = screen.geometry()
    array = np.array(shot.convert("RGB"))
    x0, y0 = int(left / scale_x), int(top / scale_y)
    x1, y1 = int((left + width) / scale_x), int((top + height) / scale_y)
    crop = array[y0:y1, x0:x1]
    big = cv2.resize(cv2.cvtColor(crop, cv2.COLOR_RGB2BGR), None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    data = pytesseract.image_to_data(big, config="--psm 6", output_type=Output.DICT)
    tokens = []
    for index, raw in enumerate(data["text"]):
        text = str(raw).strip()
        if not text:
            continue
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError):
            confidence = -1
        if confidence < 40:
            continue
        tokens.append({
            "text": text,
            "x": left + data["left"][index] / 2 * scale_x,
            "y": top + data["top"][index] / 2 * scale_y,
            "right": left + (data["left"][index] + data["width"][index]) / 2 * scale_x,
            "bottom": top + (data["top"][index] + data["height"][index]) / 2 * scale_y,
        })
    groups: dict[int, list] = {}
    for token in tokens:
        # Skip the title, the search box, and the Cancel / OK bar.
        if token["y"] < top + 70 or token["y"] > top + height - 55:
            continue
        groups.setdefault(round(token["y"] / 8), []).append(token)
    rows = []
    for group in groups.values():
        group.sort(key=lambda token: token["x"])
        rows.append({
            "text": " ".join(token["text"] for token in group),
            "x": min(token["x"] for token in group),
            "y": min(token["y"] for token in group),
            "right": max(token["right"] for token in group),
            "bottom": max(token["bottom"] for token in group),
            "tokens": group,
        })
    rows.sort(key=lambda row: row["y"])
    return rows


def _billing_on_order(order: OrderData) -> bool:
    """The invoice street is on the order. That is the address the working run accepted."""
    def seen() -> bool:
        text = screen.visible_text()
        street = screen.norm(order.billing.street)
        if street in text:
            return True
        return (
            _letters(order.billing.street)[:8] in _letters(text)
            and order.billing.street.split()[-1] in text
        )

    if seen():
        return True
    try:
        ensure_address_visible()
    except (GroundingError, ManualReview):
        return False
    return seen()


def _invoice_row_for_shared_id(rows: list[dict], order: OrderData) -> dict | None:
    """Two addresses under one customer number. The upper row is the invoice address.

    The list does not show the street, so the warehouse row looks the same.
    The working run used the upper row, and the order then showed Friedrichstrasse 88.
    """
    groups: dict[str, list] = {}
    for row in rows:
        number = _customer_number(row["text"])
        if number:
            groups.setdefault(number, []).append(row)
    billing_street = _letters(order.billing.street)[:8]
    delivery_street = _letters(order.delivery.street)[:8]
    company = screen.norm(order.company).split()[0]
    for group in groups.values():
        group = [row for row in group if company in screen.norm(row["text"])]
        if len(group) < 2:
            continue
        billing = [
            row for row in group
            if (
                order.billing.zip_code in screen.norm(row["text"])
                or billing_street in _letters(row["text"])
            )
            and delivery_street not in _letters(row["text"])
        ]
        if len(billing) == 1:
            return billing[0]
        group.sort(key=lambda row: row["y"])
        return group[0]
    return None


def _choose_address_row(rows: list[dict], order: OrderData) -> dict | None:
    """The invoice address, not the warehouse that shares the same city."""
    shared = _invoice_row_for_shared_id(rows, order)
    if shared is not None:
        return shared
    company = screen.norm(order.company).split()[0]
    city = screen.norm(order.billing.city)
    billing_street = _letters(order.billing.street)[:8]
    delivery_street = _letters(order.delivery.street)[:8]
    loose = [
        row for row in rows
        if company in screen.norm(row["text"]) and city in screen.norm(row["text"])
    ]
    def rank(row: dict) -> tuple:
        text = screen.norm(row["text"])
        letters = _letters(row["text"])
        return (
            "invoice" in text,
            order.billing.zip_code in text or billing_street in letters,
            "delivery" not in text and order.delivery.zip_code not in text and delivery_street not in letters,
            -row["y"],
        )
    if loose:
        loose.sort(key=rank, reverse=True)
        return loose[0]
    matched = [row for row in rows if _row_matches(row["text"], order)]
    if not matched:
        matched = [row for row in rows if _row_matches_visible(row["text"], order)]
    if not matched:
        return None
    matched.sort(key=rank, reverse=True)
    return matched[0]


def _read_address_rows(app) -> list[dict]:
    """Read the address table after the filter has had time to draw rows."""
    last: list[dict] = []
    for _ in range(5):
        last = _dialog_table_rows(app)
        if any(_row_readable(row["text"]) for row in last):
            return last
        time.sleep(0.4)
    return last


def try_select_existing(app, order: OrderData) -> bool:
    """2.3 Exact match on Company, First Name, Name, ZIP and City, or Cancel.

    Returns True when an existing Debtor was selected. Several address rows
    for one company: the first row is the main address.
    """
    rows = _read_address_rows(app)
    if not any(_row_readable(row["text"]) for row in rows):
        short = order.company.split()[0]
        print(f"Full company search had no row. Searching {short!r}.", flush=True)
        _set_address_search(app, short)
        rows = _read_address_rows(app)
    print("Address rows:", flush=True)
    for row in rows:
        print(f"  {row['text']}", flush=True)
    chosen = _choose_address_row(rows, order)
    if chosen is not None:
        first = screen.norm(order.first_name)
        named = [
            token for token in chosen["tokens"]
            if screen.norm(token["text"]) == first and token["x"] > 400
        ]
        body = [
            token for token in chosen["tokens"]
            if token["x"] > 450 and not token["text"].strip().isdigit()
        ]
        target = named[0] if named else (min(body, key=lambda token: token["x"]) if body else chosen)
        print(f"Clicking address row {target['text']!r} at {target['y']:.0f}", flush=True)
        pyautogui.click(
            (target["x"] + target["right"]) / 2,
            (target["y"] + target["bottom"]) / 2,
        )
        time.sleep(0.2)
        ui.click_dialog_button(app, "OK")
        print("Selected the exact existing Debtor", flush=True)
        return True
    # A blank filtered table OCRs as noise. Read the list with the search cleared
    # before deciding the company is absent.
    if not rows or not any(_row_readable(row["text"]) for row in rows):
        print("Search returned no readable row. Reading the full address list.", flush=True)
        _set_address_search(app, "")
        rows = _read_address_rows(app)
        print("Address rows:", flush=True)
        for row in rows:
            print(f"  {row['text']}", flush=True)
        chosen = _choose_address_row(rows, order)
        if chosen is not None:
            first = screen.norm(order.first_name)
            names = [
                token for row in rows for token in row["tokens"]
                if screen.norm(token["text"]) == first
            ]
            target = min(names, key=lambda token: token["y"]) if names else chosen
            pyautogui.click(
                (target["x"] + target["right"]) / 2,
                (target["y"] + target["bottom"]) / 2,
            )
            time.sleep(0.2)
            ui.click_dialog_button(app, "OK")
            print("Selected the exact existing Debtor", flush=True)
            return True
        if rows and not any(_row_readable(row["text"]) for row in rows) and _table_has_text(app):
            ui.click_dialog_button(app, "Cancel")
            time.sleep(0.4)
            raise ManualReview(
                "The address list could not be read. Stopped so a second Debtor is not created."
            )
    print("No exact Debtor row. Cancelling the selector.", flush=True)
    ui.click_dialog_button(app, "Cancel")
    time.sleep(0.4)
    return False


def _table_has_text(app) -> bool:
    """True when the address table body has ink, not only the Cancel and OK buttons."""
    import re
    if "select the address" not in screen.visible_text().lower():
        return False
    dialog = ax.window_titled(app, "Select the address")
    position = str(ax.attr(dialog, "AXPosition"))
    size = str(ax.attr(dialog, "AXSize"))
    left = float(re.search(r"x:\s*([\d.]+)", position).group(1))
    top = float(re.search(r"y:\s*([\d.]+)", position).group(1))
    width = float(re.search(r"w:\s*([\d.]+)", size).group(1))
    height = float(re.search(r"h:\s*([\d.]+)", size).group(1))
    shot, scale_x, scale_y = screen.geometry()
    array = np.array(shot.convert("RGB"))
    x0, y0 = int((left + 20) / scale_x), int((top + 80) / scale_y)
    x1, y1 = int((left + width - 20) / scale_x), int((top + height - 70) / scale_y)
    body = array[y0:y1, x0:x1]
    if body.size == 0:
        return False
    dark = np.any(body < 180, axis=2)
    return float(dark.mean()) > 0.008


def _row_readable(row_text: str) -> bool:
    """A real address row has a ZIP or at least two name words. OCR noise does not."""
    import re
    if re.search(r"\b\d{4,5}\b", row_text):
        return True
    words = [
        word for word in re.findall(r"[A-Za-z]{3,}", row_text)
        if word.casefold() not in {"cancel", "select", "address", "the"}
    ]
    return len(words) >= 2


def _row_matches_visible(row_text: str, order: OrderData) -> bool:
    """Match a row whose company cell is truncated.

    The ZIP column is often missing from OCR. First name, last name, city,
    and the first word of the company are enough when the search is already
    filtered to that company.
    """
    text = screen.norm(row_text)
    needed = [
        screen.norm(order.first_name),
        screen.norm(order.last_name),
        screen.norm(order.billing.city),
    ]
    if not all(part in text for part in needed):
        return False
    company = screen.norm(order.company)
    if company in text:
        return True
    return company.split()[0] in text


def re_zip_present(text: str) -> bool:
    import re
    return re.search(r"\b\d{4,5}\b", text) is not None


def confirm_addresses_on_order(order: OrderData) -> None:
    """2.4 / 2.13 The invoice address must be visible on the Order.

    Two addresses under one customer number: the order keeps the invoice
    address. The warehouse address stays on the debtor.
    """
    if not _billing_on_order(order):
        print(
            "Invoice street is not on the order. Selecting the invoice address "
            "for this customer number.",
            flush=True,
        )
        app = ax.activate()
        ax.show_tab(app, "New Order")
        click_existing_contact_icon()
        search_debtor(app, order)
        if not try_select_existing(app, order):
            raise ManualReview(
                f"Invoice address for {order.company!r} was not selected. Not continuing."
            )
    text = screen.visible_text()
    missing = []
    if not _billing_on_order(order):
        missing.append(order.billing.street)
    if screen.norm(order.company) not in text:
        missing.append(order.company)
    if missing:
        raise ManualReview(f"Order addresses missing {missing}. Not continuing.")
    if screen.norm(order.delivery.street) in text:
        print("Delivery street is also visible on the order", flush=True)
    print("Invoice address matches the source image", flush=True)
    screen.capture("08-debtor-on-order", "2.13 Debtor selected; billing address populated")


def open_new_debtor(app) -> None:
    """2.5 Keep the Order tab open and open New Debtor from the New menu."""
    if ax.tab_is_active(app, "New Debtor"):
        print("New Debtor already active", flush=True)
        return
    if "New Debtor" not in [name.lstrip("*") for name in ax.tab_titles(app)]:
        ui.click_menu(app, "New", "New Debtor")
        time.sleep(0.5)
    ax.show_tab(app, "New Debtor")
    if not any(name.lstrip("*") == "New Order" for name in ax.tab_titles(app)):
        raise ManualReview("The Order tab disappeared while opening the Debtor")
    print("New Debtor is active and the Order tab is still open", flush=True)


def _click_field_right_of(app, label: str, offset: int, region=None):
    row = screen.label_anchor(label, region=region)
    pyautogui.click(row["label_right"] + offset, (row["y"] + row["bottom"]) / 2)
    time.sleep(0.2)
    return ui._focused_editable(app, label)


def fill_identity(app, order: OrderData) -> None:
    """2.6 Leave the proposed Customer ID. Enter company and name. Salutation stays ---."""
    ui.require_tab(app, "New Debtor")
    element = ax.focused(app)
    if "next contact id" in ax.help_text(element).lower():
        customer_id = str(ax.value(element) or "")
        pyautogui.press("tab")
        time.sleep(0.2)
        pyautogui.press("tab")
        time.sleep(0.2)
        company = ax.focused(app)
        if ax.role(company) not in ("AXTextField", "AXTextArea"):
            raise GroundingError("Company field did not focus after the Customer ID")
        ax.set_value(company, order.company, "Company")
        if str(ax.value(element) or "") != customer_id:
            raise ManualReview(f"Customer ID changed from {customer_id!r}")
        print(f"  Customer ID preserved: {customer_id}", flush=True)
    else:
        ui.set_text_right_of(app, "Company", order.company, offset=70)

    row = screen.unique_line("first name", exact=False, region=_editor_region)
    if "last name" not in screen.norm(row["text"]) and "name" not in screen.norm(row["text"]):
        raise GroundingError("First Name / Last Name row not found")
    y = (row["y"] + row["bottom"]) / 2
    pyautogui.click(row["right"] + 60, y)
    time.sleep(0.15)
    first = ui._focused_editable(app, "First Name")
    position = str(ax.attr(first, "AXPosition"))
    size = str(ax.attr(first, "AXSize"))
    import re
    x_match = re.search(r"x:\s*([\d.]+)", position)
    w_match = re.search(r"w:\s*([\d.]+)", size)
    if not x_match or not w_match:
        raise GroundingError("Could not measure the First Name field")
    ax.set_value(first, order.first_name, "First Name")
    pyautogui.click(float(x_match.group(1)) + float(w_match.group(1)) + 45, y)
    time.sleep(0.15)
    last = ui._focused_editable(app, "Last Name")
    if str(last) == str(first):
        raise GroundingError("First Name and Last Name are the same control")
    ax.set_value(last, order.last_name, "Last Name")
    screen.capture("04-debtor-identity", "2.6 Company and contact name; Customer ID untouched")


def _zip_city_row() -> dict:
    """The ZIP - City label. OCR often keeps ZIP and City as two words."""
    for _ in range(2):
        for phrase in ("zip - city", "zip city"):
            try:
                return screen.unique_line(phrase, exact=False, region=_editor_region)
            except RuntimeError:
                pass
        words = screen.tokens()
        pairs = []
        for zip_token in words:
            if _letters(zip_token["text"]) != "zip" or not _editor_region(zip_token):
                continue
            cities = [
                token for token in words
                if _letters(token["text"]) == "city"
                and zip_token["right"] - 4 < token["x"] < zip_token["right"] + 90
                and abs(token["y"] - zip_token["y"]) < 18
            ]
            if len(cities) != 1:
                continue
            city = cities[0]
            pairs.append({
                "text": "ZIP - City",
                "x": zip_token["x"],
                "y": min(zip_token["y"], city["y"]),
                "right": city["right"],
                "bottom": max(zip_token["bottom"], city["bottom"]),
            })
        if pairs:
            # The address form that is open is the lower label when both are readable.
            return max(pairs, key=lambda row: row["y"])
        time.sleep(0.4)
    raise GroundingError("ZIP - City label was not found. Nothing was typed.")


def _zip_city(app, address: Address) -> None:
    row = _zip_city_row()
    y = (row["y"] + row["bottom"]) / 2
    pyautogui.click(row["right"] + 35, y)
    time.sleep(0.2)
    zip_field = ui._focused_editable(app, "ZIP")
    position = str(ax.attr(zip_field, "AXPosition"))
    size = str(ax.attr(zip_field, "AXSize"))
    import re
    x_match = re.search(r"x:\s*([\d.]+)", position)
    w_match = re.search(r"w:\s*([\d.]+)", size)
    if not x_match or not w_match:
        raise GroundingError("Could not measure the ZIP field")
    pyautogui.click(float(x_match.group(1)) + float(w_match.group(1)) + 55, y)
    time.sleep(0.15)
    city_field = ui._focused_editable(app, "City")
    if str(city_field) == str(zip_field):
        raise GroundingError("City field is not distinct from ZIP")
    ax.set_value(zip_field, address.zip_code, "ZIP")
    ax.set_value(city_field, address.city, "City")


def _country_row() -> dict:
    """The Country label on the open address form, not a terminal line."""
    _, screen_h = pyautogui.size()
    found = []
    for row in screen.lines():
        if row["x"] < 400 or row["y"] < 180 or row["y"] > screen_h * 0.82:
            continue
        text = screen.norm(row["text"])
        if "country:" in text or "already" in text:
            continue
        parts = [screen.norm(token["text"]) for token in row["tokens"]]
        if not parts or parts[0] != "country":
            continue
        label = row["tokens"][0]
        found.append({**row, "right": label["right"], "label_right": label["right"]})
    if not found:
        raise GroundingError("Country label was not found. Nothing was typed.")
    # The address form that is open is the lower label when both are readable.
    return max(found, key=lambda row: row["y"])


def _country_tokens(country: str) -> list[dict]:
    """Value tokens to the right of Country. They often sit a few pixels off the label line."""
    row = _country_row()
    wanted = screen.norm(country)
    return [
        token for token in screen.tokens()
        if token["x"] > row["label_right"] + 4
        and abs(token["y"] - row["y"]) < 22
        and wanted in screen.norm(token["text"])
    ]


def _column_limit(row: dict) -> float:
    """Mobile, Telefax and Telephone share a row with the field to their left."""
    limit = float(pyautogui.size().width - 20)
    blockers = {"mobile", "telefax", "fax", "telephone", "email", "e-mail"}
    for token in screen.tokens():
        name = screen.norm(token["text"])
        if name not in blockers and not name.startswith("2nd"):
            continue
        if token["x"] < row["label_right"] + 80:
            continue
        if abs(token["y"] - row["y"]) > 18:
            continue
        limit = min(limit, token["x"] - 12)
    return limit


def _combo_arrow(row: dict) -> tuple[float, float]:
    """Dropdown arrow of the combo on this label's row.

    The white area to the right of Country continues into Mobile. Only the
    first wide field before that label is the country combo.
    """
    shot, scale_x, scale_y = screen.geometry()
    array = np.array(shot.convert("RGB"))
    y = int(((row["y"] + row["bottom"]) / 2) / scale_y)
    start = int((row["label_right"] + 8) / scale_x)
    stop = int(_column_limit(row) / scale_x)
    white = np.all(array[y, start:stop] > 235, axis=1)
    run_start = None
    chosen = None
    for index, is_white in enumerate(list(white) + [False]):
        if is_white and run_start is None:
            run_start = index
        elif not is_white and run_start is not None:
            origin = (start + run_start) * scale_x
            width = (index - run_start) * scale_x
            if chosen is None and width > 80 and origin < row["label_right"] + 220:
                chosen = index
            run_start = None
    if chosen is None:
        raise GroundingError(
            "Country combo was not found before the Mobile column. Nothing was typed."
        )
    right = start + chosen
    return (right - 12) * scale_x, y * scale_y


def _type_into_open_list(country: str) -> None:
    """Type into the open country list. Select-all is not used; that replaces the city."""
    import subprocess

    time.sleep(1.0)
    safe = country.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(
        ["osascript", "-e", f'tell application "System Events" to keystroke "{safe}"'],
        check=True,
    )
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.45)


def _set_country(app, country: str) -> None:
    """Open the country dropdown, type the name, and press Enter.

    The pointer stays on the arrow. A sweep across the screen closes the list.
    Keystrokes go to the open list; if they change the city field, it is restored.
    """
    if _country_tokens(country):
        print(f"  Selected country already {country}", flush=True)
        return
    title = _debtor_editor_title(app)
    if not ax.tab_is_active(app, title):
        ax.show_tab(app, title)
    row = _country_row()
    x, y = _combo_arrow(row)
    width, height = pyautogui.size()
    if not (120 < x < width - 120 and 400 < y < height - 120):
        raise GroundingError(
            f"Country click ({x:.0f}, {y:.0f}) would leave the address form. Nothing was typed."
        )
    focused = ax.focused(app)
    previous = "" if ax.value(focused) is None else str(ax.value(focused))
    pyautogui.mouseUp()
    pyautogui.click(x, y)
    time.sleep(0.35)
    if not ax.tab_is_active(app, title):
        ax.show_tab(app, title)
        raise ManualReview("The country list switched the editor tab. Nothing was typed.")
    _type_into_open_list(country)
    focused = ax.focused(app)
    current = "" if ax.value(focused) is None else str(ax.value(focused))
    if previous and current != previous and screen.norm(country) not in screen.norm(current):
        ax.set_value(focused, previous, "City")
        raise ManualReview(
            f"Typing {country!r} changed {previous!r} to {current!r}. Restored it. Nothing saved."
        )
    if not _country_tokens(country):
        raise ManualReview(f"Country read back without {country!r}. Nothing saved.")
    print(f"  Selected country {country}", flush=True)


def _address_type_token() -> dict:
    words = screen.tokens()
    typed = [
        token for token in words
        if screen.norm(token["text"]) == "type" and _editor_region(token)
        and any(
            screen.norm(other["text"]) == "address"
            and abs(other["y"] - token["y"]) < 10
            and other["x"] < token["x"]
            for other in words
        )
    ]
    if len(typed) != 1:
        raise GroundingError(f"address type label matched {len(typed)} times")
    return typed[0]


def _role_visible(role_text: str) -> bool:
    """The role sits on the address-type row. Accessibility reads it back empty after Enter."""
    try:
        token = _address_type_token()
    except GroundingError:
        return False
    nearby = [
        screen.norm(other["text"])
        for other in screen.tokens()
        if other["x"] > token["right"] - 4
        and abs(other["y"] - token["y"]) < 28
    ]
    blob = " ".join(nearby)
    return all(word in blob for word in screen.norm(role_text).split())


def _set_address_role(app, country: str, role_text: str) -> None:
    """Paste the role into address type and press Enter.

    The field commits on Enter. The suggestion boxes are not clicked.
    """
    del country  # the role is not anchored to the country value
    import pyperclip
    if _role_visible(role_text):
        print(f"  Address role already {role_text}", flush=True)
        return
    token = _address_type_token()
    # The label click hits the composite around the field. The white text box is the control.
    anchor = {
        "text": "address type",
        "label_right": token["right"],
        "y": token["y"],
        "bottom": token["bottom"],
    }
    field_box = screen.white_field_on_row(anchor)
    click_x = field_box["x"] + 36
    click_y = (field_box["y"] + field_box["bottom"]) / 2
    pyautogui.mouseUp()
    pyautogui.click(click_x, click_y)
    time.sleep(0.2)
    element = ax.focused(app)
    if ax.role(element) not in ("AXTextField", "AXTextArea", "AXComboBox"):
        pyautogui.click(click_x + 50, click_y)
        time.sleep(0.2)
        element = ax.focused(app)
    if ax.role(element) not in ("AXTextField", "AXTextArea", "AXComboBox"):
        raise GroundingError(
            "address type: click did not land in the text field. "
            "The suggestion boxes were not clicked."
        )
    pyperclip.copy(role_text)
    pyautogui.hotkey("command", "a")
    pyautogui.hotkey("command", "v")
    time.sleep(0.6)
    # Enter accepts the address type. The suggestion checkboxes are not clicked.
    # Clicking Street clears the type, so the field is left after Enter.
    pyautogui.press("enter")
    time.sleep(0.5)
    if not _role_visible(role_text):
        pyautogui.press("enter")
        time.sleep(0.4)
    if not _role_visible(role_text):
        raise ManualReview(f"Address role read back '', expected {role_text!r}")
    print(f"  Address role: {role_text}", flush=True)


def _street_anchor() -> dict:
    """Street label on the address form that is open.

    A content-assist icon can turn the word into 'stree', and the same label
    is sometimes read twice. Two copies on one row are one field.
    """
    last_count = 0
    for _ in range(2):
        try:
            return screen.label_anchor("Street", region=_editor_region)
        except RuntimeError:
            pass
        hits = [
            token for token in screen.tokens()
            if _letters(token["text"]).startswith("stree")
            and token["x"] < 900
            and _editor_region(token)
        ]
        last_count = len(hits)
        unique = []
        for token in sorted(hits, key=lambda item: (item["y"], item["x"])):
            if any(abs(token["y"] - kept["y"]) < 22 and abs(token["x"] - kept["x"]) < 120 for kept in unique):
                continue
            unique.append(token)
        if unique:
            # The open address form is the lower Street when both tabs are readable.
            token = unique[-1]
            return {**token, "label_right": token["right"]}
        time.sleep(0.4)
    raise GroundingError(f"Street label matched {last_count}. Nothing was typed.")


def _set_street(app, text: str) -> None:
    row = _street_anchor()
    pyautogui.click(row["label_right"] + 55, (row["y"] + row["bottom"]) / 2)
    time.sleep(0.2)
    element = ui._focused_editable(app, "Street")
    ax.set_value(element, text, "Street")
    print(f"  Street: {text!r}", flush=True)


def _show_main_address_tab() -> None:
    screen.click_line(_main_address_tab())
    time.sleep(0.35)


def _additional_address_tab() -> dict | None:
    """The extra address tab on the same bar as Main address.

    The form label "additional name" also contains that word and must not count.
    """
    tokens = screen.tokens()
    mains = [
        token for token in tokens
        if screen.norm(token["text"]) == "main"
        and token["x"] > 400
        and 360 < token["y"] < 750
    ]
    if len(mains) != 1:
        return None
    main = mains[0]
    hits = [
        token for token in tokens
        if "ditional" in _letters(token["text"])
        and token["x"] > main["right"]
        and abs(token["y"] - main["y"]) < 18
    ]
    if len(hits) > 1:
        raise GroundingError(
            f"Additional address tab matched {len(hits)}. No address was changed."
        )
    return hits[0] if hits else None


def fill_main_address(app, order: OrderData) -> None:
    """2.7 and 2.8. Delivery role is added here only when the addresses match."""
    open_section("Addresses")
    _show_main_address_tab()
    billing = order.billing
    _set_street(app, billing.street)
    for label, text, offset in (
        ("E-Mail", order.email, 70),
        ("Telephone", order.telephone, 70),
    ):
        ui.set_text_right_of(app, label, text, offset=offset)
    _zip_city(app, billing)
    _set_country(app, billing.country)
    if order.delivery_same_as_billing:
        _set_address_role(app, billing.country, "Invoice address,Delivery address")
    else:
        _set_address_role(app, billing.country, "Invoice address")
    screen.capture("05-main-address", "2.7-2.8 Main address with Invoice role")


def _main_address_tab() -> dict:
    """The Main address tab. OCR often splits Main and address onto adjacent lines."""
    tokens = screen.tokens()
    found = []
    for main in tokens:
        if screen.norm(main["text"]) != "main" or main["x"] < 400 or not 360 < main["y"] < 750:
            continue
        neighbors = [
            token for token in tokens
            if screen.norm(token["text"]) == "address"
            and abs(token["y"] - main["y"]) < 16
            and main["x"] - 30 < token["x"] < main["right"] + 90
        ]
        if len(neighbors) == 1:
            found.append((main, neighbors[0]))
    if len(found) != 1:
        raise GroundingError(
            f"Main address tab matched {len(found)}. No second address was created."
        )
    main, address = found[0]
    return {
        "x": main["x"],
        "y": min(main["y"], address["y"]),
        "right": max(main["right"], address["right"]),
        "bottom": max(main["bottom"], address["bottom"]),
        "label_right": max(main["right"], address["right"]),
    }


def _add_address_plus(array, scale_x, scale_y, tab, screen_width) -> tuple[float, float]:
    """The plus is the small dark glyph at the right end of the Main address tab.

    It sits in a light button a few dozen points from the screen edge. A search
    that stops 70 points short cuts through the glyph, and a fixed start at
    x=1500 misses it when the editor is further left.
    """
    y = (tab["y"] + tab["bottom"]) / 2
    y0 = max(0, int((y - 22) / scale_y))
    y1 = min(array.shape[0], int((y + 26) / scale_y))
    x0 = max(0, int((tab["label_right"] + 24) / scale_x))
    x1 = min(array.shape[1], max(x0 + 1, int((screen_width - 8) / scale_x)))
    if y1 <= y0 or x1 <= x0:
        raise ManualReview(
            "Add-address '+' was not found on the Main address tab. "
            "No second address was created."
        )
    gray = array[y0:y1, x0:x1].mean(axis=2)
    columns = (gray < 80).any(axis=0)
    runs = []
    run_start = None
    for index, is_dark in enumerate(columns):
        if is_dark and run_start is None:
            run_start = index
        elif not is_dark and run_start is not None:
            width = (index - run_start) * scale_x
            if 2.5 <= width <= 16:
                runs.append((run_start, index))
            run_start = None
    if run_start is not None:
        width = (len(columns) - run_start) * scale_x
        if 2.5 <= width <= 16:
            runs.append((run_start, len(columns)))
    if not runs:
        raise ManualReview(
            "Add-address '+' was not found on the Main address tab. "
            "No second address was created."
        )
    left, right = runs[-1]
    click_x = (x0 + (left + right) / 2) * scale_x
    return click_x, y


def _click_add_address() -> None:
    """The '+' sits at the right end of the Main address tab. It is not in the AX tree."""
    tab = _main_address_tab()
    shot, scale_x, scale_y = screen.geometry()
    array = np.array(shot.convert("RGB"))
    click_x, y = _add_address_plus(array, scale_x, scale_y, tab, pyautogui.size().width)
    pyautogui.mouseUp()
    pyautogui.click(click_x, y)
    time.sleep(0.5)


def _additional_name_row() -> dict:
    """The additional-name label on the open address form, not the address tab."""
    tokens = screen.tokens()
    tab_ys = [
        token["y"] for token in tokens
        if screen.norm(token["text"]) == "main" and token["x"] > 400 and 360 < token["y"] < 750
    ]
    pairs = []
    for token in tokens:
        letters = _letters(token["text"])
        if "ditional" not in letters or not _editor_region(token):
            continue
        if tab_ys and abs(token["y"] - tab_ys[0]) < 18 and token["x"] > 500:
            continue
        if letters.startswith("additionalname"):
            pairs.append({
                "text": "additional name",
                "x": token["x"],
                "y": token["y"],
                "right": token["right"],
                "bottom": token["bottom"],
                "label_right": token["right"],
            })
            continue
        names = [
            other for other in tokens
            if _letters(other["text"]) == "name"
            and token["right"] - 4 < other["x"] < token["right"] + 90
            and abs(other["y"] - token["y"]) < 16
        ]
        if len(names) != 1:
            continue
        name = names[0]
        pairs.append({
            "text": "additional name",
            "x": token["x"],
            "y": min(token["y"], name["y"]),
            "right": name["right"],
            "bottom": max(token["bottom"], name["bottom"]),
            "label_right": name["right"],
        })
    if len(pairs) != 1:
        raise GroundingError(
            f"additional name label matched {len(pairs)}. The street was not typed."
        )
    return pairs[0]


def _write_delivery_street(app, delivery: Address) -> None:
    """Street is the row under additional name. The warehouse name stays in the upper field."""
    row = _additional_name_row()
    y = (row["y"] + row["bottom"]) / 2
    pyautogui.mouseUp()
    pyautogui.click(row["label_right"] + 70, y)
    time.sleep(0.2)
    name_field = ui._focused_editable(app, "additional name")
    box = ui._control_box(name_field)
    if box is None:
        raise GroundingError("Could not measure additional name. Nothing was typed.")
    name_x, name_y, _name_w, name_h = box
    width, height = pyautogui.size()
    click_x = name_x + 36
    street_field = None
    for extra in (14, 22, 30):
        click_y = name_y + name_h + extra
        if not (120 < click_x < width - 120 and 400 < click_y < height - 120):
            continue
        pyautogui.click(click_x, click_y)
        time.sleep(0.2)
        element = ax.focused(app)
        if str(element) == str(name_field):
            continue
        if ax.role(element) not in ("AXTextField", "AXTextArea", "AXComboBox"):
            continue
        focused = ui._control_box(element)
        if focused is None or focused[1] < name_y + name_h * 0.5:
            continue
        street_field = element
        break
    if street_field is None:
        raise GroundingError("Street click stayed on additional name. Nothing was typed.")
    ax.set_value(street_field, delivery.street, "Street")
    print(f"  Street: {delivery.street!r}", flush=True)
    if not delivery.company:
        return
    pyautogui.click(name_x + 36, name_y + max(name_h, 1) / 2)
    time.sleep(0.15)
    focused_name = ui._focused_editable(app, "additional name")
    if str(focused_name) == str(street_field):
        raise GroundingError("additional name click landed on Street. The company was not typed.")
    ax.set_value(focused_name, delivery.company, "additional name")
    print(f"  additional name: {delivery.company!r}", flush=True)


def add_delivery_address(app, order: OrderData) -> None:
    """A second address, only when delivery differs from billing."""
    if order.delivery_same_as_billing:
        print("Billing and delivery match; no second address", flush=True)
        return
    existing = _additional_address_tab()
    if existing is None:
        _click_add_address()
    else:
        screen.click_line(existing)
        time.sleep(0.35)
        print("Using the additional address tab already open", flush=True)
    delivery = order.delivery
    _write_delivery_street(app, delivery)
    _zip_city(app, delivery)
    _set_country(app, delivery.country)
    _set_address_role(app, delivery.country, "Delivery address")
    screen.capture("06-delivery-address", "2.8 Delivery address on its own address")


def _address_form_visible() -> bool:
    """Street or ZIP on the editor means the Addresses section is already open."""
    return any(
        token["x"] > 400
        and token["y"] > 180
        and (_letters(token["text"]).startswith("stree") or _letters(token["text"]) == "zip")
        for token in screen.tokens()
    )


def open_section(name: str) -> None:
    """Click Addresses or Miscellaneous inside the editor, not the left navigator."""
    if screen.norm(name) == "addresses" and _address_form_visible():
        print("Addresses section already open", flush=True)
        return
    wanted = screen.norm(name)
    hits = []
    for _ in range(2):
        hits = []
        for token in screen.tokens():
            if token["y"] > 560 or token["x"] < 400:
                continue
            text = screen.norm(token["text"])
            letters = _letters(token["text"])
            if wanted == "addresses":
                if letters.startswith("address") and "type" not in text and "spec" not in letters:
                    hits.append(token)
            elif text == wanted:
                hits.append(token)
        if len(hits) == 1:
            break
        time.sleep(0.4)
    if len(hits) != 1:
        raise GroundingError(f"Editor tab {name!r} matched {len(hits)}")
    screen.click_line(hits[0])
    time.sleep(0.45)
    if screen.norm(name) == "miscellaneous" and "alias" not in screen.visible_text():
        raise GroundingError("Miscellaneous did not open")
    print(f"Opened section {name}", flush=True)


def _alias_anchor() -> dict:
    """The Alias name label. OCR often keeps Alias and name as two words."""
    for _ in range(2):
        try:
            return screen.label_anchor("Alias name", region=_editor_region)
        except RuntimeError:
            pass
        words = screen.tokens()
        pairs = []
        for alias in words:
            if not _editor_region(alias):
                continue
            letters = _letters(alias["text"])
            if letters.startswith("aliasname"):
                pairs.append({
                    "text": "Alias name",
                    "x": alias["x"],
                    "y": alias["y"],
                    "right": alias["right"],
                    "bottom": alias["bottom"],
                    "label_right": alias["right"],
                })
                continue
            if letters != "alias":
                continue
            names = [
                token for token in words
                if _letters(token["text"]) == "name"
                and alias["right"] - 4 < token["x"] < alias["right"] + 90
                and abs(token["y"] - alias["y"]) < 18
            ]
            if len(names) != 1:
                continue
            name = names[0]
            pairs.append({
                "text": "Alias name",
                "x": alias["x"],
                "y": min(alias["y"], name["y"]),
                "right": name["right"],
                "bottom": max(alias["bottom"], name["bottom"]),
                "label_right": name["right"],
            })
        if len(pairs) == 1:
            return pairs[0]
        time.sleep(0.4)
    raise GroundingError("Alias name label was not found. Nothing was typed.")


def _net_gross_anchor() -> dict:
    """The Net or Gross label. OCR often keeps the three words apart."""
    for _ in range(2):
        try:
            return screen.label_anchor("Net or Gross", region=_editor_region)
        except RuntimeError:
            pass
        words = screen.tokens()
        pairs = []
        for net in words:
            if _letters(net["text"]) != "net" or not _editor_region(net):
                continue
            ors = [
                token for token in words
                if _letters(token["text"]) == "or"
                and net["right"] - 4 < token["x"] < net["right"] + 50
                and abs(token["y"] - net["y"]) < 16
            ]
            if len(ors) != 1:
                continue
            grosses = [
                token for token in words
                if _letters(token["text"]) == "gross"
                and ors[0]["right"] - 4 < token["x"] < ors[0]["right"] + 80
                and abs(token["y"] - ors[0]["y"]) < 16
            ]
            if len(grosses) != 1:
                continue
            gross = grosses[0]
            pairs.append({
                "text": "Net or Gross",
                "x": net["x"],
                "y": min(net["y"], gross["y"]),
                "right": gross["right"],
                "bottom": max(net["bottom"], gross["bottom"]),
                "label_right": gross["right"],
            })
        if len(pairs) == 1:
            return pairs[0]
        time.sleep(0.4)
    raise GroundingError("Net or Gross label was not found. Nothing was chosen.")


def _net_is_selected(row: dict) -> bool:
    values = [
        token for token in screen.tokens()
        if token["x"] > row["label_right"] + 4
        and token["x"] - row["label_right"] < 220
        and abs(token["y"] - row["y"]) < 16
        and _letters(token["text"]) == "net"
    ]
    return len(values) == 1


def _set_net_or_gross() -> None:
    """Select Net. One Down from the default '---' is that choice."""
    row = _net_gross_anchor()
    if _net_is_selected(row):
        print("  Net or Gross already Net", flush=True)
        return
    y = (row["y"] + row["bottom"]) / 2
    try:
        field = screen.white_field_on_row(row)
        pyautogui.click(field["right"] - 12, y)
    except RuntimeError:
        pyautogui.click(row["label_right"] + 90, y)
    time.sleep(0.2)
    pyautogui.press("down")
    time.sleep(0.15)
    pyautogui.press("enter")
    time.sleep(0.4)
    row = _net_gross_anchor()
    if not _net_is_selected(row):
        raise ManualReview("Net or Gross did not read back Net. Nothing saved.")
    print("  Net or Gross: Net", flush=True)


def fill_miscellaneous(app, order: OrderData) -> None:
    """2.9 Alias, Discount 0%, Net or Gross = Net."""
    open_section("Miscellaneous")
    row = _alias_anchor()
    nearby = " ".join(
        token["text"] for token in screen.tokens()
        if token["x"] > row["label_right"]
        and token["x"] - row["label_right"] < 280
        and abs(token["y"] - row["y"]) < 16
    )
    if screen.norm(order.alias) in screen.norm(nearby):
        print(f"  Alias name already {order.alias}", flush=True)
    else:
        pyautogui.click(row["label_right"] + 75, (row["y"] + row["bottom"]) / 2)
        time.sleep(0.2)
        element = ui._focused_editable(app, "Alias name")
        ax.set_value(element, order.alias, "Alias name")
        pyautogui.press("enter")
        time.sleep(0.3)
        print(f"  Alias name: {order.alias!r}", flush=True)
    discount = _click_field_right_of(app, "Discount", 60, region=_editor_region)
    current = str(ax.value(discount) or "").strip()
    if current not in ("0%", "0", "0.0%", "0.00%", "0.0", "0.00"):
        ax.set_value(discount, "0%", "Discount")
        current = str(ax.value(discount) or "").strip()
    if current not in ("0%", "0", "0.0%", "0.00%", "0.0", "0.00"):
        raise ManualReview(f"Discount is {current!r}, not 0%")
    print("  Discount: 0%", flush=True)
    _set_net_or_gross()
    screen.capture("07-miscellaneous", "2.9 Alias, 0% discount, Net")


def _debtor_editor_title(app) -> str:
    """The editor is 'New Debtor' until the first save, then 'Company, First Last'."""
    for raw in ax.tab_titles(app):
        title = raw.lstrip("*")
        if title == "New Debtor" or ", " in title:
            return title
    raise GroundingError(f"No Debtor editor is open. Tabs: {ax.tab_titles(app)}")


def _payment_row() -> dict:
    """The Payment label on the debtor form, not a terminal line that starts with that word."""
    _, screen_h = pyautogui.size()
    found = []
    for row in screen.lines():
        if row["x"] < 400 or row["y"] < 180 or row["y"] > screen_h * 0.82:
            continue
        text = screen.norm(row["text"])
        if "reopening" in text or text.startswith("payment list"):
            continue
        parts = [screen.norm(token["text"]) for token in row["tokens"]]
        if not parts or parts[0] != "payment":
            continue
        label = row["tokens"][0]
        found.append({**row, "right": label["right"], "label_right": label["right"]})
    if len(found) != 1:
        sample = [row["text"] for row in found[:6]]
        raise GroundingError(f"Payment label matched {len(found)}: {sample}")
    return found[0]


def _payment_already_bank(row: dict) -> bool:
    return any(
        "bank" in screen.norm(token["text"])
        and token["x"] > row["label_right"]
        and abs(token["y"] - row["y"]) < 16
        for token in screen.tokens()
    )


def _bank_choices(row: dict) -> list[dict]:
    """Bank Transfer in the open list under Payment. The terminal is not that list."""
    _, screen_h = pyautogui.size()
    hits = []
    for token in screen.tokens():
        text = screen.norm(token["text"])
        if "bank" not in text or "reopening" in text or "no bank" in text:
            continue
        if token["y"] > screen_h * 0.82 or token["x"] < row["label_right"] - 30:
            continue
        if token["x"] > row["label_right"] + 420:
            continue
        if not row["y"] - 10 < token["y"] < row["y"] + 280:
            continue
        if abs(token["y"] - row["y"]) < 14 and token["x"] > row["label_right"]:
            continue
        hits.append(token)
    hits.sort(key=lambda token: (token["y"], token["x"]))
    return hits


def _type_bank_transfer() -> None:
    """Type into the Payment combo. Wait so a notification does not take the keys."""
    import subprocess

    time.sleep(1.0)
    pyautogui.hotkey("command", "a")
    time.sleep(0.12)
    subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to keystroke "Bank Transfer"'],
        check=True,
    )
    time.sleep(0.4)
    pyautogui.press("enter")
    time.sleep(0.45)


def _choose_bank(app, order: OrderData) -> bool:
    """Open Payment, click Bank Transfer, or type it and press Enter."""
    row = _payment_row()
    if _payment_already_bank(row):
        print(f"  Payment already {order.payment_method}", flush=True)
        return True
    values = [
        token for token in screen.tokens()
        if token["x"] > row["label_right"]
        and token["x"] < row["label_right"] + 280
        and abs(token["y"] - row["y"]) < 18
    ]
    values.sort(key=lambda token: token["x"])
    if values:
        pyautogui.click(
            (values[0]["x"] + values[0]["right"]) / 2,
            (values[0]["y"] + values[0]["bottom"]) / 2,
        )
    else:
        pyautogui.click(row["label_right"] + 70, (row["y"] + row["bottom"]) / 2)
    time.sleep(1.0)
    choices = _bank_choices(row)
    if len(choices) == 1:
        screen.click_line(choices[0])
        time.sleep(0.4)
    elif len(choices) > 1:
        screen.click_line(choices[0])
        time.sleep(0.4)
    else:
        element = ax.focused(app)
        current = str(ax.value(element) or "")
        if ax.role(element) not in ("AXTextField", "AXTextArea", "AXComboBox"):
            return False
        if current.strip() in {"0%", "0", "0.0", "0.00", "0.0%", "0.00%"}:
            return False
        _type_bank_transfer()
    if not _payment_already_bank(_payment_row()):
        return False
    print(f"  Payment: {order.payment_method}", flush=True)
    return True


def _customer_number(text: str) -> str:
    """CUST plus its digits. A zero in that number is often read as the letter O."""
    raw = "".join(str(text).upper().split())
    if "CUST" not in raw:
        return ""
    rest = raw[raw.index("CUST") + 4 :]
    if not any(ch.isdigit() for ch in rest):
        return ""
    rest = rest.replace("O", "0").replace("I", "1").replace("L", "1")
    digits = "".join(ch for ch in rest if ch.isdigit())
    if len(digits) < 4:
        return ""
    return "CUST" + digits


def _customer_id_on_editor() -> str:
    """The CUST number on the editor. The word Customer is not that number."""
    hits = [
        token for token in screen.tokens()
        if _customer_number(token["text"])
        and token["x"] > 400
        and 180 < token["y"] < 430
    ]
    if not hits:
        raise GroundingError("Customer ID was not read. The Debtor was not closed.")
    kept = []
    for token in hits:
        text = token["text"].upper()
        if any(
            text != other["text"].upper() and text in other["text"].upper()
            for other in hits
        ):
            continue
        kept.append(token)
    top = min(kept, key=lambda token: token["y"])
    values = []
    for token in kept:
        if abs(token["y"] - top["y"]) >= 14:
            continue
        number = _customer_number(token["text"])
        if number not in values:
            values.append(number)
    if len(values) != 1:
        raise GroundingError(
            f"Customer ID matched {values}. The Debtor was not closed."
        )
    return values[0]


def _wait_for_debtor_editor(app, seconds: float = 5.0) -> str | None:
    """The reopened editor appears a moment after the list row is opened."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            return _debtor_editor_title(app)
        except GroundingError:
            time.sleep(0.4)
    return None


def _reload_debtor(app) -> None:
    """Save, close, and open the same Debtor so Payment reloads its terms."""
    customer_id = _customer_id_on_editor()
    before = {name.lstrip("*") for name in ax.tab_titles(app)}
    ui.save_once(app, "Debtor")
    time.sleep(0.4)
    opened = [name.lstrip("*") for name in ax.tab_titles(app) if name.lstrip("*") not in before]
    title = opened[0] if len(opened) == 1 else _debtor_editor_title(app)
    ax.show_tab(app, title)
    pyautogui.hotkey("command", "w")
    time.sleep(1.0)
    if title in [name.lstrip("*") for name in ax.tab_titles(app)]:
        raise GroundingError("The Debtor editor stayed open, so its payment list was not reloaded.")
    time.sleep(1.0)
    ui.open_list_via_data_menu(app, "Debtors")
    time.sleep(1.2)
    field = ui.search_field_right_of(app, "Search", x_min_ratio=0.55)
    ui.type_search(app, field, customer_id)
    box = ui._control_box(field)
    search_bottom = box[1] + box[3] if box else 0
    hits = []
    for _ in range(5):
        time.sleep(0.45)
        wanted = _customer_number(customer_id)
        seen = [
            token for token in screen.tokens()
            if _customer_number(token["text"]) == wanted
            and token["y"] > search_bottom + 8
        ]
        hits = []
        for token in seen:
            if any(abs(token["y"] - kept["y"]) < 16 for kept in hits):
                continue
            hits.append(token)
        if len(hits) == 1:
            break
    if len(hits) != 1:
        raise ManualReview(
            f"Debtor {customer_id} matched {len(hits)} rows. It was not reopened."
        )
    pyautogui.doubleClick((hits[0]["x"] + hits[0]["right"]) / 2, (hits[0]["y"] + hits[0]["bottom"]) / 2)
    title = _wait_for_debtor_editor(app)
    if title is None:
        pyautogui.press("enter")
        title = _wait_for_debtor_editor(app, 4.0)
    if title is None:
        raise GroundingError(
            f"Debtor {customer_id} did not open. Tabs: {ax.tab_titles(app)}"
        )
    ax.show_tab(app, title)
    time.sleep(0.8)
    open_section("Miscellaneous")
    time.sleep(0.8)
    print(f"Reopened Debtor {customer_id}", flush=True)


def select_payment_method(app, order: OrderData) -> None:
    """2.10 The Payment combo lives on Miscellaneous in this Fakturama version.

    The list is filled when the Debtor editor opens. A term created after that
    is missing until this debtor is saved, closed, and opened again.
    """
    if "alias" not in screen.visible_text():
        open_section("Miscellaneous")
    if not _choose_bank(app, order):
        print("No Bank row under Payment. Reopening the Debtor.", flush=True)
        _reload_debtor(app)
        if not _choose_bank(app, order):
            raise ManualReview(
                f"Payment option {order.payment_method!r} matched 0 rows. Nothing was chosen."
            )
    screen.capture("07b-debtor-payment", f"2.10 Payment {order.payment_method}")


def save_debtor(app) -> None:
    """2.11"""
    ax.show_tab(app, _debtor_editor_title(app))
    ui.save_once(app, "Debtor")
    screen.capture("07c-debtor-saved", "2.11 Debtor saved once")


def reselect_on_order(app, order: OrderData) -> None:
    """2.12-2.13 Return to the Order and select the Debtor that was just saved."""
    ax.show_tab(app, "New Order")
    click_existing_contact_icon()
    search_debtor(app, order)
    if not try_select_existing(app, order):
        raise ManualReview(
            f"Saved Debtor {order.company!r} did not appear as an exact row. "
            "Stopped for manual review."
        )
    confirm_addresses_on_order(order)
