"""Steps 3.1-3.17: select or create each product, then complete the order line."""

from __future__ import annotations

import re
import time
from decimal import Decimal

import pyautogui

from fakturama_auto import ax, screen, ui
from fakturama_auto.errors import GroundingError, ManualReview
from fakturama_auto.models import Item, OrderData, money
from fakturama_auto.steps import vat as vat_step


def _selector_above_plus(plus_x: float, plus_y: float) -> tuple[float, float]:
    """Center of the document icon stacked above the green +.

    A fixed offset lands on the column header. The red delete icon is below the plus.
    """
    import cv2
    import numpy as np

    shot, scale_x, scale_y = screen.geometry()
    array = np.array(shot.convert("RGB"))
    px = int(plus_x / scale_x)
    py = int(plus_y / scale_y)
    x0 = max(0, px - int(16 / scale_x))
    x1 = min(array.shape[1], px + int(16 / scale_x))
    y_top = max(0, py - int(64 / scale_y))
    y_bot = max(0, py - int(8 / scale_y))
    column = array[y_top:y_bot, x0:x1]
    if column.size == 0:
        return plus_x, plus_y - 24
    gray = cv2.cvtColor(column, cv2.COLOR_RGB2GRAY)
    row_has = (gray < 185).mean(axis=1) > 0.15
    min_height = int(8 / scale_y)
    bands: list[tuple[int, int]] = []
    start = None
    for index, flag in enumerate(row_has):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            if index - start > min_height:
                bands.append((start, index - 1))
            start = None
    if start is not None and len(row_has) - start > min_height:
        bands.append((start, len(row_has) - 1))
    if not bands:
        return plus_x, plus_y - 24
    top, bottom = bands[-1]
    return plus_x, (y_top + (top + bottom) / 2) * scale_y


def _product_dialog_open(app) -> bool:
    for window in ax.windows(app):
        if "product" in ax.title(window).lower():
            return True
        for sheet in ax.attr(window, "AXSheets") or []:
            if "product" in ax.title(sheet).lower():
                return True
    return False


def click_product_selector() -> None:
    """3.2 The document icon above the green + beside Items. Not the green + or the red x."""
    items = screen.line_starting("Items")
    pluses = screen.green_plus_buttons()
    near = [
        plus for plus in pluses
        if abs(plus[0] - items["x"]) < 80 and 8 < plus[1] - items["bottom"] < 90
    ]
    if len(near) != 1:
        raise ManualReview(
            f"Product green + matched {len(near)} times, so the selector was not clicked."
        )
    plus_x, plus_y, _ = near[0]
    click_x, click_y = _selector_above_plus(plus_x, plus_y)
    print(f"Product selector at ({click_x:.0f}, {click_y:.0f})", flush=True)
    pyautogui.click(click_x, click_y)
    app = ax.activate()
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if _product_dialog_open(app):
            return
        time.sleep(0.25)
    if "select a product" in screen.visible_text():
        return
    raise GroundingError("Select a product did not open. The green + was not used.")


def _dialog_product_rows(app) -> list[dict]:
    """OCR the product dialog. Item numbers are often truncated with an ellipsis."""
    import re
    import cv2
    import numpy as np
    import pytesseract
    from pytesseract import Output

    dialog = ax.window_titled(app, "Select a product")
    position = str(ax.attr(dialog, "AXPosition"))
    size = str(ax.attr(dialog, "AXSize"))
    left = float(re.search(r"x:\s*([\d.]+)", position).group(1))
    top = float(re.search(r"y:\s*([\d.]+)", position).group(1))
    width = float(re.search(r"w:\s*([\d.]+)", size).group(1))
    height = float(re.search(r"h:\s*([\d.]+)", size).group(1))
    shot, scale_x, scale_y = screen.geometry()
    array = np.array(shot.convert("RGB"))
    crop = array[int(top / scale_y): int((top + height) / scale_y), int(left / scale_x): int((left + width) / scale_x)]
    big = cv2.resize(cv2.cvtColor(crop, cv2.COLOR_RGB2BGR), None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    data = pytesseract.image_to_data(big, config="--psm 6", output_type=Output.DICT)
    groups: dict[int, list] = {}
    for index, raw in enumerate(data["text"]):
        text = str(raw).strip()
        if not text:
            continue
        token = {
            "text": text,
            "x": left + data["left"][index] / 2 * scale_x,
            "y": top + data["top"][index] / 2 * scale_y,
            "right": left + (data["left"][index] + data["width"][index]) / 2 * scale_x,
            "bottom": top + (data["top"][index] + data["height"][index]) / 2 * scale_y,
        }
        if token["y"] < top + 55:
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
        })
    return rows


