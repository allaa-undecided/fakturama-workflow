"""Fakturama interactions shared by every step.

Controls are found by Accessibility role and title first. When SWT does not
expose a control, the visible label is located with OCR and the click is
placed relative to that label. Every write is read back.
"""

from __future__ import annotations

import time

import pyautogui

from fakturama_auto import ax, screen
from fakturama_auto.errors import GroundingError, ManualReview


def click_menu(app, menu_title: str, item_title: str) -> None:
    menu = ax.find_unique(app, "AXMenuBarItem", menu_title)
    ax.press(menu)
    time.sleep(0.35)
    item = ax.find_unique(app, "AXMenuItem", item_title)
    ax.press(item)
    time.sleep(0.6)


def click_toolbar(app, button_title: str) -> None:
    ax.press(ax.find_unique(app, "AXButton", button_title))
    time.sleep(0.5)


def save_once(app, what: str) -> None:
    """The toolbar Save control. Clicked exactly once."""
    buttons = ax.find_all(app, "AXButton", "Save")
    if len(buttons) != 1:
        raise ManualReview(f"Save for {what} is ambiguous ({len(buttons)} buttons). Not saved.")
    ax.press(buttons[0])
    time.sleep(0.8)
    print(f"Saved {what} once", flush=True)


def _focused_editable(app, label: str):
    element = ax.focused(app)
    if ax.role(element) not in ("AXTextField", "AXTextArea", "AXComboBox"):
        raise GroundingError(
            f"{label}: click did not land in an editable control (role {ax.role(element)})"
        )
    return element


def set_text_right_of(app, label: str, text: str, offset: int = 60, exact: bool = True, ok=None, region=None) -> None:
    """Click the field to the right of a uniquely visible label and write it."""
    del exact  # the anchor is the label tokens, so a joined value does not move the click
    if text is None or text == "":
        return
    row = screen.label_anchor(label, region=region)
    pyautogui.click(row["label_right"] + offset, (row["y"] + row["bottom"]) / 2)
    time.sleep(0.2)
    element = _focused_editable(app, label)
    ax.set_value(element, text, label, ok=ok)
    print(f"  {label}: {text!r}", flush=True)


def confirm_text_right_of(label: str, expected: str, offset_limit: int = 320, region=None) -> None:
    row = screen.label_anchor(label, region=region)
    words = [
        token for token in screen.tokens()
        if token["x"] >= row["label_right"] - 2
        and token["x"] - row["label_right"] < offset_limit
        and abs(token["y"] - row["y"]) < 16
    ]
    words.sort(key=lambda token: token["x"])
    observed = " ".join(token["text"] for token in words)
    if screen.norm(expected) not in screen.norm(observed):
        raise ManualReview(
            f"{label} shows {observed!r}, not {expected!r}. Not saved."
        )
    print(f"  {label}: {expected} verified", flush=True)


def _control_box(element) -> tuple[float, float, float, float] | None:
    import re
    position = str(ax.attr(element, "AXPosition") or "")
    size = str(ax.attr(element, "AXSize") or "")
    x_match = re.search(r"x:\s*([\d.]+)", position)
    y_match = re.search(r"y:\s*([\d.]+)", position)
    w_match = re.search(r"w:\s*([\d.]+)", size)
    h_match = re.search(r"h:\s*([\d.]+)", size)
    if not (x_match and y_match and w_match and h_match):
        return None
    return (
        float(x_match.group(1)),
        float(y_match.group(1)),
        float(w_match.group(1)),
        float(h_match.group(1)),
    )


def choose_combo(app, label: str, option: str, offset: int = 90, region=None) -> None:
    """Open the combo beside a label and click the option. Nothing is typed."""
    del app, offset  # the arrow is the right edge of the visible field, not the focused control
    row = screen.label_anchor(label, region=region)
    value_text = screen.norm(row["text"])
    label_text = screen.norm(label)
    if value_text.startswith(label_text):
        value_text = value_text[len(label_text):].strip()
    if value_text == screen.norm(option) or value_text.startswith(screen.norm(option) + " "):
        confirm_text_right_of(label, option, region=region)
        return
    field = screen.white_field_on_row(row)
    y = (field["y"] + field["bottom"]) / 2
    pyautogui.click(field["right"] - 12, y)
    time.sleep(0.45)
    wanted = screen.norm(option).split()
    words = [
        token for token in screen.tokens()
        if field["x"] - 20 <= token["x"] <= field["right"] + 30
        and row["bottom"] + 2 < token["y"] < row["bottom"] + 240
    ]
    words.sort(key=lambda token: (token["y"], token["x"]))
    hits = []
    for index in range(len(words)):
        window = words[index: index + len(wanted)]
        if [screen.norm(token["text"]) for token in window] != wanted:
            continue
        if max(token["y"] for token in window) - min(token["y"] for token in window) > 12:
            continue
        hits.append(window)
    if len(hits) != 1:
        raise ManualReview(
            f"{label} option {option!r} matched {len(hits)} rows. Nothing was chosen."
        )
    screen.click_line(hits[0][0])
    time.sleep(0.35)
    confirm_text_right_of(label, option, region=region)


