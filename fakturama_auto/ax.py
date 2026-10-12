"""macOS Accessibility helpers for the Fakturama process."""

from __future__ import annotations

import time

import AppKit
import ApplicationServices as AX

from fakturama_auto.errors import GroundingError

SYSTEM_EVENTS = AX.AXUIElementCreateSystemWide()


def attr(element, name):
    if element is None:
        return None
    error, value = AX.AXUIElementCopyAttributeValue(element, name, None)
    return value if error == 0 else None


def walk(root, limit: int = 4000):
    pending = [root]
    seen = 0
    while pending and seen < limit:
        element = pending.pop()
        seen += 1
        yield element
        children = attr(element, "AXChildren") or []
        pending.extend(children)


def role(element) -> str:
    return str(attr(element, "AXRole") or "")


def title(element) -> str:
    return str(attr(element, "AXTitle") or "")


def value(element):
    return attr(element, "AXValue")


def help_text(element) -> str:
    return str(attr(element, "AXHelp") or "")


def find_all(root, wanted_role: str, wanted_title: str | None = None):
    found = []
    for element in walk(root):
        if role(element) != wanted_role:
            continue
        if wanted_title is not None and title(element) != wanted_title:
            continue
        found.append(element)
    return found


def find_unique(root, wanted_role: str, wanted_title: str):
    found = find_all(root, wanted_role, wanted_title)
    if len(found) != 1:
        raise GroundingError(
            f"Expected one {wanted_role} titled {wanted_title!r}, found {len(found)}"
        )
    return found[0]


def press(element) -> None:
    error = AX.AXUIElementPerformAction(element, "AXPress")
    if error != 0:
        raise GroundingError(f"AXPress failed ({error})")


def set_value(element, text: str, label: str, *, ok=None) -> str:
    """Write a text control and read it back. Raises if the write did not stick.

    ``ok`` accepts a read-back that the control rewrites, such as a percent sign
    added after a VAT value.
    """
    error = AX.AXUIElementSetAttributeValue(element, "AXValue", text)
    readback = "" if value(element) is None else str(value(element))
    if error != 0 or (readback != text and not (ok is not None and ok(readback))):
        raise GroundingError(
            f"{label}: expected {text!r}, read back {readback!r} (AX error {error})"
        )
    return readback


def focused(app):
    return attr(app, "AXFocusedUIElement")


def focus(element) -> None:
    error = AX.AXUIElementSetAttributeValue(element, "AXFocused", True)
    if error != 0:
        raise GroundingError(f"Could not focus control (AX error {error})")


def activate() :
    """Bring Fakturama forward and return its AX application element."""
    if not AX.AXIsProcessTrusted():
        raise GroundingError(
            "Accessibility permission is not granted to the process running this script."
        )
    for running in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
        # Match the app itself. Helper processes also contain "Fakturama" in their name.
        if str(running.bundleIdentifier() or "") != "Fakturama.ID":
            continue
        running.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
        time.sleep(0.6)
        return AX.AXUIElementCreateApplication(running.processIdentifier())
    raise GroundingError("Fakturama is not running. Open Fakturama and retry.")


def _selected(element) -> bool:
    """Editor tabs are checkboxes. Selected is 1, not the boolean True."""
    return value(element) in (True, 1)


def editor_tabs(app):
    found = []
    for element in walk(app):
        if role(element) != "AXCheckBox":
            continue
        label = title(element).lstrip("*")
        if not label or label == "Empty Stack":
            continue
        found.append(element)
    return found


def tab_titles(app) -> list[str]:
    return [title(element) for element in editor_tabs(app)]


def find_tab(app, name: str):
    """A leading '*' marks an unsaved editor. Match the name with or without it."""
    matches = []
    for element in editor_tabs(app):
        label = title(element).lstrip("*")
        if label == name or label.startswith(name + " "):
            matches.append(element)
    if len(matches) != 1:
        raise GroundingError(
            f"Expected one tab {name!r}, found {len(matches)}. Open tabs: {tab_titles(app)}"
        )
    return matches[0]


def tab_is_active(app, name: str) -> bool:
    try:
        element = find_tab(app, name)
    except GroundingError:
        return False
    return _selected(element)


def show_tab(app, name: str) -> None:
    element = find_tab(app, name)
    if not _selected(element):
        press(element)
        time.sleep(0.45)
    if not _selected(find_tab(app, name)):
        raise GroundingError(f"Tab {name!r} did not become active")


def windows(app) -> list:
    return [element for element in (attr(app, "AXWindows") or [])]


def window_titled(app, fragment: str):
    hits = [window for window in windows(app) if fragment.lower() in title(window).lower()]
    if len(hits) != 1:
        names = [title(window) for window in windows(app)]
        raise GroundingError(
            f"Expected one window containing {fragment!r}, found {len(hits)}: {names}"
        )
    return hits[0]