def _selector_rows(sku: str) -> list[dict]:
    return [row for row in screen.lines() if sku.lower() in screen.norm(row["text"])]


def _sku_prefix(sku: str) -> str:
    """The part of an item number that stays visible when the cell is truncated."""
    parts = sku.split("-")
    if len(parts) >= 2:
        return parts[0] + "-" + parts[1][:3]
    return sku


def _product_dialog_open(app) -> bool:
    return any("product" in ax.title(window).lower() for window in ax.windows(app))


def _type_product_search(app, sku: str) -> bool:
    """Type the SKU into the product search. Returns True if the dialog stayed open.

    Accessibility writes and synthesized key presses hit OK and insert the
    highlighted row. A real keystroke into the search field filters the list,
    and a unique match closes the dialog and places that product on the order.
    """
    import subprocess

    field = ui.dialog_search_field(app, "Select a product")
    box = ui._control_box(field)
    if not box:
        raise GroundingError("Product search field has no position")
    pyautogui.click(box[0] + box[2] / 2, box[1] + box[3] / 2)
    time.sleep(0.2)
    safe = sku.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(
        ["osascript", "-e", f'tell application "System Events" to keystroke "{safe}"'],
        check=True,
    )
    time.sleep(0.55)
    return _product_dialog_open(app)


def try_select_product(app, item: Item) -> bool:
    """3.3 Search the SKU. One exact row is selected. None means create it."""
    stayed_open = _type_product_search(app, item.sku)
    if not stayed_open:
        print(f"Selected product {item.sku}", flush=True)
        return True
    field = ui.dialog_search_field(app, "Select a product")
    ui.wait_until_stable()
    box = ui._control_box(field)
    floor = (box[1] + box[3] + 8) if box else 220
    rows = _dialog_product_rows(app)
    prefix = _sku_prefix(item.sku)
    rows = [
        row for row in rows
        if row["y"] > floor and (
            item.sku.lower() in screen.norm(row["text"])
            or prefix.lower() in screen.norm(row["text"])
        )
    ]
    screen.capture(f"prod-search-{item.sku}", f"3.3 search {item.sku}: {len(rows)}")
    if len(rows) > 1:
        raise ManualReview(f"Several products match {item.sku}. Stopped for manual review.")
    if len(rows) == 1:
        screen.click_line(rows[0])
        time.sleep(0.2)
        ui.click_dialog_button(app, "OK")
        print(f"Selected product {item.sku}", flush=True)
        return True
    print(f"No product {item.sku}. Cancelling the selector.", flush=True)
    ui.click_dialog_button(app, "Cancel")
    time.sleep(0.4)
    return False


def _set_gross_price(app, gross: str) -> None:
    """The product form has Price (gross) and price (net). Only the gross field is typed."""
    found = []
    for row in screen.lines():
        text = screen.norm(row["text"])
        if not text.startswith("price") or "gross" not in text:
            continue
        label_right = row["tokens"][0]["right"]
        for token in row["tokens"]:
            part = screen.norm(token["text"])
            if part == "price" or "gross" in part:
                label_right = token["right"]
                continue
            break
        found.append({**row, "label_right": label_right})
    if len(found) != 1:
        sample = [row["text"] for row in found[:8]]
        raise GroundingError(f"Price (gross) matched {len(found)}: {sample}")
    row = found[0]
    pyautogui.click(row["label_right"] + 80, (row["y"] + row["bottom"]) / 2)
    time.sleep(0.2)
    element = ax.focused(app)
    if ax.role(element) not in ("AXTextField", "AXTextArea"):
        raise GroundingError(f"Price (gross) did not focus (role {ax.role(element)})")
    ax.set_value(element, gross, "Price (gross)")
    print(f"  Price (gross): {gross!r}", flush=True)