def click_sidebar(label: str) -> None:
    """Left-hand data navigator. The label must be unique inside the left quarter."""
    screen_w, _ = pyautogui.size()

    def on_the_left(row):
        return row["x"] < screen_w * 0.30

    row = screen.unique_line(label, exact=False, region=on_the_left)
    screen.click_line(row)
    time.sleep(0.5)
    print(f"Opened sidebar {label!r}", flush=True)


def open_list_via_data_menu(app, *item_titles: str) -> None:
    """Try Data-menu item titles in order, then the left sidebar."""
    menu = ax.find_unique(app, "AXMenuBarItem", "Data")
    ax.press(menu)
    time.sleep(0.35)
    available = {
        ax.title(element): element
        for element in ax.walk(app)
        if ax.role(element) == "AXMenuItem"
    }
    for wanted in item_titles:
        if wanted in available:
            ax.press(available[wanted])
            time.sleep(0.6)
            print(f"Opened Data > {wanted}", flush=True)
            return
    pyautogui.press("escape")
    time.sleep(0.2)
    click_sidebar(item_titles[-1])


def dialog_search_field(app, window_fragment: str):
    """The single text field of a Fakturama selector dialog."""
    dialog = ax.window_titled(app, window_fragment)
    fields = [
        element for element in ax.walk(dialog, limit=600)
        if ax.role(element) in ("AXTextField", "AXTextArea")
    ]
    if len(fields) != 1:
        raise GroundingError(
            f"{window_fragment!r} has {len(fields)} text fields; search was not typed"
        )
    return fields[0]


def search_field_right_of(app, label: str = "Search", x_min_ratio: float = 0.45) -> object:
    screen_w, screen_h = pyautogui.size()

    def region(row):
        return row["x"] > screen_w * x_min_ratio and row["y"] < screen_h * 0.45

    row = screen.label_anchor(label, region=region)
    pyautogui.click(row["label_right"] + 50, (row["y"] + row["bottom"]) / 2)
    time.sleep(0.2)
    return _focused_editable(app, label)


def type_search(app, field, query: str) -> None:
    ax.set_value(field, query, "Search")
    pyautogui.press("tab")
    time.sleep(0.7)


def wait_until_stable(seconds: float = 0.6, samples: int = 2) -> str:
    previous = None
    for _ in range(samples):
        time.sleep(seconds)
        current = screen.visible_text()
        if current == previous:
            return current
        previous = current
    return previous or ""


def dialog_button(app, name: str):
    buttons = ax.find_all(app, "AXButton", name)
    if len(buttons) != 1:
        raise GroundingError(f"Dialog button {name!r} matched {len(buttons)}")
    return buttons[0]


def click_dialog_button(app, name: str) -> None:
    ax.press(dialog_button(app, name))
    time.sleep(0.5)


def rows_containing(text: str, y_min_ratio: float = 0.15, y_max_ratio: float = 0.75) -> list[dict]:
    _, screen_h = pyautogui.size()
    wanted = screen.norm(text)
    return [
        row for row in screen.lines()
        if wanted in screen.norm(row["text"])
        and screen_h * y_min_ratio < row["y"] < screen_h * y_max_ratio
    ]


def click_exact_row(text: str) -> dict:
    hits = [row for row in rows_containing(text) if screen.norm(text) in screen.norm(row["text"])]
    exact = [row for row in hits if screen.norm(row["text"]) == screen.norm(text) or screen.norm(text) in screen.norm(row["text"])]
    if len(exact) != 1:
        raise ManualReview(
            f"Row {text!r} is ambiguous ({len(exact)} hits). Stopped for manual review."
        )
    screen.click_line(exact[0])
    return exact[0]


def green_plus_in(x_min, y_min, x_max, y_max) -> tuple[float, float]:
    hits = screen.green_plus_buttons(x_min, y_min, x_max, y_max)
    if len(hits) != 1:
        raise ManualReview(
            f"Green + control is ambiguous ({len(hits)} in region). Nothing was created."
        )
    return hits[0][0], hits[0][1]


def require_tab(app, name: str) -> None:
    if not ax.tab_is_active(app, name):
        raise GroundingError(f"Expected the {name!r} editor to be active. Tabs: {ax.tab_titles(app)}")
