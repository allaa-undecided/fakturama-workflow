"""Fakturama macOS: safe, unsaved Order date/reference automation test.

Requirements: pyobjc-framework-ApplicationServices, pyobjc-framework-Cocoa,
              pyautogui, pytesseract, Pillow; Tesseract CLI installed.
"""
import re
import time

import AppKit
import ApplicationServices as AX
import pyautogui
import pytesseract
from pytesseract import Output

TEST_DATE = "Mar 15, 2025"
TEST_REFERENCE = "TEST-REF-001"
DATE_HELP = "The document's date"
REFERENCE_HELP = "Customer's reference"

pyautogui.FAILSAFE = True  # Move pointer to top-left to interrupt mouse automation
pyautogui.PAUSE = 0.12


def attr(element, name):
    error, value = AX.AXUIElementCopyAttributeValue(element, name, None)
    return value if error == 0 else None


def find_fakturama():
    for application in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
        if "fakturama" in str(application.localizedName() or "").lower():
            return application, AX.AXUIElementCreateApplication(application.processIdentifier())
    raise RuntimeError("Fakturama is not running")


def find_ui(element, role, title, depth=0):
    if depth > 15:
        return None
    if attr(element, "AXRole") == role and attr(element, "AXTitle") == title:
        return element
    for child in attr(element, "AXChildren") or []:
        found = find_ui(child, role, title, depth + 1)
        if found is not None:
            return found
    return None


def focused(app):
    return attr(app, "AXFocusedUIElement")


def in_order(element):
    for _ in range(12):
        if element is None:
            return False
        if (attr(element, "AXRole") == "SWTComposite"
                and attr(element, "AXTitle") in ("New Order", "*New Order")):
            return True
        element = attr(element, "AXParent")
    return False


def verify_focus(app, help_fragment):
    element = focused(app)
    role = attr(element, "AXRole") if element is not None else None
    help_text = str(attr(element, "AXHelp") or "") if element is not None else ""
    if role != "AXTextField" or help_fragment.lower() not in help_text.lower() or not in_order(element):
        raise RuntimeError(
            f"Unsafe focus: expected {help_fragment!r} within New Order; "
            f"got role={role!r}, AXHelp={help_text!r}. Nothing was written."
        )
    return element


def ocr_screen():
    shot = pyautogui.screenshot()
    width, height = shot.size
    screen_width, screen_height = pyautogui.size()
    scale_x, scale_y = screen_width / width, screen_height / height
    data = pytesseract.image_to_data(shot, config="--psm 11", output_type=Output.DICT)
    words = []
    for i, token in enumerate(data["text"]):
        token = token.strip()
        if not token:
            continue
        words.append({
            "text": token,
            "x": (data["left"][i] + data["width"][i] / 2) * scale_x,
            "y": (data["top"][i] + data["height"][i] / 2) * scale_y,
        })
    return words


def focus_date_visually(app):
    """Use current on-screen Order number as the anchor; never fixed coordinates."""
    print("Finding generated Order number on screen with OCR...", flush=True)
    words = ocr_screen()
    candidates = [w for w in words if re.fullmatch(r"[Pp][0-9Oo]{5,}", w["text"])]
    if len(candidates) != 1:
        raise RuntimeError(
            "Couldn't uniquely identify the generated Order number by OCR. "
            "Keep one New Order open, visible and unobstructed; no value changed. "
            f"OCR candidates: {[w['text'] for w in candidates]}"
        )
    candidate = candidates[0]
    print(f"Order number OCR: {candidate['text']}")
    pyautogui.click(candidate["x"], candidate["y"])
    time.sleep(0.3)
    start = focused(app)
    if attr(start, "AXRole") != "AXTextField" or not in_order(start):
        raise RuntimeError("Order number did not focus an Order text field; stopping")
    print("Order number focused; navigating to Date...")
    pyautogui.press("tab")
    time.sleep(0.3)
    return verify_focus(app, DATE_HELP)


def set_date(app, value):
    field = verify_focus(app, DATE_HELP)
    before = attr(field, "AXValue")
    print(f"Date before: {before!r}")
    if before != value:
        result = AX.AXUIElementSetAttributeValue(field, "AXValue", value)
        if result != 0:
            raise RuntimeError(f"Date AXValue update failed (error {result})")
        if attr(field, "AXValue") != value:
            raise RuntimeError("Date AXValue readback mismatch")
    print(f"Date AXValue verified: {value}")
    # Leaving the widget can commit its value; don't assume readback implies persistence.
    pyautogui.press("tab")
    time.sleep(0.35)
    pyautogui.hotkey("shift", "tab")
    time.sleep(0.25)
    check_field = verify_focus(app, DATE_HELP)
    if attr(check_field, "AXValue") != value:
        raise RuntimeError("Date changed after focus left the widget; stopping")
    print("Date retained after Tab / Shift+Tab")