def _on_product_form(row) -> bool:
    """The product editor, above the terminal."""
    _, screen_h = pyautogui.size()
    return row["x"] > 400 and row["y"] < screen_h * 0.78


def _not_the_vat_log(row) -> bool:
    """The terminal still shows Name and Description from the VAT that was just saved."""
    return _on_product_form(row) and "vat" not in screen.norm(row["text"])


def _description_field(row) -> bool:
    """The description field sits below the section title of the same name."""
    return _not_the_vat_log(row) and row["y"] > 400


def _price_anchor_y(lines: list[dict]) -> float | None:
    anchors = [
        line for line in lines
        if _on_product_form(line) and (
            screen.norm(line["text"]).startswith("cost price")
            or (screen.norm(line["text"]).startswith("price") and "gross" in screen.norm(line["text"]))
        )
    ]
    if not anchors:
        return None
    return min(line["y"] for line in anchors)


def _near_vat_field(row, anchor_y: float | None) -> bool:
    """The VAT combo beside the prices, not the editor tab named VAT 19%."""
    if not _on_product_form(row):
        return False
    if anchor_y is None:
        return row["y"] > 280
    return anchor_y - 80 < row["y"] < anchor_y + 220


def _set_product_vat(app, item: Item) -> None:
    """Select VAT 19%. VAT Free Tax is the other entry in that list."""
    del app
    wanted = screen.norm(item.vat_name)

    def vat_rows() -> list[dict]:
        lines = screen.lines()
        anchor_y = _price_anchor_y(lines)
        return [
            row for row in lines
            if _near_vat_field(row, anchor_y) and screen.norm(row["text"]).startswith("vat")
        ]

    found = vat_rows()
    exact = [row for row in found if wanted in screen.norm(row["text"])]
    if len(found) == 1 and exact:
        print(f"  VAT: {item.vat_name}", flush=True)
        return
    if len(found) > 1 and len(exact) == 1:
        screen.click_line(exact[0])
        time.sleep(0.4)
    else:
        if len(found) != 1:
            sample = [row["text"] for row in found[:6]]
            raise GroundingError(f"Product VAT field matched {len(found)}: {sample}")
        row = found[0]
        anchor = {**row, "label_right": row["tokens"][0]["right"]}
        try:
            field = screen.white_field_on_row(anchor)
            pyautogui.click(field["right"] - 12, (field["y"] + field["bottom"]) / 2)
        except RuntimeError:
            pyautogui.click(row["right"] - 8, (row["y"] + row["bottom"]) / 2)
        time.sleep(0.5)
        options = [
            line for line in screen.lines()
            if _on_product_form(line)
            and wanted in screen.norm(line["text"])
            and line["y"] > row["bottom"] + 2
        ]
        if len(options) != 1:
            sample = [line["text"] for line in options[:6]]
            raise ManualReview(
                f"VAT option {item.vat_name!r} matched {len(options)}: {sample}. Nothing was chosen."
            )
        screen.click_line(options[0])
        time.sleep(0.4)
    if not any(wanted in screen.norm(row["text"]) for row in vat_rows()):
        raise ManualReview(f"Product VAT does not show {item.vat_name}. Not saved.")
    print(f"  VAT: {item.vat_name}", flush=True)


