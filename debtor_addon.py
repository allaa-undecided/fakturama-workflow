
import time

import AppKit
import ApplicationServices as AX
import pyautogui
import pytesseract
from pytesseract import Output


SEARCH_TEXT = "Hello World"

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.2


def get_attr(element, name):
    error, value = AX.AXUIElementCopyAttributeValue(
        element, name, None
    )
    return value if error == 0 else None


def find_fakturama():
    for running in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
        name = str(running.localizedName() or "")

        if "fakturama" in name.lower():
            print(f"Found Fakturama: {name}", flush=True)

            app = AX.AXUIElementCreateApplication(
                running.processIdentifier()
            )

            running.activateWithOptions_(
                AppKit.NSApplicationActivateIgnoringOtherApps
            )

            time.sleep(0.8)
            return app

    raise RuntimeError("Fakturama is not running.")


def find_element(element, role, title, depth=0):
    if depth > 20 or element is None:
        return None

    if (
        get_attr(element, "AXRole") == role
        and get_attr(element, "AXTitle") == title
    ):
        return element

    for child in get_attr(element, "AXChildren") or []:
        result = find_element(child, role, title, depth + 1)

        if result is not None:
            return result

    return None


def ensure_debtors_list(app):
    # Do not reopen it if the tab already exists.
    if find_element(app, "AXTabGroup", "Debtors"):
        print("Debtors list already open.", flush=True)
        return

    print("Opening Debtors through Data menu...", flush=True)

    data_menu = find_element(app, "AXMenuBarItem", "Data")

    if data_menu is None:
        raise RuntimeError("Data menu not found.")

    error = AX.AXUIElementPerformAction(
        data_menu, "AXPress"
    )

    if error != 0:
        raise RuntimeError(f"Cannot open Data menu: {error}")

    time.sleep(0.4)

    debtor_item = find_element(app, "AXMenuItem", "Debtors")

    if debtor_item is None:
        raise RuntimeError("Debtors menu item not found.")

    error = AX.AXUIElementPerformAction(
        debtor_item, "AXPress"
    )

    if error != 0:
        raise RuntimeError(f"Cannot open Debtors: {error}")

    time.sleep(0.8)

    if not find_element(app, "AXTabGroup", "Debtors"):
        raise RuntimeError("Debtors tab was not verified.")

    print("SUCCESS: Debtors list open.", flush=True)


def find_search_label():
    screenshot = pyautogui.screenshot()
    image_w, image_h = screenshot.size
    screen_w, screen_h = pyautogui.size()

    scale_x = screen_w / image_w
    scale_y = screen_h / image_h

    data = pytesseract.image_to_data(
        screenshot,
        config="--psm 11",
        output_type=Output.DICT
    )

    matches = []

    for i, raw in enumerate(data["text"]):
        word = raw.strip().lower().rstrip(":")

        if word != "search":
            continue

        confidence = float(data["conf"][i])
        if confidence < 35:
            continue

        x = data["left"][i] * scale_x
        y = data["top"][i] * scale_y
        width = data["width"][i] * scale_x
        height = data["height"][i] * scale_y

        matches.append({
            "x": x,
            "y": y,
            "width": width,
            "height": height
        })

    print("Search label candidates:", matches, flush=True)

    # The Debtors search box is in the lower-right
    # pane of Fakturama, above its customer table.
    candidates = [
        m for m in matches
        if (
            m["x"] > screen_w * 0.50
            and m["y"] > screen_h * 0.35
            and m["y"] < screen_h * 0.85
        )
    ]

    if len(candidates) != 1:
        raise RuntimeError(
            f"Expected one Debtors Search label, found "
            f"{len(candidates)}. No click performed."
        )

    return candidates[0]


def belongs_to_debtors(element):
    current = element

    for _ in range(12):
        if current is None:
            return False

        role = get_attr(current, "AXRole")
        title = get_attr(current, "AXTitle")

        if role == "SWTComposite" and title == "Debtors":
            return True

        current = get_attr(current, "AXParent")

    return False


def focus_search(app, label):
    # Search input is to the RIGHT of the visible
    # "Search" label, not on the label itself.
    label_right = label["x"] + label["width"]
    center_y = label["y"] + label["height"] / 2

    screen_w, screen_h = pyautogui.size()

    for offset in (30, 60, 100):
        x = label_right + offset
        y = center_y

        if not (0 < x < screen_w and 0 < y < screen_h):
            continue

        print(
            f"Testing Search input at ({x:.0f}, {y:.0f})",
            flush=True
        )

        pyautogui.click(x, y)
        time.sleep(0.4)

        focused = get_attr(app, "AXFocusedUIElement")
        role = get_attr(focused, "AXRole") if focused else None
        help_text = get_attr(focused, "AXHelp") if focused else None

        print(
            f"Focused: {role}, Help: {help_text}",
            flush=True
        )

        if (
            role in ("AXTextField", "AXTextArea", "AXComboBox")
            and belongs_to_debtors(focused)
        ):
            print("SUCCESS: Debtors input focused.", flush=True)
            return focused

    raise RuntimeError(
        "Could not verify the Debtors Search input. "
        "No text was entered."
    )


def search_debtor(app, field, query):
    print(f"Searching for {query!r}...", flush=True)

    error = AX.AXUIElementSetAttributeValue(
        field, "AXValue", query
    )

    if error != 0:
        raise RuntimeError(
            f"Could not enter Search text: AX error {error}"
        )

    actual = get_attr(field, "AXValue")

    if actual != query:
        raise RuntimeError(
            f"Search field mismatch: {actual!r}"
        )

    # Commit text/change focus so the table can update.
    pyautogui.press("tab")
    time.sleep(1)

    print("SUCCESS: Search text entered.", flush=True)
    print("Check the visible Debtors results.", flush=True)


def main():
    print("\nStarting Debtor search test...\n", flush=True)

    if not AX.AXIsProcessTrusted():
        raise RuntimeError(
            "macOS Accessibility permission is not enabled."
        )

    app = find_fakturama()
    ensure_debtors_list(app)

    label = find_search_label()
    field = focus_search(app, label)

    search_debtor(app, field, SEARCH_TEXT)

    print(
        "\nTEST COMPLETE. No customer selected or saved.",
        flush=True
    )


if __name__ == "__main__":
    main()