def focus_reference(app, max_tabs=5):
    # Start from verified Date, then use observed tab sequence.
    verify_focus(app, DATE_HELP)
    for step in range(1, max_tabs + 1):
        pyautogui.press("tab")
        time.sleep(0.25)
        element = focused(app)
        role = attr(element, "AXRole") if element is not None else None
        help_text = str(attr(element, "AXHelp") or "") if element is not None else ""
        print(f"Tab {step}: {role}, AXHelp={help_text!r}")
        if role == "AXTextField" and REFERENCE_HELP.lower() in help_text.lower():
            return verify_focus(app, REFERENCE_HELP)
    raise RuntimeError("Cust.Ref. was not found within 5 Tabs from Date; no reference entered")


def set_reference(app, value):
    field = verify_focus(app, REFERENCE_HELP)
    previous = attr(field, "AXValue")
    print(f"Cust.Ref. before: {previous!r}")
    if previous != value:
        result = AX.AXUIElementSetAttributeValue(field, "AXValue", value)
        if result != 0:
            raise RuntimeError(f"Cust.Ref. AXValue update failed (error {result})")
    if attr(field, "AXValue") != value:
        raise RuntimeError("Cust.Ref. readback mismatch")
    pyautogui.press("tab")
    time.sleep(0.3)
    pyautogui.hotkey("shift", "tab")
    time.sleep(0.25)
    if attr(verify_focus(app, REFERENCE_HELP), "AXValue") != value:
        raise RuntimeError("Cust.Ref. did not retain value after focus change")
    print(f"SUCCESS: Cust.Ref. retained {value!r}")



def set_price_mode_net(app):
    """Ground the price-mode dropdown in the *current* screen, select Net, verify visually.

    This intentionally fails closed when OCR cannot locate the relevant UI.
    """
    print("Locating document price mode (Gross/Net)...", flush=True)
    words = ocr_screen()
    order_numbers = [w for w in words if re.fullmatch(r"[Pp][0-9Oo]{5,}", w["text"])]
    if len(order_numbers) != 1:
        raise RuntimeError("Cannot uniquely locate the open Order number; leaving price mode unchanged")
    order = order_numbers[0]

    # Price mode is on the same upper header row as the current Order number.
    # These are relative relationships, not fixed pixel coordinates.
    def header_values(items):
        return [w for w in items if w["text"].casefold() in {"gross", "net", "---"}
                and abs(w["y"] - order["y"]) < 45
                and w["x"] > order["x"] + 90]

    matches = header_values(words)
    if len(matches) != 1:
        raise RuntimeError(f"Could not uniquely ground price-mode dropdown: {matches}")

    current = matches[0]
    print(f"Price mode shown: {current['text']!r}", flush=True)
    if current["text"].casefold() == "net":
        print("Price mode already Net; no change needed.", flush=True)
        return

    # Click inside the dropdown, but only after dynamically grounding it by OCR.
    pyautogui.click(current["x"], current["y"])
    time.sleep(0.4)

    # Favor choosing a visible Net option. Avoid 'Total Net' elsewhere on screen.
    options = ocr_screen()
    net_options = [w for w in options if w["text"].casefold() == "net"
                   and abs(w["x"] - current["x"]) < 150
                   and current["y"] - 10 < w["y"] < current["y"] + 160]

    if len(net_options) == 1:
        print("Selecting visible Net option...", flush=True)
        pyautogui.click(net_options[0]["x"], net_options[0]["y"])
    else:
        print("Net option not uniquely OCR-visible; trying dropdown keyboard selection...", flush=True)
        pyautogui.press("n")
        pyautogui.press("enter")

    time.sleep(0.5)
    confirmed = header_values(ocr_screen())
    if len(confirmed) != 1 or confirmed[0]["text"].casefold() != "net":
        raise RuntimeError(
            f"Could not visually verify price mode Net; observed {confirmed}. "
            "Do not save the Order."
        )
    print("SUCCESS: Document price mode visually verified as Net.", flush=True)


def main():
    print("Starting Fakturama Order field test...", flush=True)
    if not AX.AXIsProcessTrusted():
        raise RuntimeError("Accessibility permission not granted to the Python-running application")
    running, app = find_fakturama()
    print(f"Found Fakturama (PID {running.processIdentifier()})")
    running.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
    time.sleep(0.8)
    order_tabs = [find_ui(app, "AXTabGroup", title) for title in ("New Order", "*New Order")]
    if not any(tab is not None for tab in order_tabs):
        button = find_ui(app, "AXButton", "Order")
        if button is None or AX.AXUIElementPerformAction(button, "AXPress") != 0:
            raise RuntimeError("Could not open a New Order")
        time.sleep(0.8)
    print("Keep the New Order window visible; locating the Date field...")
    focus_date_visually(app)
    set_date(app, TEST_DATE)
    focus_reference(app)
    set_reference(app, TEST_REFERENCE)
    set_price_mode_net(app)
    print("\nTEST COMPLETE: Date, Cust.Ref. and Net price mode verified; Order NOT saved.")
    print("Visually check the two fields in Fakturama and discard this test Order.")


if __name__ == "__main__":
    main()