def create_product(app, item: Item) -> None:
    """3.7-3.11 New product after the VAT exists."""
    ui.click_menu(app, "New", "New product")
    time.sleep(0.5)
    if not ax.tab_is_active(app, "New Product"):
        # Some builds title the tab "New product".
        try:
            ax.show_tab(app, "New product")
        except GroundingError:
            raise GroundingError(f"New product did not open. Tabs: {ax.tab_titles(app)}")
    ui.set_text_right_of(app, "Item Number", item.sku, offset=40, region=_on_product_form)
    ui.set_text_right_of(app, "Name", item.description, offset=40, region=_not_the_vat_log)
    # The section title and the field are both named Description. Use the field.
    # The terminal still shows the VAT step's "Description: 'VAT 19%'".
    row = screen.label_anchor("Description", region=_description_field)
    pyautogui.click(row["label_right"] + 40, (row["y"] + row["bottom"]) / 2)
    time.sleep(0.2)
    element = ax.focused(app)
    if ax.role(element) not in ("AXTextField", "AXTextArea"):
        raise GroundingError(f"Product description did not focus (role {ax.role(element)})")
    ax.set_value(element, item.description, "Description")
    gross = f"{item.gross_unit:.2f}"
    _set_gross_price(app, gross)
    ui.set_text_right_of(app, "cost price", "0.00", offset=80, region=_on_product_form)
    _set_product_vat(app, item)
    ui.set_text_right_of(app, "Stock", "0.00", offset=70, region=_on_product_form)
    screen.capture(f"prod-new-{item.sku}", f"3.8-3.10 {item.sku} gross {gross}")
    ui.save_once(app, f"product {item.sku}")
    ax.show_tab(app, "New Order")


def reselect_product(app, item: Item) -> None:
    """3.12"""
    ax.show_tab(app, "New Order")
    click_product_selector()
    if not try_select_product(app, item):
        raise ManualReview(f"Saved product {item.sku} did not appear. Stopped for manual review.")


def _money_token(text: str):
    import re
    match = re.search(r"\d+(?:[.,]\d+)?", text.replace(" ", ""))
    if not match:
        return None
    return money(match.group(0).replace(",", "."))


def _shows_amount(text: str, amount: Decimal) -> bool:
    """True when the line price is in the read, even with a currency sign or a split cent."""
    compact = "".join(text.replace("\u00a0", " ").replace("\u202f", " ").split())
    shown = f"{amount:.2f}"
    if shown in compact or shown.replace(".", ",") in compact:
        return True
    digits = "".join(ch for ch in compact if ch.isdigit())
    return f"{int(amount * 100)}" in digits


