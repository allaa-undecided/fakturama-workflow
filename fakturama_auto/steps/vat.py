"""Steps 3.4-3.6: reuse or create the VAT rate a product needs."""

from __future__ import annotations

import time

import pyautogui

from fakturama_auto import ax, screen, ui
from fakturama_auto.errors import GroundingError, ManualReview
from fakturama_auto.models import Item


def open_vats(app) -> None:
    ui.open_list_via_data_menu(app, "VATs", "VAT", "Vats")
    time.sleep(0.4)
    screen.capture("vat-01-list", "3.4 Data > VATs")


def _value_text(percent) -> str:
    if percent == percent.to_integral():
        return str(int(percent))
    return format(percent.normalize(), "f")


def _vat_rows(item: Item, search_bottom: float = 0) -> list[dict]:
    """One entry per VAT table row.

    The search box repeats the query. Name and description on the same row both
    say 'VAT 19%'. Neither of those is a second VAT.
    """
    name = screen.norm(item.vat_name)
    lines = screen.lines()
    screen_h = pyautogui.size()[1]
    header_bottom = 0.0
    for row in lines:
        label = screen.norm(row["text"])
        if row["x"] < 300 or row["y"] > screen_h * 0.55:
            continue
        if label == "name" or label.startswith("name "):
            header_bottom = max(header_bottom, row["bottom"])
    grouped: list[dict] = []
    for row in lines:
        if row["y"] > screen_h * 0.82:
            continue
        if search_bottom and row["bottom"] <= search_bottom + 6:
            continue
        if header_bottom and row["y"] < header_bottom + 2:
            continue
        if name not in screen.norm(row["text"]):
            continue
        same = next((kept for kept in grouped if abs(kept["y"] - row["y"]) < 16), None)
        if same is None:
            grouped.append(dict(row))
            continue
        same["text"] = f"{same['text']} {row['text']}"
        same["right"] = max(same["right"], row["right"])
    for row in lines:
        for kept in grouped:
            if abs(kept["y"] - row["y"]) >= 16:
                continue
            if row["text"] in kept["text"]:
                continue
            kept["text"] = f"{kept['text']} {row['text']}"
    return grouped


def vat_row_is_exact(item: Item, row: dict | None = None) -> bool:
    """Name is 'VAT 19%', value matches, and the e-invoice code is S."""
    text = screen.visible_text()
    name = screen.norm(item.vat_name)
    if name not in text:
        return False
    if row is None:
        rows = _vat_rows(item)
        if len(rows) > 1:
            raise ManualReview(f"Several rows match {item.vat_name}. Stopped for manual review.")
        if len(rows) == 0:
            return False
        row = rows[0]
    row_text = screen.norm(row["text"])
    value = _value_text(item.vat_percent)
    if value not in row_text and f"{value}%" not in row_text and f"{value}.00" not in row_text:
        # The value may sit in a neighboring cell on the same visual line, already joined.
        raise ManualReview(
            f"{item.vat_name} exists but its visible row {row['text']!r} "
            f"does not show value {value}. Stopped for manual review."
        )
    if "standard" not in text and screen.norm("S") not in row_text:
        # Code S is 'S (Standard rate)'. Require the standard-rate wording somewhere
        # on the open VAT editor or the row. A bare missing code is a conflict.
        raise ManualReview(
            f"{item.vat_name} is visible but the Standard rate code was not confirmed."
        )
    return True


def ensure_vat(app, item: Item) -> None:
    """3.4-3.6 Search, reuse one exact VAT, or create it."""
    open_vats(app)
    field = ui.search_field_right_of(app, "Search", x_min_ratio=0.5)
    ui.type_search(app, field, item.vat_name)
    ui.wait_until_stable()
    screen.capture("vat-02-search", f"3.4 search {item.vat_name}")
    box = ui._control_box(field)
    search_bottom = box[1] + box[3] if box else 0
    rows = _vat_rows(item, search_bottom)
    if len(rows) == 1:
        if not vat_row_is_exact(item, rows[0]):
            raise ManualReview(f"{item.vat_name} conflicted. Stopped for manual review.")
        print(f"Reusing {item.vat_name}", flush=True)
        return
    if len(rows) > 1:
        raise ManualReview(f"Several {item.vat_name} rows. Stopped for manual review.")
    print(f"Creating {item.vat_name}", flush=True)
    plus = ui.green_plus_in(0.55, 0.06, 0.98, 0.35)
    pyautogui.click(plus[0], plus[1])
    time.sleep(0.6)
    _fill_new_vat(app, item)
    ui.save_once(app, item.vat_name)
    screen.capture("vat-03-saved", f"3.6 {item.vat_name} saved")


def _percent_readback(expected: str):
    """The value field shows 19% after 19 is written."""

    def ok(readback: str) -> bool:
        shown = readback.replace(" ", "").replace(",", ".")
        if shown.endswith("%"):
            shown = shown[:-1]
        return shown in {expected, f"{expected}.00", f"{expected}.0"}

    return ok


def _fill_new_vat(app, item: Item) -> None:
    """Name and description 'VAT 19%', code stays S, value is the percentage."""
    for label in ("Name", "Description"):
        ui.set_text_right_of(app, label, item.vat_name, offset=90)
    # VAT code (E-Invoice) must stay S (Standard rate). Verify, do not change it
    # when it already says so. A different code is a conflict.
    text = screen.visible_text()
    if "standard" not in text:
        raise ManualReview(
            "New VAT did not show S (Standard rate). Left it unchanged and stopped."
        )
    value = _value_text(item.vat_percent)
    ui.set_text_right_of(app, "Value", value, offset=70, ok=_percent_readback(value))
    print(f"  VAT value {value}, code left as Standard rate", flush=True)