def _items_grid_text() -> str:
    """Read the item header and the first rows, including white text on the blue row.

    The highlight is a run of blue pixels. A fraction of the whole crop misses it
    when the window is wider than the selected cells, and the white price stays invisible.
    """
    import cv2
    import numpy as np
    from pathlib import Path
    import tempfile

    from fakturama_auto.extract import _vision_text

    shot, scale_x, scale_y = screen.geometry()
    array = np.array(shot.convert("RGB"))
    screen_w, _ = pyautogui.size()
    try:
        items = screen.line_starting("Items")
        x0 = int(max(0, items["x"] - 8) / scale_x)
        y0 = int(max(0, items["y"] - 6) / scale_y)
    except RuntimeError:
        x0, y0 = int(520 / scale_x), int(400 / scale_y)
    x1 = int(min(array.shape[1], (screen_w - 16) / scale_x))
    y1 = int(min(array.shape[0], y0 + 120 / scale_y))
    roi = array[y0:y1, x0:x1]
    if roi.size == 0:
        return ""
    red = roi[:, :, 0].astype("int16")
    blue = roi[:, :, 2].astype("int16")
    is_blue = (blue > 185) & (blue > red + 18)
    row_selected = is_blue.sum(axis=1) > 40
    gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    painted = np.full(gray.shape, 255, dtype="uint8")
    painted[gray < 90] = 0
    white = np.all(roi > 210, axis=2)
    for row_index, selected in enumerate(row_selected):
        if not selected:
            continue
        painted[row_index, white[row_index]] = 0
        painted[row_index, is_blue[row_index]] = 255
    big = cv2.resize(painted, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        path = handle.name
    cv2.imwrite(path, big)
    return _vision_text(Path(path))


def complete_line(app, item: Item, index: int) -> None:
    """3.13-3.16 Qty, unit price and the line discount, then check the line price.

    VAT is taken from the product. A line that is still tax-free is not saved.
    """
    print(f"Completing line {index + 1} {item.sku}", flush=True)
    # Enter on Qty clears the blue selection. Price and discount stay on that row.
    row_y = _set_line_cell(app, item, "Qty.", _format_qty(item.quantity))
    _set_line_cell(app, item, "U.Price", f"{item.unit_net:.2f}", row_y=row_y)
    # Fakturama displays a 10% line discount as -10.00 %.
    _set_line_cell(app, item, "Discount", f"{item.discount_percent:.0f}", row_y=row_y)
    shown = f"{item.expected_line_net:.2f}"
    text = _wait_for_line_price(item)
    # A click on the heading writes into the item number and leaves quantity at 1,
    # so the price stays the single-unit net (225.00 instead of 450.00).
    if (
        not _shows_amount(text, item.expected_line_net)
        and item.quantity != 1
        and _shows_amount(text, _discounted_unit(item))
    ):
        print("  Quantity is still 1. Setting Qty on the decimal cell.", flush=True)
        _set_line_cell(app, item, "Qty.", _format_qty(item.quantity), row_y=row_y)
        text = _wait_for_line_price(item)
    if not _shows_amount(text, item.expected_line_net):
        seen = " | ".join(
            line.strip() for line in text.splitlines() if any(ch.isdigit() for ch in line)
        )[:220]
        raise ManualReview(
            f"Line {item.sku} price {shown} is not visible ({seen}). Not saving the Order."
        )
    if item.vat_name.casefold() not in text.casefold() and "19%" not in text and "19" not in text:
        raise ManualReview(
            f"Line {item.sku} does not show {item.vat_name}. Not saving the Order."
        )
    print(f"  Line {item.sku} price {shown} verified", flush=True)
    screen.capture(f"prod-line-{item.sku}", f"3.13-3.16 {item.sku} qty/price/vat/discount")


def _format_qty(number: Decimal) -> str:
    if number == number.to_integral():
        return str(int(number))
    return f"{number:.2f}"


def _discounted_unit(item: Item) -> Decimal:
    factor = Decimal(1) - item.discount_percent / Decimal(100)
    return money(item.unit_net * factor)


def _header_words() -> list[tuple[str, float, float]]:
    """Gray item-header words as (normalized text, left, right) in screen points."""
    import cv2
    import numpy as np
    import pytesseract
    from pytesseract import Output

    shot, scale_x, scale_y = screen.geometry()
    array = np.array(shot.convert("RGB"))
    items = screen.line_starting("Items")
    x0, x1 = int(items["x"] / scale_x), int(1600 / scale_x)
    y0, y1 = int(items["y"] / scale_y), int((items["bottom"] + 10) / scale_y)
    if y1 <= y0 or x1 <= x0:
        return []
    gray = cv2.cvtColor(array[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)
    big = cv2.resize(cv2.bitwise_not(binary), None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    data = pytesseract.image_to_data(big, config="--psm 7", output_type=Output.DICT)
    words = []
    for index, raw in enumerate(data["text"]):
        text = str(raw).strip()
        if not text:
            continue
        left = (x0 + data["left"][index] / 3) * scale_x
        right = (x0 + (data["left"][index] + data["width"][index]) / 3) * scale_x
        words.append((screen.norm(text), left, right))
    return words


def _column_center(label: str) -> float:
    """The item-table header is gray, so the normal screen read misses it."""
    wanted = screen.norm(label).rstrip(".")
    hits: list[float] = []
    for _attempt in range(2):
        words = _header_words()
        hits = [(left + right) / 2 for text, left, right in words if text.rstrip(".") == wanted]
        if len(hits) == 1:
            return hits[0]
        if wanted == "qty":
            # Qty is often not read as that word. It is the heading immediately left of Item,
            # not the position heading further left.
            items = screen.line_starting("Items")
            item_no = [word for word in words if word[0].rstrip(".") == "item" and word[1] > items["x"] + 80]
            if len(item_no) == 1:
                before = [
                    word for word in words
                    if word[2] < item_no[0][1] and word[1] > item_no[0][1] - 90
                ]
                before.sort(key=lambda word: word[1])
                quantity_words = [word for word in before if word[0].rstrip(".") not in {"p", "pos"}]
                chosen = quantity_words[-1] if quantity_words else (before[-1] if before else None)
                if chosen is not None:
                    return (chosen[1] + chosen[2]) / 2
        time.sleep(0.4)
    raise ManualReview(f"Items column {label!r} matched {len(hits)}. The cell was not edited.")


def _item_heading_left() -> float | None:
    items = screen.line_starting("Items")
    headings = [
        word for word in _header_words()
        if word[0].rstrip(".") == "item" and word[1] > items["x"] + 80
    ]
    if len(headings) != 1:
        return None
    return headings[0][1]


def _pick_quantity_token(tokens: list[dict], header_x: float, item_left: float | None) -> dict | None:
    """The right-aligned quantity decimal, not the position integer or the item number.

    The Qty heading is the empty left side of the cell. The first digit in a wide
    window around that heading is the item number, and writing there leaves the
    quantity at 1.
    """
    decimal = re.compile(r"^\d+[.,]\d{2}$")
    found = []
    for token in tokens:
        raw = str(token["text"]).strip()
        if raw.startswith(("$", "-", "+")):
            continue
        if not decimal.fullmatch(raw.replace(" ", "")):
            continue
        if token["x"] < header_x - 30:
            continue
        if item_left is not None and token["x"] >= item_left - 4:
            continue
        if token["x"] > header_x + 160:
            continue
        found.append(token)
    if not found:
        return None
    found.sort(key=lambda token: token["x"])
    return found[0]


def _opened_is_quantity(value: str) -> bool:
    """A quantity editor shows a decimal such as 1.00. Position is a bare integer."""
    compact = value.replace(" ", "").replace("\u00a0", "")
    if re.search(r"[A-Za-z$€£]", compact):
        return False
    return bool(re.fullmatch(r"\d+[.,]\d+", compact))


def _selected_row_y() -> float | None:
    """The line just inserted is drawn blue, with white text that OCR skips."""
    import numpy as np

    shot, scale_x, scale_y = screen.geometry()
    array = np.array(shot.convert("RGB"))
    # Item number and name stay filled; wider cells are empty and not blue.
    x0, x1 = int(720 / scale_x), int(920 / scale_x)
    bands: list[list[float]] = []
    current: list[float] = []
    for pixel_y in range(int(420 / scale_y), int(780 / scale_y)):
        band = array[pixel_y, x0:x1]
        red = band[:, 0].astype("int16")
        blue = band[:, 2].astype("int16")
        selected = ((blue > 220) & (blue > red + 30)).mean() > 0.5
        if selected:
            current.append(pixel_y * scale_y)
        elif current:
            bands.append(current)
            current = []
    if current:
        bands.append(current)
    # Stay inside the blue row. A point below it focuses the table, not the cell.
    centers = [(group[0] + group[-1]) / 2 for group in bands if len(group) > 6]
    if len(centers) == 1:
        return centers[0]
    return None


def _wait_for_line_price(item: Item) -> str:
    text = ""
    for _ in range(3):
        time.sleep(0.45)
        text = _items_grid_text()
        if _shows_amount(text, item.expected_line_net):
            break
    return text


def _quantity_click_x(row_y: float, header_x: float) -> float:
    """Click the decimal quantity, which sits just left of the item number."""
    on_row = [
        token for token in screen.tokens()
        if abs((token["y"] + token["bottom"]) / 2 - row_y) < 18
    ]
    item_left = _item_heading_left()
    token = _pick_quantity_token(on_row, header_x, item_left)
    if token is not None:
        return (token["x"] + token["right"]) / 2
    if item_left is not None:
        return item_left - 24
    return header_x + 70


def _sku_row_y(item: Item) -> float:
    """The item-number cell in the order table, not the same text in the terminal."""
    prefix = _sku_prefix(item.sku).lower()
    try:
        items = screen.line_starting("Items")
        top = items["bottom"]
        left = items["x"]
    except RuntimeError:
        top, left = 420, 500
    _, screen_h = pyautogui.size()
    hits = [
        token for token in screen.tokens()
        if prefix in screen.norm(token["text"])
        and top - 4 < token["y"] < min(top + 220, screen_h * 0.72)
        and token["x"] > left
    ]
    rows = []
    for token in hits:
        if any(abs(token["y"] - kept["y"]) < 14 for kept in rows):
            continue
        rows.append(token)
    if len(rows) != 1:
        raise ManualReview(
            f"Line {item.sku} matched {len(rows)} rows in the items table. The cell was not edited."
        )
    return (rows[0]["y"] + rows[0]["bottom"]) / 2


def _set_line_cell(app, item: Item, label: str, text: str, row_y: float | None = None) -> float:
    """NatTable cells are not in the accessibility tree until double-clicked.

    The column comes from the gray header. The row is the blue selection,
    which is the line just placed on the order. Enter removes that highlight,
    so later cells on the line reuse the row the quantity was edited on.
    """
    header_x = _column_center(label)
    if row_y is None:
        row_y = _selected_row_y()
    if row_y is None:
        row_y = _sku_row_y(item)
    center_x = _quantity_click_x(row_y, header_x) if label == "Qty." else header_x
    # A step to the right of the quantity number lands on the item number.
    offsets = ((0, 0), (-12, 0), (-24, 0), (0, 4)) if label == "Qty." else (
        (0, 0), (16, 0), (0, -6), (0, 6), (28, 0)
    )
    element = None
    for dx, dy in offsets:
        pyautogui.doubleClick(center_x + dx, row_y + dy)
        time.sleep(0.25)
        element = ax.focused(app)
        if ax.role(element) not in ("AXTextField", "AXTextArea"):
            element = None
            continue
        if label == "Qty." and not _opened_is_quantity(str(ax.value(element) or "")):
            pyautogui.press("escape")
            time.sleep(0.15)
            element = None
            continue
        break
    if element is None or ax.role(element) not in ("AXTextField", "AXTextArea"):
        raise GroundingError(f"Line cell {label!r} did not focus (role {ax.role(element)})")
    try:
        ax.set_value(element, text, label)
    except GroundingError as exc:
        readback = str(ax.value(element) or "")
        if text not in readback.replace("$", "").replace(" ", ""):
            raise GroundingError(str(exc)) from exc
    pyautogui.press("enter")
    time.sleep(0.3)
    print(f"  {label}: {text}", flush=True)
    return row_y


def add_all_products(app, order: OrderData) -> None:
    """3.1 Run selection, then creation, for every item in source order."""
    ax.show_tab(app, "New Order")
    time.sleep(0.4)
    vats_ready: set[str] = set()
    for index, item in enumerate(order.items):
        grid = _items_grid_text()
        if _sku_prefix(item.sku).lower() not in grid.lower():
            time.sleep(0.45)
            grid = _items_grid_text()
        prefix = _sku_prefix(item.sku).lower()
        if prefix in grid.lower() and _shows_amount(grid, item.expected_line_net):
            print(f"Line {item.sku} already shows {item.expected_line_net}", flush=True)
            continue
        if prefix in grid.lower():
            print(f"Line {item.sku} is on the order without its line price. Completing it.", flush=True)
            complete_line(app, item, index)
            continue
        click_product_selector()
        if try_select_product(app, item):
            complete_line(app, item, index)
            continue
        if item.vat_name not in vats_ready:
            vat_step.ensure_vat(app, item)
            vats_ready.add(item.vat_name)
        create_product(app, item)
        reselect_product(app, item)
        complete_line(app, item, index)
